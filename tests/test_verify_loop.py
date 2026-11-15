"""Tests for the generate -> execute -> repair loop and best-of-N sampling."""

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from inference.verify_loop import (
    best_of_n,
    default_score,
    extract_code,
    format_failure,
    solve,
)

GOOD = "def add(a, b):\n    return a + b\n"
BAD = "def add(a, b):\n    return a - b\n"


def _runner(results):
    """Return an execute() that yields the given outcomes in order."""
    queue = list(results)

    def execute(files, command):
        assert "main.py" in files
        assert command
        return queue.pop(0)

    return execute


def _generator(replies):
    queue = list(replies)
    prompts = []

    def generate(messages):
        prompts.append(messages[-1]["content"])
        return queue.pop(0)

    generate.prompts = prompts
    return generate


def test_solve_repairs_the_real_failure():
    generate = _generator([BAD, GOOD])
    execute = _runner([
        {"success": False, "exit_code": 1, "stdout": "1 failed", "stderr": "assert 2 == -1"},
        {"success": True, "exit_code": 0, "stdout": "1 passed", "stderr": ""},
    ])

    result = solve("write add(a, b)", generate, execute, attempts=3, log=lambda _: None)

    assert result.success is True
    assert result.attempts_used == 2
    assert result.code.strip() == GOOD.strip()
    # The repair prompt must carry the actual failure, not a generic retry.
    assert "assert 2 == -1" in generate.prompts[1]
    assert "root cause" in generate.prompts[1]


def test_solve_returns_failure_after_budget():
    generate = _generator([BAD, BAD, BAD])
    execute = _runner([
        {"success": False, "exit_code": 1, "stdout": "", "stderr": "boom"}
        for _ in range(3)
    ])

    result = solve("write add", generate, execute, attempts=3, log=lambda _: None)

    assert result.success is False
    assert result.attempts_used == 3
    assert [attempt.index for attempt in result.attempts] == [1, 2, 3]
    assert all(attempt.exit_code == 1 for attempt in result.attempts)


def test_solve_places_test_files_beside_the_solution():
    seen = {}

    def execute(files, command):
        seen.update(files)
        return {"success": True, "exit_code": 0, "stdout": "", "stderr": ""}

    solve(
        "write add",
        _generator([GOOD]),
        execute,
        tests={"test_main.py": "from main import add\n"},
        log=lambda _: None,
    )
    assert seen["test_main.py"].startswith("from main import add")
    assert seen["main.py"].strip() == GOOD.strip()


def test_solve_treats_runner_crash_as_failure():
    def broken(files, command):
        raise RuntimeError("sandbox unavailable")

    result = solve("write add", _generator([BAD, GOOD]), broken, attempts=2, log=lambda _: None)
    assert result.success is False
    assert result.attempts_used == 2
    assert "sandbox unavailable" in result.attempts[0].stderr


def test_solve_validates_attempts():
    with pytest.raises(ValueError):
        solve("x", _generator([]), _runner([]), attempts=0)


def test_solve_uses_prompt_notes():
    generate = _generator([GOOD])
    solve(
        "fix the failing test in this module",
        generate,
        _runner([{"success": True, "exit_code": 0}]),
        attempts=1,
        log=lambda _: None,
    )
    prompt = generate.prompts[0]
    assert "CATEGORY NOTES:" in prompt
    assert "DEBUGGING PROCEDURE" in prompt


def test_extract_code_strips_fences():
    assert extract_code("```python\nprint(1)\n```") == "print(1)"
    assert extract_code("print(1)") == "print(1)"


def test_format_failure_includes_output_and_truncates():
    text = format_failure({
        "success": False,
        "exit_code": 2,
        "stderr": "x" * 5000,
        "stdout": "partial",
    })
    assert "STDERR" in text and "STDOUT" in text
    assert len(text) < 5000 * 2


def test_format_failure_handles_timeout_and_empty_output():
    text = format_failure({"timed_out": True, "exit_code": -1})
    assert "timed out" in text


def test_best_of_n_picks_the_highest_score():
    generate = _generator(["short", "a much better and longer answer", "mid"])

    def score(text):
        return float(len(text))

    result = best_of_n("explain X", generate, n=3, score=score, log=lambda _: None)
    assert result["text"] == "a much better and longer answer"
    assert result["score"] == float(len("a much better and longer answer"))
    assert len(result["samples"]) == 3


def test_best_of_n_validates_n():
    with pytest.raises(ValueError):
        best_of_n("x", _generator([]), n=0)


def test_default_score_prefers_structure_and_penalises_placeholders():
    good = "1. First step\n2. Second step\n\nNumbers: 42 and 7."
    assert default_score(good) > default_score("i think maybe it depends")
    assert default_score("") < 0
    assert default_score("TODO placeholder") < default_score(good)
