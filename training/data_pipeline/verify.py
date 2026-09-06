"""Candidate validation, safety scanning, and sandbox verification.

Executable coding candidates are verified with the existing Penthos Docker
sandbox (sandbox.runner.execute). There is no host fallback: if the sandbox
is unavailable or the candidate fails, the candidate is rejected, never run
on the host.
"""

from datetime import datetime, timezone

from sandbox import policies, runner


VERIFIER_VERSION = "1.0.0"

# Enum values compatible with datasets/schema.json (extended minimally).
SCHEMA_CATEGORIES = (
    "coding",
    "debugging",
    "reasoning",
    "software_engineering",
    "agentic",
    "security",
    "general_chat",
)
SCHEMA_DIFFICULTY = ("easy", "medium", "hard", "expert")
SCHEMA_SOURCES = ("human", "synthetic", "transformed")
SCHEMA_SOURCE_DEFAULT = "human"

# Categories whose candidates normally carry executable code.
EXECUTABLE_CATEGORIES = ("coding", "debugging", "software_engineering", "security")

# Languages supported by the existing sandbox.
EXECUTABLE_LANGUAGES = policies.SUPPORTED_LANGUAGES

# Rejection reasons emitted by this pipeline.
REASON_MALFORMED = "malformed_record"
REASON_UNSAFE = "unsafe_candidate"
REASON_EXECUTION_FAILED = "execution_failed"
REASON_TESTS_FAILED = "tests_failed"
REASON_TIMEOUT = "timeout"
REASON_INVALID_COMMAND = "invalid_command"
REASON_UNSUPPORTED_LANGUAGE = "unsupported_language"
REASON_DUPLICATE = "duplicate"
REASON_LOW_QUALITY = "low_quality"

# Hard-danger patterns. Any hit rejects the candidate without executing it.
_HARD_UNSAFE_PATTERNS = (
    ("ssh_keys", r"(\.ssh|id_rsa|id_ed25519)"),
    ("cloud_keys", r"(\.aws|aws_access_key_id|AKIA[0-9A-Z]{16}|~/.gcp)"),
    ("user_configs", r"(\.config|\.cache)"),
    ("system_files", r"/etc/(passwd|shadow|sudoers)"),
    ("docker_socket", r"docker\.sock"),
    ("env_files", r"\.env\b"),
    ("destructive", r"rm\s+-[a-zA-Z]*\s*/"),
    ("local_exec", r"(os\.system|subprocess\.run|subprocess\.Popen|os\.popen)"),
)

# Suspicious-but-not-fatal indicators. They reduce the security dimension in
# the quality scorer rather than rejecting outright (the sandbox blocks real
# network access anyway).
_SUSPICIOUS_PATTERNS = (
    ("network", r"(urlopen|requests\.|https?://|socket\.|ftplib)"),
    ("privilege", r"(/var/run/docker|unshare|mount)"),
)


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# Candidate validation
# ---------------------------------------------------------------------------

