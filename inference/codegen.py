"""Multi-file code generation pipeline for Pari.

A small model writes far better code when a large request is decomposed. This
module turns "build me X" into:

1. PLAN      — the model returns a JSON file plan (paths, purposes, entry point).
2. GENERATE  — one focused call per file, with the shared contract in the prompt.
3. CHECK     — cheap static checks (empty files, placeholders, unbalanced
               brackets) catch the failure modes that waste a full rerun.
4. REVIEW    — the model critiques its own project and flags files to rewrite;
               flagged files are regenerated once with the issue in context.
5. WRITE     — files land in a workspace, paths confined to it.
6. VERIFY    — an optional caller-supplied check (for example the Docker
               sandbox) runs the entry point or test command.

Nothing here imports a model runtime, so the pipeline is testable on any
machine and reusable by the chat, the agent, and the HTTP server. The caller
passes a ``generate(messages) -> str`` callable.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from inference.prompt import (
    MODEL_DISPLAY,
    PARI_SYSTEM_PROMPT,
    prompt_notes,
)

GenerateFn = Callable[[list[dict]], str]

MAX_FILES = 8
MAX_REWRITES = 3

# Extensions a build may write. Everything else is rejected so a confused model
# cannot drop binaries or overwrite files outside the workspace.
ALLOWED_EXTENSIONS = {
    ".py", ".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".go", ".rs",
    ".java", ".kt", ".rb", ".php", ".cs", ".c", ".h", ".cpp", ".hpp",
    ".html", ".css", ".scss", ".sql", ".sh", ".bash", ".json", ".yml",
    ".yaml", ".toml", ".ini", ".cfg", ".md", ".txt", ".env.example",
    ".dockerfile", ".gitignore",
}

PLAN_PROMPT = """Break this build request into the smallest complete set of files.

REQUEST:
{request}

Reply with ONLY a JSON object in this exact shape:

{{"project": "short-kebab-name",
  "language": "primary language",
  "entrypoint": "relative/path/to/the/file/a/user/rus",
  "test_command": ["argv", "list", "as", "strings"],
  "files": [{{"path": "relative/path.ext", "purpose": "one sentence, including the public names this file exports"}}]}}

Rules:
- Between 1 and {max_files} files. No file that does not need to exist.
- Paths are relative, no leading slash, no "..".
- Use the standard library or the most common package for the language; list
  any third-party dependency in a requirements/package file inside the plan.
- The entry point must run the project with the test command, with no manual
  editing by the user.
- Do not write any code yet, and do not explain the plan outside the JSON."""

FILE_PROMPT = """Write the complete contents of one file in a project.

ORIGINAL REQUEST:
{request}

PROJECT PLAN:
{plan}

FILE TO WRITE NOW: {path}
ITS PURPOSE: {purpose}

Rules:
- Output ONLY the complete contents of `{path}`. No markdown fences, no prose.
- Match the other files exactly: same module paths, exported names, signatures,
  and data shapes.
- No placeholders, TODOs, or "..." in place of logic. Everything is implemented.
- Include imports, docstrings, and type hints. Include tests when this file is a
  test file.
