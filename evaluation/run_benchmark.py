#!/usr/bin/env python3
"""Complete model benchmark for Penthos.

Runs the local Penthos model (lightweight 4B-scale weights, MLX 4-bit) across
every category and grades each answer:

  - Free-form tasks (baseline prompts + non-code dataset records): grade by
    rubric term coverage. Every output is saved for manual review.
  - Executable tasks (code/debugging/security records from the verified
    dataset): the model's generated source is placed as the main file next to
    the reference tests and executed inside the Docker sandbox. Pass/fail is
    decided by the sandbox result (and expected output when defined). No
    model output is ever executed on the host.

Results are written to evaluation/results/<stamp>/ (report.json, per-task
outputs, summary.md).

Usage:
  python evaluation/run_benchmark.py                 # full suite, greedy decode
  python evaluation/run_benchmark.py --categories coding,reasoning
  python evaluation/run_benchmark.py --ids coding_001 seed-reason-sheep-0008
  python evaluation/run_benchmark.py --temp 0.2 --max-tokens 1024
"""

import argparse
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Loader identifier for the local weights (functional handle for mlx_lm.load).
# The evaluated model is presented to the user as Penthos.
MODEL = "Qwen/Qwen3-4B-MLX-4bit"

from inference.prompt import PENTHOS_SYSTEM_PROMPT  # noqa: E402

TASKS_JSON = REPO_ROOT / "evaluation" / "baseline" / "tasks.json"
VERIFIED_JSONL = REPO_ROOT / "datasets" / "verified" / "verified.jsonl"
RESULTS_DIR = REPO_ROOT / "evaluation" / "results"

# Per-record benchmark rubrics for the non-code records in datasets/verified.
# Evaluation artifacts only: they tag the terms a good answer should contain.
VERIFIED_RUBRICS = {
    "seed-reason-sheep-0008": ["9"],
    "seed-reason-ml-0009": ["supervised", "unsupervised", "labeled", "unlabeled"],
    "seed-chat-penthos-0010": ["open-source", "coding", "agent"],
    "seed-agentic-loop-0012": ["fix", "test", "report"],
    "challenge-cycle-1009": ["tortoise", "hare", "o(1)", "hash"],
    "challenge-endpoint-1008": ["route", "schema", "test", "sandbox", "auth"],
    "ff-debug-lifecycle-1101": ["reproduce", "hypothesis", "logs", "verify"],
    "ff-debug-traceback-1102": ["traceback", "stack", "frame", "reproduce"],
    "ff-debug-bisect-1103": ["reproduce", "bisect", "commit", "verify"],
    "ff-reason-trains-1104": ["closing", "speed", "hour", "2.5"],
    "ff-reason-sort-1105": ["o(n log n)", "in-place", "space", "worst"],
    "ff-sec-hardcoded-1106": ["revoke", "rotate", "secret", "scan"],
    "ff-sec-passwords-1107": ["hash", "salt", "argon2", "bcrypt"],
    "ff-se-endpoint-1108": ["route", "auth", "validate", "test", "prisma"],
    "ff-se-review-1109": ["test", "style", "security", "behavior", "verify"],
    "ff-se-refactor-1110": ["helper", "contract", "call", "test"],
    "ff-se-prisma-1111": ["schema", "migration", "backfill", "nullable", "rollback"],
    "ff-agent-ci-1112": ["reproduce", "fix", "test", "verify", "report"],
    "ff-agent-triage-1113": ["reproduce", "minimal", "bisect", "plan"],
    "ff-chat-use-1114": ["agent", "coding", "open-source", "verify", "build"],
    "ff-chat-learn-1115": ["practice", "project", "documentation", "habit"],
    "ff-code-contract-1116": ["signature", "contract", "import", "export", "test"],
    "ff-code-bigo-1117": ["o(n)", "o(n^2)", "hash", "input"],
}