def validate_candidate(candidate: dict) -> list[str]:
    """Return a list of validation errors (empty when the candidate is valid)."""

    errors = []

    if not isinstance(candidate, dict):
        return ["candidate must be a JSON object"]

    if not isinstance(candidate.get("instruction"), str) or not candidate["instruction"].strip():
        errors.append("instruction is required and must be a non-empty string")

    category = candidate.get("category")
    if category not in SCHEMA_CATEGORIES:
        errors.append(f"category must be one of {SCHEMA_CATEGORIES}, got {category!r}")

    difficulty = candidate.get("difficulty")
    if difficulty not in SCHEMA_DIFFICULTY:
        errors.append(f"difficulty must be one of {SCHEMA_DIFFICULTY}, got {difficulty!r}")

    language = candidate.get("language")
    if language is not None and language != "" and not isinstance(language, str):
        errors.append("language must be a string")

    for key in ("context", "expected_answer", "code"):
        value = candidate.get(key)
        if value is not None and not isinstance(value, str):
            errors.append(f"{key} must be a string when present")

    files = candidate.get("files")
    if files is not None:
        if not isinstance(files, dict) or not all(
            isinstance(k, str) and isinstance(v, str) for k, v in files.items()
        ):
            errors.append("files must be an object of string to string")

    test_command = candidate.get("test_command")
    if test_command is not None:
        if not isinstance(test_command, list) or not all(
            isinstance(t, str) for t in test_command
        ):
            errors.append("test_command must be a list of strings")

    tests = candidate.get("tests")
    if tests is not None:
        if not isinstance(tests, list):
            errors.append("tests must be a list")
        else:
            for test in tests:
                if not (
                    isinstance(test, dict)
                    and "input" in test
                    and "expected" in test
                ):
                    errors.append("tests entries must have 'input' and 'expected'")

    source = candidate.get("source") or {}
    if not isinstance(source, dict):
        errors.append("source must be an object")
    else:
        source_type = source.get("type")
        if source_type is not None and source_type not in SCHEMA_SOURCES:
            errors.append(f"source.type must be one of {SCHEMA_SOURCES}")

    trajectory = candidate.get("trajectory")
    if trajectory is not None and not isinstance(trajectory, dict):
        errors.append("trajectory must be an object when present")

    return errors


def validate_record(record: dict) -> list[str]:
    """Validate a final, exported training record against the schema."""

    errors = []

    if not isinstance(record, dict):
        return ["record must be a JSON object"]

    for key in ("id", "prompt", "category", "difficulty"):
        if not isinstance(record.get(key), str) or not record[key]:
            errors.append(f"record field {key!r} is required")

    if record.get("category") not in SCHEMA_CATEGORIES:
        errors.append(f"record category invalid: {record.get('category')!r}")
    if record.get("difficulty") not in SCHEMA_DIFFICULTY:
        errors.append(f"record difficulty invalid: {record.get('difficulty')!r}")

    verification = record.get("verification")
    if not isinstance(verification, dict):
        errors.append("verification must be an object")
    else:
        status = verification.get("status")
        if status not in ("passed", "failed", "pending", "not_required"):
            errors.append(f"verification.status invalid: {status!r}")

    metadata = record.get("metadata")
    if not isinstance(metadata, dict):
        errors.append("metadata must be an object")
    elif metadata.get("source") not in SCHEMA_SOURCES:
        errors.append(f"metadata.source invalid: {metadata.get('source')!r}")

    return errors


# ---------------------------------------------------------------------------
# Safety scanning
# ---------------------------------------------------------------------------

def safety_scan(candidate: dict) -> dict:
    """Return {'unsafe': bool, 'labels': [...], 'indicators': [...]}."""

    if not isinstance(candidate, dict):
        return {"unsafe": True, "labels": ["malformed"], "indicators": []}

    texts = []
    code = candidate.get("code")
    if isinstance(code, str):
        texts.append(code)
    files = candidate.get("files")
    if isinstance(files, dict):
        texts.extend(v for v in files.values() if isinstance(v, str))
    answer = candidate.get("expected_answer")
    if isinstance(answer, str):
        texts.append(answer)

    corpus = "\n".join(texts)

    labels = [label for label, pattern in _HARD_UNSAFE_PATTERNS
              if _search(pattern, corpus)]
    indicators = [label for label, pattern in _SUSPICIOUS_PATTERNS
                  if _search(pattern, corpus)]

    return {
        "unsafe": bool(labels),
        "labels": labels,
        "indicators": indicators,
    }


def _search(pattern: str, text: str) -> bool:
    import re

    return re.search(pattern, text, flags=re.IGNORECASE) is not None


# ---------------------------------------------------------------------------
# Verification routing
# ---------------------------------------------------------------------------