- The code must run as written."""


@dataclass
class BuildResult:
    """Outcome of a multi-file build."""

    plan: dict[str, Any]
    files: dict[str, str] = field(default_factory=dict)
    written: list[str] = field(default_factory=list)
    issues: list[dict[str, str]] = field(default_factory=list)
    review: dict[str, Any] | None = None
    checks: Any = None


# ---------------------------------------------------------------------------
# Parsing helpers (pure, testable without a model)
# ---------------------------------------------------------------------------

def extract_json_object(text: str) -> dict[str, Any] | None:
    """Return the first complete JSON object in ``text``, ignoring fences/prose."""
    if not text:
        return None
    start = text.find("{")
    while start != -1:
        depth = 0
        in_string = False
        escaped = False
        for index in range(start, len(text)):
            char = text[index]
            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
                continue
            if char == '"':
                in_string = True
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    candidate = text[start:index + 1]
                    try:
                        data = json.loads(candidate)
                    except json.JSONDecodeError:
                        break
                    if isinstance(data, dict):
                        return data
                    break
        start = text.find("{", start + 1)
    return None


def normalize_path(path: str) -> str:
    """Normalize a plan path, rejecting absolute paths and traversal."""
    cleaned = path.strip().strip("`\"'").replace("\\", "/")
    while cleaned.startswith("./"):
        cleaned = cleaned[2:]
    cleaned = cleaned.lstrip("/")
    if not cleaned or cleaned in (".", ".."):
        raise ValueError(f"invalid path: {path!r}")
    parts = [part for part in cleaned.split("/") if part not in ("", ".")]
    if any(part == ".." for part in parts):
        raise ValueError(f"path escapes the workspace: {path!r}")
    cleaned = "/".join(parts)
    suffix = Path(cleaned).suffix.lower()
    name = Path(cleaned).name.lower()
    allowed_names = (".gitignore", ".env.example", "dockerfile")
    if suffix not in ALLOWED_EXTENSIONS and name not in allowed_names:
        raise ValueError(f"unsupported file type: {path!r}")
    return cleaned


def _fallback_plan(text: str) -> dict[str, Any] | None:
    """Recover a usable plan when the model ignored the JSON instruction."""
    pattern = re.compile(
        r"(?:^|\n)\s*(?:[-*]|\d+\.)?\s*`?([\w./-]+\.(?:"
        r"py|js|jsx|ts|tsx|go|rs|java|rb|php|html|css|json|sh|sql|md|ya?ml|toml))`?"
        r"\s*[:—\-]\s*(.*)",
    )
    files: list[dict[str, str]] = []
    for match in pattern.finditer(text):
        try:
            path = normalize_path(match.group(1))
        except ValueError:
            continue
        if any(existing["path"] == path for existing in files):
            continue
        files.append({"path": path, "purpose": match.group(2).strip()[:300]})
    if not files:
        return None
    return {
        "project": "pari-build",
        "language": "",
        "entrypoint": files[0]["path"],
        "test_command": [],
        "files": files,
    }


def parse_file_plan(text: str, max_files: int = MAX_FILES) -> dict[str, Any]:
    """Parse a plan response into a normalized plan dict.

    Raises ValueError when no plan can be recovered, so the caller can retry
    with a stricter prompt instead of writing a half-empty project.
    """
    data = extract_json_object(text)
    files_raw: list[Any] = []
    if data and isinstance(data.get("files"), list):
        files_raw = data["files"]
    if not files_raw:
        fallback = _fallback_plan(text)
        if fallback is None:
            raise ValueError("no file plan found in the model response")
        return fallback

    files: list[dict[str, str]] = []
    for item in files_raw:
        if isinstance(item, str):
            path, purpose = item, ""
        elif isinstance(item, dict):
            path = item.get("path") or item.get("file") or ""
            purpose = item.get("purpose") or item.get("description") or ""
        else:
            continue
        try:
            normalized = normalize_path(str(path))
        except ValueError:
            continue
        if any(existing["path"] == normalized for existing in files):
            continue
        files.append({"path": normalized, "purpose": str(purpose)[:300]})

    if not files:
        raise ValueError("file plan contained no usable paths")
    files = files[:max_files]

    entrypoint = str(data.get("entrypoint") or "").strip() if data else ""
    try:
        entrypoint = normalize_path(entrypoint) if entrypoint else files[0]["path"]
    except ValueError:
        entrypoint = files[0]["path"]
    if entrypoint not in {item["path"] for item in files}:
        entrypoint = files[0]["path"]

    command = data.get("test_command") if data else None
    if not isinstance(command, list) or not all(isinstance(c, str) for c in command):
        command = []

    return {
        "project": re.sub(r"[^a-z0-9-]+", "-", str(data.get("project") or "pari-build").lower()).strip("-")
        or "pari-build",
        "language": str(data.get("language") or ""),
        "entrypoint": entrypoint,
        "test_command": command,
        "files": files,
    }


def strip_code_fences(text: str) -> str:
    """Return file contents from a model reply: last fenced block, or raw text."""
    if not text:
        return ""
    blocks = re.findall(r"```[a-zA-Z0-9_+-]*\s*\n(.*?)```", text, flags=re.DOTALL)
    if blocks:
        return blocks[-1].strip("\n")
    return text.strip("\n")


def clean_file_output(text: str) -> str:
    """Strip fences and a leading ``path:`` label from a generated file."""
    content = strip_code_fences(text)
    lines = content.splitlines()
    if lines:
        first = lines[0].strip().strip("`*_ ")
        if re.fullmatch(r"[\w./-]+\.(?:[a-zA-Z0-9]{1,8})(?::)?", first):
            remainder = "\n".join(lines[1:]).lstrip("\n")
            if remainder.strip():
                content = remainder
    return content


def plan_summary(plan: dict[str, Any]) -> str:
    """Human-readable contract block shared by every per-file prompt."""
    lines = [
        f"Project: {plan.get('project', 'pari-build')}",
        f"Language: {plan.get('language') or 'match the file extension'}",
        f"Entry point: {plan.get('entrypoint', '')}",
        "Files:",
    ]
    for item in plan.get("files", []):
        marker = " (entry point)" if item["path"] == plan.get("entrypoint") else ""
        lines.append(f"- {item['path']}{marker}: {item.get('purpose', '')}")
    return "\n".join(lines)


def _bracket_balance(code: str) -> bool:
    pairs = {")": "(", "]": "[", "}": "{"}
    opening = set(pairs.values())
    stack: list[str] = []
    in_string: str | None = None
    escaped = False
    in_line_comment = False
    in_block_comment = False
    index = 0
    while index < len(code):
        char = code[index]
        nxt = code[index + 1] if index + 1 < len(code) else ""
        if in_line_comment:
            if char == "\n":
                in_line_comment = False
        elif in_block_comment:
            if char == "*" and nxt == "/":
                in_block_comment = False
                index += 1
        elif in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == in_string:
                in_string = None
        elif char in ("'", '"', "`") and not (char == "'" and code[index - 1:index].isalnum()):
            in_string = char
        elif char == "/" and nxt == "/":
            in_line_comment = True
            index += 1
        elif char == "#" and not code[index - 1:index].strip(" \t"):
            in_line_comment = True
        elif char == "/" and nxt == "*":
            in_block_comment = True
            index += 1
        elif char in opening:
            stack.append(char)
        elif char in pairs:
            if not stack or stack[-1] != pairs[char]:
                return False
            stack.pop()
        index += 1
    return not stack


_PLACEHOLDER = re.compile(
    r"(?im)^\s*(?:#|//|--)?\s*(?:TODO|FIXME|XXX)\b|raise NotImplementedError|your code here",
)


def static_checks(files: dict[str, str]) -> list[dict[str, str]]:
    """Cheap checks that catch the most common broken-generation failure modes."""
    issues: list[dict[str, str]] = []
    for path, code in files.items():
        if not code.strip():
            issues.append({"path": path, "problem": "file is empty", "fix": "write the full file"})
            continue
        if _PLACEHOLDER.search(code):
            issues.append({
                "path": path,
                "problem": "contains a TODO/placeholder instead of logic",
                "fix": "implement the missing branch",
            })
        if Path(path).suffix.lower() in {".py", ".js", ".jsx", ".ts", ".tsx", ".go", ".rs",
                                         ".java", ".kt", ".rb", ".php", ".c", ".cpp", ".h"}:
            if not _bracket_balance(code):
                issues.append({
                    "path": path,
                    "problem": "unbalanced brackets — the file is truncated or malformed",
                    "fix": "close every block and function",
                })
    return issues


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

def _safe_target(workspace: Path, relative: str) -> Path:
    root = workspace.resolve()
    target = (root / relative).resolve()
    if target != root and root not in target.parents:
        raise ValueError(f"path escapes the build workspace: {relative}")
    return target


def _review_files(files: dict[str, str], request: str, generate: GenerateFn, log: Callable[[str], None]) -> dict[str, Any] | None:
    from inference.prompt import REVIEW_PROMPT

    budget = 60000
    body_lines: list[str] = []
    for path, code in files.items():
        clipped = code if len(code) <= budget // max(len(files), 1) else code[: budget // max(len(files), 1)]
        body_lines.append(f"--- {path} ---\n{clipped}")
    body = "\n\n".join(body_lines)

    messages = [
        {"role": "system", "content": PARI_SYSTEM_PROMPT},
        {"role": "user", "content": f"ORIGINAL REQUEST:\n{request}\n\nPROJECT:\n{body}\n\n{REVIEW_PROMPT}"},
    ]
    try:
        raw = generate(messages)
    except Exception as exc:  # pragma: no cover - model/runtime failure
        log(f"[{MODEL_DISPLAY} build] review skipped: {exc}")
        return None

    data = extract_json_object(raw)
    if data is None:
        log(f"[{MODEL_DISPLAY} build] review was not valid JSON; keeping the draft.")
        return None

    issues = [item for item in data.get("issues", []) if isinstance(item, dict)]
    rewrite = [str(item) for item in data.get("files_to_rewrite", []) if isinstance(item, str)]
    return {"verdict": data.get("verdict"), "issues": issues, "files_to_rewrite": rewrite}


def generate_project(
    request: str,
    generate: GenerateFn,
    workspace: str | Path | None = None,
    *,
    max_files: int = MAX_FILES,
    review: bool = True,
    domain: str | None = None,
    run_checks: Callable[[dict[str, str], dict[str, Any]], Any] | None = None,
    write: bool = True,
    log: Callable[[str], None] = print,
) -> BuildResult:
    """Plan, generate, review, and write a complete multi-file project.

    Args:
        request: what the user asked for.
        generate: ``generate(messages) -> str`` for the loaded model.
        workspace: destination directory; defaults to ``Pari/builds/<project>``.
        max_files: hard cap on files in the plan.
        review: run the self-review pass and rewrite flagged files once.
        domain: web | game | graphics3d | general; detected from the request
            when omitted. The playbook is injected into every prompt.
        run_checks: optional callback ``(files, plan) -> result`` used for
            verification (for example the Docker sandbox).
        write: set False to plan and generate without touching disk.
        log: progress sink.
    """
    log("[Pari build] planning files...")
    notes = prompt_notes(request, domain)
    plan_messages = [
        {"role": "system", "content": PARI_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": PLAN_PROMPT.format(request=request, max_files=max_files)
            + f"\n\nDOMAIN NOTES:\n{notes}",
        },
    ]
    plan = parse_file_plan(generate(plan_messages), max_files=max_files)
    log(f"[Pari build] {len(plan['files'])} file(s), entry point {plan['entrypoint']}")

    contract = plan_summary(plan)
    files: dict[str, str] = {}
    for item in plan["files"]:
        log(f"[Pari build] writing {item['path']}...")
        messages = [
            {"role": "system", "content": PARI_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": FILE_PROMPT.format(
                    request=request,
                    plan=contract,
                    path=item["path"],
                    purpose=item.get("purpose", ""),
                ) + f"\n\nDOMAIN NOTES:\n{notes}",
            },
        ]
        code = clean_file_output(generate(messages))
        if not code.strip():
            code = "# generation produced no content; retry with /build\n"
        files[item["path"]] = code

    result = BuildResult(plan=plan, files=files, issues=static_checks(files))

    if review:
        log("[Pari build] reviewing the project...")
        review_data = _review_files(files, request, generate, log)
        result.review = review_data
        if review_data:
            flagged: list[str] = []
            for path in review_data["files_to_rewrite"]:
                if path in files and path not in flagged:
                    flagged.append(path)
            for issue in review_data["issues"]:
                path = str(issue.get("path", ""))
                if path in files and path not in flagged:
                    flagged.append(path)
            for path in flagged[:MAX_REWRITES]:
                notes = [
                    f"- {issue.get('problem', '')} → {issue.get('fix', '')}"
                    for issue in review_data["issues"]
                    if str(issue.get("path", "")) == path
                ]
                fix_block = "\n".join(notes) or "- the previous attempt was incomplete"
                log(f"[Pari build] rewriting {path} after review...")
                messages = [
                    {"role": "system", "content": PARI_SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": (
                            FILE_PROMPT.format(
                                request=request,
                                plan=contract,
                                path=path,
                                purpose=next(
                                    (i.get("purpose", "") for i in plan["files"] if i["path"] == path),
                                    "",
                                ),
                            )
                            + f"\n\nA reviewer found these problems with the previous version:\n{fix_block}\n"
                            "Fix all of them. Output ONLY the complete corrected file."
                        ),
                    },
                ]
                fixed = clean_file_output(generate(messages))
                if fixed.strip():
                    files[path] = fixed
            result.issues = static_checks(files)

    if write:
        destination = Path(workspace) if workspace else Path("Pari") / "builds" / plan["project"]
        destination.mkdir(parents=True, exist_ok=True)
        for path, code in files.items():
            target = _safe_target(destination, path)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(code, encoding="utf-8")
            result.written.append(str(target))
        log(f"[Pari build] wrote {len(result.written)} file(s) to {destination}")

    if run_checks is not None:
        try:
            result.checks = run_checks(files, plan)
        except Exception as exc:  # pragma: no cover - sandbox/docker failure
            result.checks = {"success": False, "error": str(exc)}
            log(f"[Pari build] verification failed to run: {exc}")

    return result