# When a rubric is present, an answer passes if at least this many terms hit.
VERIFIED_RUBRIC_MIN = {
    "seed-reason-sheep-0008": 1,
    "seed-reason-ml-0009": 3,
    "seed-chat-penthos-0010": 2,
    "seed-agentic-loop-0012": 3,
    "challenge-cycle-1009": 2,
    "challenge-endpoint-1008": 3,
    "ff-debug-lifecycle-1101": 2,
    "ff-debug-traceback-1102": 2,
    "ff-debug-bisect-1103": 2,
    "ff-reason-trains-1104": 2,
    "ff-reason-sort-1105": 2,
    "ff-sec-hardcoded-1106": 2,
    "ff-sec-passwords-1107": 2,
    "ff-se-endpoint-1108": 2,
    "ff-se-review-1109": 2,
    "ff-se-refactor-1110": 1,
    "ff-se-prisma-1111": 2,
    "ff-agent-ci-1112": 2,
    "ff-agent-triage-1113": 2,
    "ff-chat-use-1114": 2,
    "ff-chat-learn-1115": 1,
    "ff-code-contract-1116": 2,
    "ff-code-bigo-1117": 2,
}

# Expected stdout for records whose reference runner prints a known value.
VERIFIED_EXPECTED_OUTPUT = {
    "seed-ts-add-0003": "5",
}

# Original plain prompt used to reproduce the pre-improvement baseline.
BASELINE_SYSTEM_PROMPT = (
    "You are Penthos, an open-source coding AI. Answer the user's question "
    "directly and concretely. Prefer precise, actionable content over "
    "generalities. Do not be overly long."
)

CODE_DIRECTIVE = (
    "\n\nOutput ONLY the complete source code for the requested file. "
    "No markdown fences. No explanation. No prose."
)


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def read_jsonl(path: Path) -> list[dict]:
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            records.append(json.loads(line))
    return records


# ---------------------------------------------------------------------------
# Suite assembly
# ---------------------------------------------------------------------------

def _build_grading(record: dict) -> dict | None:
    """Derive sandbox grading from a verified executable record."""

    language = record.get("language")
    files = record.get("files") or {}
    if not files:
        return None

    main_file = "main.py" if language == "python" else "math.ts"

    grading = {
        "type": "sandbox_test",
        "language": language,
        "main_file": main_file,
        "other_files": {k: v for k, v in files.items() if k != main_file},
        "command": list(record["verification"]["command"])
        if record.get("verification", {}).get("command")
        else ["python", "-m", "pytest", "-q"],
        "expected_output": VERIFIED_EXPECTED_OUTPUT.get(record.get("id", "")),
    }
    if language == "typescript":
        # The reference runner imports add from './math'; the model's single
        # output file must satisfy that module contract.
        grading["contract"] = (
            "The file you write will be imported by another module as:\n"
            "import { add } from './math';\n"
            "So produce exactly a single module file: export function add(a: number, b: number): number { ... }"
        )
    return grading


def build_suite(
    sources: tuple[str, ...],
    categories: set[str] | None,
    ids: set[str] | None,
) -> list[dict]:
    tasks: list[dict] = []

    if "baseline" in sources:
        for task in json.loads(TASKS_JSON.read_text(encoding="utf-8")):
            task = dict(task)
            task["source"] = "baseline"
            tasks.append(task)

    if "verified" in sources:
        for record in read_jsonl(VERIFIED_JSONL):
            grading = _build_grading(record)
            task = {
                "id": record["id"],
                "category": record["category"],
                "difficulty": record["difficulty"],
                "language": record.get("language") or None,
                "source": "verified",
                "prompt": record["prompt"],
                "solution": record.get("solution", ""),
                "grading": grading,
                "rubric": VERIFIED_RUBRICS.get(record["id"]),
                "rubric_min": VERIFIED_RUBRIC_MIN.get(record["id"]),
            }
            tasks.append(task)

    if categories:
        tasks = [t for t in tasks if t["category"] in categories]
    if ids:
        tasks = [t for t in tasks if t["id"] in ids]

    return tasks


# ---------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------

def build_prompt(tokenizer, task: dict, system_prompt: str, thinking: bool) -> str:
    prompt_text = task["prompt"]
    grading = task.get("grading")
    if grading and grading["type"] == "sandbox_test":
        if grading.get("contract"):
            prompt_text = prompt_text + "\n\n" + grading["contract"]
        prompt_text = prompt_text + CODE_DIRECTIVE
    return tokenizer.apply_chat_template(
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt_text},
        ],
        tokenize=False,
        add_generation_prompt=True,
        enable_thinking=thinking,
    )


