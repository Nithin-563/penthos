"""Transparent deterministic baseline quality scorer.

This is a heuristic used only to filter and rank candidates before training.
It does not measure reasoning quality or intelligence; it scores cheap,
observable signals such as field completeness, instruction length, presence
of answers/code/tests, and verification outcome.
"""

from training.data_pipeline import verify


DEFAULT_MIN_SCORE = 30.0

_WEIGHTS = {
    "completeness": 0.15,
    "instruction_clarity": 0.20,
    "answer_presence": 0.20,
    "code_presence": 0.10,
    "test_presence": 0.10,
    "verification_result": 0.10,
    "difficulty": 0.05,
    "reasoning_quality": 0.05,
    "security_indicator": 0.05,
}

_REASONING_MARKERS = (
    "explain",
    "why",
    "compare",
    "reason",
    "because",
    "difference",
    "describe",
    "analyze",
    "step",
    "summarize",
    "derive",
    "justify",
)

_DIFFICULTY_BASE = {
    "easy": 70,
    "medium": 80,
    "hard": 90,
    "expert": 95,
}


def score_candidate(
    candidate: dict,
    verification: dict | None = None,
    safety: dict | None = None,
) -> dict:
    """Score a candidate. Returns {'total': float, 'dimensions': {...}}.

    Deterministic: inputs fully determine the output (no randomness, no
    wall-clock dependence).
    """

    dimensions = {
        "completeness": _score_completeness(candidate),
        "instruction_clarity": _score_instruction(candidate),
        "answer_presence": _score_answer(candidate),
        "code_presence": _score_code(candidate),
        "test_presence": _score_tests(candidate),
        "verification_result": _score_verification(candidate, verification),
        "difficulty": _score_difficulty(candidate),
        "reasoning_quality": _score_reasoning(candidate),
        "security_indicator": _score_security(safety),
    }

    total = round(
        sum(dimensions[name] * _WEIGHTS[name] for name in dimensions), 1
    )

    return {
        "total": total,
        "dimensions": dimensions,
    }


def is_pass_score(total: float, min_score: float = DEFAULT_MIN_SCORE) -> bool:
    return total >= min_score


def _score_completeness(candidate: dict) -> float:
    present = 0
    fields = ("instruction", "language", "category", "difficulty")
    for field in fields:
        if candidate.get(field):
            present += 1
    optional = ("context", "expected_answer", "code", "tests")
    for field in optional:
        if field in candidate and candidate.get(field):
            present += 1
    return round((present / (len(fields) + len(optional))) * 100, 1)


def _score_instruction(candidate: dict) -> float:
    text = candidate.get("instruction") or ""
    length = len(text.strip())

    for marker in ("TODO", "lorem", "placeholder", "this is a test"):
        if marker in text.lower():
            return 20.0

    if length < 8:
        return 20.0
    if length < 40:
        return 60.0
    if length > 1200:
        return 50.0
    return 90.0


def _score_answer(candidate: dict) -> float:
    answer = candidate.get("expected_answer") or candidate.get("solution") or ""
    if not isinstance(answer, str) or not answer.strip():
        return 0.0
    if len(answer.strip()) < 5:
        return 40.0
    return 100.0


def _score_code(candidate: dict) -> float:
    executable = candidate.get("category") in verify.EXECUTABLE_CATEGORIES
    has_code = bool(candidate.get("code") or candidate.get("files"))
    if not executable:
        return 100.0
    return 100.0 if has_code else 0.0


def _score_tests(candidate: dict) -> float:
    executable = candidate.get("category") in verify.EXECUTABLE_CATEGORIES
    if not executable:
        return 100.0
    if candidate.get("tests") or candidate.get("test_command"):
        return 100.0
    if candidate.get("files"):  # files may embed a test harness
        return 90.0
    return 0.0


def _score_verification(candidate: dict, verification: dict | None) -> float:
    executable = candidate.get("category") in verify.EXECUTABLE_CATEGORIES
    if not executable:
        return 100.0
    if not verification:
        return 0.0
    status = verification.get("status")
    if status == "passed":
        return 100.0
    if status == "not_required":
        return 80.0
    if verification.get("timed_out"):
        return 0.0
    return 20.0


def _score_difficulty(candidate: dict) -> float:
    return float(_DIFFICULTY_BASE.get(candidate.get("difficulty"), 60))


def _score_reasoning(candidate: dict) -> float:
    text = " ".join(
        str(candidate.get("instruction") or "")
        + " "
        + str(candidate.get("expected_answer") or "")
    ).lower()

    matches = sum(1 for marker in _REASONING_MARKERS if marker in text)
    if matches >= 3:
        return 100.0
    if matches == 2:
        return 80.0
    if matches == 1:
        return 60.0
    return 50.0


def _score_security(safety: dict | None) -> float:
    if not safety:
        return 80.0
    if safety.get("unsafe"):
        return 0.0
    indicators = len(safety.get("indicators") or [])
    return max(90.0 - indicators * 40.0, 10.0)