def executable_decision(candidate: dict) -> str:
    """Decide how a candidate must be treated.

    Returns one of:
      - "verify": run through the Docker sandbox
      - "not_required": no executable verification (reasoning/chat/agentic)
      - "unsupported_language": executable category but language unsupported
      - "no_code": executable category but no code or files to run
    """

    if candidate.get("category") not in EXECUTABLE_CATEGORIES:
        return "not_required"

    if not (candidate.get("files") or candidate.get("code")):
        return "no_code"

    if candidate.get("language") not in EXECUTABLE_LANGUAGES:
        return "unsupported_language"

    return "verify"


def build_verify_payload(candidate: dict) -> dict:
    """Build the sandbox payload for a candidate.

    Prefers the candidate-provided `files`; falls back to a syntax smoke of
    the candidate `code` when only code is available.
    """

    language = candidate["language"]
    files = candidate.get("files")

    if not files:
        main_name = _main_filename(language)
        files = {main_name: candidate.get("code") or ""}

    command = candidate.get("test_command") or _default_command(language, files)

    payload = {
        "language": language,
        "files": files,
        "command": command,
    }

    timeout_seconds = candidate.get("timeout_seconds")
    if isinstance(timeout_seconds, int) and timeout_seconds >= 1:
        payload["timeout_seconds"] = timeout_seconds

    return payload


def _main_filename(language: str) -> str:
    if language == "python":
        return "main.py"
    if language == "node":
        return "main.js"
    if language == "typescript":
        return "main.ts"
    raise ValueError(f"Unsupported language: {language}")


def _default_command(language: str, files: dict) -> list[str]:
    has_tests = any(
        name.startswith("test_") or name.endswith("_test.py") or "test" in name
        for name in files
    )
    if language == "python":
        if has_tests:
            return ["python", "-m", "pytest", "-q"]
        return ["python", "-m", "py_compile", "main.py"]
    if language == "node":
        if has_tests:
            return ["node", "--test"]
        return ["node", "--check", "main.js"]
    if language == "typescript":
        if has_tests:
            return ["node", "--test"]
        return ["tsc", "--noEmit", "--skipLibCheck", "main.ts"]
    raise ValueError(f"Unsupported language: {language}")


def verify_candidate(
    candidate: dict,
    docker_binary: str = "docker",
    execute=None,
) -> dict:
    """Verify an executable candidate inside the Docker sandbox.

    Returns {"verification": {...}, "reason": str | None}.
    reason is None when verification passed.

    `execute` is resolved at call time so the live sandbox.runner.execute
    is always used (and can be patched in tests); it is never a host runner.
    """

    execute = execute if execute is not None else runner.execute
    payload = build_verify_payload(candidate)
    result = execute(payload, docker_binary=docker_binary)

    verification = {
        "required": True,
        "status": "passed" if result.get("success") else "failed",
        "command": list(payload["command"]),
        "exit_code": int(result.get("exit_code", -1)),
        "stdout": str(result.get("stdout", "")),
        "stderr": str(result.get("stderr", "")),
        "timed_out": bool(result.get("timed_out")),
        "verified_at": utcnow(),
        "language": str(result.get("language") or candidate.get("language", "")),
        "verifier_version": VERIFIER_VERSION,
    }

    if result.get("success"):
        return {"verification": verification, "reason": None}

    stderr = verification["stderr"] + verification["stdout"]

    if verification["timed_out"]:
        reason = REASON_TIMEOUT
    elif "not allowed" in stderr:
        reason = REASON_INVALID_COMMAND
    elif result.get("error") is not None:
        reason = REASON_EXECUTION_FAILED
    else:
        reason = REASON_TESTS_FAILED

    return {"verification": verification, "reason": reason}


def not_required_verification() -> dict:
    return {
        "required": False,
        "status": "not_required",
    }


def reject_record(candidate: dict, reason: str, detail: str) -> dict:
    """Build a rejection record for the rejected/<reason>.jsonl output."""

    return {
        "candidate": candidate,
        "reason": reason,
        "detail": detail,
        "rejected_at": utcnow(),
    }