def generate(model, tokenizer, prompt: str, max_tokens: int, temp: float):
    from mlx_lm import stream_generate
    from mlx_lm.generate import make_sampler

    sampler = make_sampler(temp=temp, top_p=0.9) if temp > 0 else make_sampler(0.0)

    started = time.monotonic()
    output = ""
    for response in stream_generate(
        model,
        tokenizer,
        prompt=prompt,
        max_tokens=max_tokens,
        sampler=sampler,
    ):
        output += response.text
    elapsed = time.monotonic() - started
    tokens = len(tokenizer.encode(output))
    return output, tokens, elapsed


# ---------------------------------------------------------------------------
# Grading
# ---------------------------------------------------------------------------

def _extract_code(output: str) -> str:
    # Drop any Penthos chain-of-thought that made it into the output, then take
    # the last fenced code block (falling back to the raw text) as the code.
    text = re.sub(
        r"<\|start_of_thought\|>.*?<\|end_of_thought\|>", "", output,
        flags=re.DOTALL,
    )
    blocks = re.findall(r"```(?:[a-zA-Z]+)?\s*\n?(.*?)```", text, flags=re.DOTALL)
    if blocks:
        return blocks[-1].strip()
    return text.strip()


def clean_completion(output: str) -> str:
    """Reduce a raw streaming output to the clean final answer.

    Only outputs that visibly begin a thinking scaffold (``<thinking>``,
    the typed ``<|start_of_thought|>`` tag, or mlx_lm's literal `` thinking``
    opener) are rewritten; everything else is returned untouched, so a normal
    answer containing the words "thinking"/"response" is never damaged.

    Returns an empty string when a thinking scaffold is found but no answer can
    be isolated (e.g. the output was truncated mid-thought), so callers can
    drop such rows instead of training on them.
    """
    openers = (
        r"<think(?:ing)?>",
        r"<\|start_of_thought\|>",
        r"\A\s+thinking\b",
    )
    if not any(re.search(p, output) for p in openers):
        return output

    markers = (
        r"</think(?:ing)?>",
        r"<\|end_of_thought\|>",
        r"<response>",
        r"<\|answer\|>",
        r"\n\s*response\b",
        r"\n<\|im_start\|>response",
    )
    # Strip an opening scaffold tag so the real answer line is findable.
    head = re.sub(r"\A\s*<\s*(?:think(?:ing)?|start_of_thought)/?\s*\n?", "", output)
    # Take the content after the LAST closing marker emitted.
    best = -1
    for pattern in markers:
        match = re.search(r".*" + pattern, head, flags=re.DOTALL)
        if match and match.end() > best:
            best = match.end()
    if best >= 0:
        return head[best:].strip()
    return ""


def grade_freeform(task: dict, output: str) -> dict:
    rubric = [term for term in (task.get("rubric") or []) if term.strip()]
    if not rubric:
        return {
            "type": "freeform",
            "pass": None,
            "score": None,
            "rubric": [],
            "rubric_hits": [],
            "rubric_missed": [],
            "review_required": True,
        }
    lowered = output.casefold()
    hits = [term for term in rubric if term in lowered]
    missed = [term for term in rubric if term not in lowered]
    required = int(task.get("rubric_min") or len(rubric))
    return {
        "type": "freeform",
        "pass": len(hits) >= required,
        "score": round(len(hits) / len(rubric), 2),
        "required_hits": min(required, len(rubric)),
        "rubric": rubric,
        "rubric_hits": hits,
        "rubric_missed": missed,
        "review_required": True,
    }


def grade_executable(task: dict, output: str, docker_binary: str) -> dict:
    from sandbox import runner

    grading = task["grading"]
    files = dict(grading["other_files"])
    files[grading["main_file"]] = _extract_code(output)

    payload = {
        "language": grading["language"],
        "files": files,
        "command": grading["command"],
    }

    started = time.monotonic()
    try:
        result = runner.execute(payload, docker_binary=docker_binary)
    except RuntimeError as exc:
        return {
            "type": "sandbox_test",
            "pass": False,
            "error": f"sandbox unavailable: {exc}",
            "verified": False,
        }
    elapsed = time.monotonic() - started

    success = bool(result.get("success"))
    stdout = str(result.get("stdout", ""))
    stderr = str(result.get("stderr", ""))
    expected = grading.get("expected_output")
    matched = expected is None or expected in stdout

    return {
        "type": "sandbox_test",
        "pass": success and matched,
        "verified": True,
        "verified_elapsed": round(elapsed, 2),
        "exit_code": result.get("exit_code"),
        "timed_out": result.get("timed_out"),
        "expected_output": expected,
        "output_matched": matched,
        "stdout_truncated": str(stdout)[-300:],
        "stderr_truncated": str(stderr)[-300:],
    }


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def _summarize(results: list[dict]) -> dict:
    summary = {
        "total": len(results),
        "passed": sum(1 for r in results if r["pass"] is True),
        "failed": sum(1 for r in results if r["pass"] is False),
        "unscored": sum(1 for r in results if r["pass"] is None),
        "by_category": {},
        "by_source": {},
    }
    for result in results:
        category = result["category"]
        by_cat = summary["by_category"].setdefault(
            category,
            {"total": 0, "passed": 0, "failed": 0},
        )
        by_cat["total"] += 1
        if result["pass"] is True:
            by_cat["passed"] += 1
        elif result["pass"] is False:
            by_cat["failed"] += 1

        by_src = summary["by_source"].setdefault(
            result["source"],
            {"total": 0, "passed": 0, "failed": 0},
        )
        by_src["total"] += 1
        if result["pass"] is True:
            by_src["passed"] += 1
        elif result["pass"] is False:
            by_src["failed"] += 1

    for by_cat in summary["by_category"].values():
        by_cat["pass_rate"] = round(
            by_cat["passed"] / by_cat["total"], 2
        ) if by_cat["total"] else None
    for by_src in summary["by_source"].values():
        by_src["pass_rate"] = round(
            by_src["passed"] / by_src["total"], 2
        ) if by_src["total"] else None

    return summary


def _write_summary_md(out_dir: Path, meta: dict, results: list[dict], summary: dict) -> None:
    lines = [
        "# Penthos Model Benchmark",
        "",
        f"- model: `{meta['model']}`",
        f"- mlx_lm: {meta['mlx_lm_version']}",
        f"- temperature: {meta['temp']}",
        f"- max_tokens: {meta['max_tokens']}",
        f"- generated: {meta['generated_at']}",
        f"- total: {summary['total']} | passed: {summary['passed']} | "
        f"failed: {summary['failed']} | unscored: {summary['unscored']}",
        "",
        "## By category",
        "",
        "| category | total | passed | failed | pass rate |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for category, by_cat in sorted(summary["by_category"].items()):
        lines.append(
            f"| {category} | {by_cat['total']} | {by_cat['passed']} | "
            f"{by_cat['failed']} | {by_cat['pass_rate']} |"
        )
    lines += ["", "## Tasks", ""]
    for result in results:
        status = "PASS" if result["pass"] is True else (
            "FAIL" if result["pass"] is False else "REVIEW")
        lines.append(f"- [{status}] `{result['id']}` ({result['category']}): {result['grade'].get('type')}")
        if result["grade"].get("rubric_missed"):
            lines.append(f"    - missed rubric terms: {', '.join(result['grade']['rubric_missed'])}")
        if result["grade"].get("error"):
            lines.append(f"    - error: {result['grade']['error']}")
    lines.append("")
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "summary.md").write_text("\n".join(lines), encoding="utf-8")


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the Penthos model benchmark.")
    parser.add_argument("--sources", nargs="*", default=["baseline", "verified"],
                        choices=["baseline", "verified"])
    parser.add_argument("--categories", default=None,
                        help="comma-separated category filter")
    parser.add_argument("--ids", default=None,
                        help="comma-separated task id filter")
    parser.add_argument("--limit", type=int, default=0,
                        help="run only the first N matching tasks")
    parser.add_argument("--temp", type=float, default=0.0)
    parser.add_argument("--max-tokens", type=int, default=4096)
    parser.add_argument("--docker", default="docker")
    parser.add_argument("--adapter", default=None,
                        help="path to a fine-tuned adapter (e.g. adapters/penthos-lora)")
    parser.add_argument("--out", default=None,
                        help="output directory (default evaluation/results/<stamp>)")
    parser.add_argument("--thinking", action="store_true", default=True,
                        help="enable Penthos chain-of-thought (default on)")
    parser.add_argument("--no-thinking", action="store_false", dest="thinking",
                        help="disable Penthos chain-of-thought")
    parser.add_argument("--system-prompt", choices=["penthos", "baseline"],
                        default="penthos",
                        help="system prompt used for generation (default penthos)")
    args = parser.parse_args(argv)

    categories = {c.strip() for c in (args.categories or "").split(",") if c.strip()}
    ids = {i.strip() for i in (args.ids or "").split(",") if i.strip()}

    tasks = build_suite(tuple(args.sources), categories, ids)
    if args.limit:
        tasks = tasks[: args.limit]
    if not tasks:
        print("no tasks matched")
        return 2

    stamp = utcnow().replace(":", "-")
    out_dir = Path(args.out or RESULTS_DIR / f"benchmark_{stamp}")

    print(f"loading model {MODEL}" + (f" + adapter {args.adapter}" if args.adapter else "") + " ...")
    from mlx_lm import load

    model, tokenizer = load(MODEL, adapter_path=args.adapter)

    meta = {
        "model": MODEL,
        "adapter": args.adapter,
        "mlx_lm_version": __import__("mlx_lm").__version__,
        "temp": args.temp,
        "max_tokens": args.max_tokens,
        "thinking": args.thinking,
        "system_prompt": (
            PENTHOS_SYSTEM_PROMPT if args.system_prompt == "penthos"
            else BASELINE_SYSTEM_PROMPT
        ),
        "generated_at": stamp,
    }

    results = []
    for index, task in enumerate(tasks, start=1):
        # Sandbox tasks demand "output ONLY the code": chain-of-thought would
        # pollute the file, so those run without thinking regardless of the
        # --thinking flag. Free-form tasks keep thinking when enabled.
        use_thinking = args.thinking and not task.get("grading")
        prompt = build_prompt(tokenizer, task, meta["system_prompt"], use_thinking)
        print(f"[{index}/{len(tasks)}] {task['id']} ({task['category']}) ... ", end="", flush=True)
        started = time.monotonic()
        try:
            output, tokens, elapsed = generate(model, tokenizer, prompt, args.max_tokens, args.temp)
        except KeyboardInterrupt:
            print("\ninterrupted; saving partial results")
            summary = _write_results(out_dir, meta, results)
            print_summary(summary)
            return 130

        if task.get("grading") and task["grading"]["type"] == "sandbox_test":
            grade = grade_executable(task, output, args.docker)
        else:
            grade = grade_freeform(task, output)

        total_time = time.monotonic() - started
        status = "PASS" if grade["pass"] is True else (
            "FAIL" if grade["pass"] is False else "REVIEW")
        detail = ""
        if grade["type"] == "sandbox_test" and grade.get("verified"):
            detail = f" exit={grade.get('exit_code')} matched={grade.get('output_matched')}"
        elif grade["type"] == "freeform":
            detail = f" score={grade.get('score')}"
        print(f"{status}{detail} ({tokens} tok, {round(total_time, 1)}s)")

        results.append({
            "id": task["id"],
            "category": task["category"],
            "difficulty": task["difficulty"],
            "language": task.get("language"),
            "source": task["source"],
            "thinking": use_thinking,
            "prompt": task["prompt"],
            "output": output,
            "tokens": tokens,
            "elapsed_s": round(total_time, 2),
            "pass": grade["pass"],
            "grade": grade,
        })

    summary = _write_results(out_dir, meta, results)
    print_summary(summary)
    print(f"results: {out_dir}")
    return 1 if summary["failed"] else 0


def _write_results(out_dir: Path, meta: dict, results: list[dict]) -> dict:
    summary = _summarize(results)
    out_dir.mkdir(parents=True, exist_ok=True)
    outputs_dir = out_dir / "outputs"
    outputs_dir.mkdir(parents=True, exist_ok=True)
    for result in results:
        (outputs_dir / f"{result['id']}.txt").write_text(
            result["output"], encoding="utf-8")
    (out_dir / "report.json").write_text(
        json.dumps({"meta": meta, "summary": summary, "results": results},
                   indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    _write_summary_md(out_dir, meta, results, summary)
    return summary


def print_summary(summary: dict) -> None:
    print("\n=== summary ===")
    print(f"total: {summary['total']} | passed: {summary['passed']} | "
          f"failed: {summary['failed']} | unscored: {summary['unscored']}")
    for category, by_cat in sorted(summary["by_category"].items()):
        print(f"  {category:>22}: {by_cat['passed']}/{by_cat['total']} "
              f"({by_cat['pass_rate']})")


if __name__ == "__main__":
    raise SystemExit(main())