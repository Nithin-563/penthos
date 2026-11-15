"""Tests for domain exemplars and pass@N solving."""

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from inference.exemplars import EXEMPLARS, exemplar_for
from inference.prompt import build_code_prompt
from inference.verify_loop import solve_best_of_n

GOOD = "def add(a, b):\n    return a + b\n"
BAD = "def add(a, b):\n    return a - b\n"


def test_exemplars_cover_the_three_domains():
    assert set(EXEMPLARS) == {"web", "game", "graphics3d"}
    for text in EXEMPLARS.values():
        assert len(text) > 100


def test_exemplar_lookup_and_fallback():
    assert "<main" in exemplar_for("web")
    assert exemplar_for("nope") == ""
    assert exemplar_for(None) == ""


def test_web_prompt_includes_reference_shape():
    prompt = build_code_prompt("Build a responsive landing page for a SaaS product")
    assert "REFERENCE SHAPE" in prompt
    assert 'aria-label="Primary"' in prompt


def test_game_prompt_includes_the_fixed_step_shape():
    prompt = build_code_prompt("Make a 2D platformer game with a player and collisions")
    assert "REFERENCE SHAPE" in prompt
    assert "accumulator" in prompt


def test_graphics_prompt_includes_the_mvp_chain():
    prompt = build_code_prompt("Render a rotating 3D cube with WebGL")
    assert "projection" in prompt.lower()
    assert "ndc" in prompt.lower()


def test_general_prompt_has_no_reference_shape():
    prompt = build_code_prompt("parse a CSV of invoices into records")
    assert "REFERENCE SHAPE" not in prompt


def _generator(replies):
    queue = list(replies)
    prompts = []

    def generate(messages):
        prompts.append(messages[-1]["content"])
        return queue.pop(0)

    generate.prompts = prompts
    return generate


def _runner(results):
    queue = list(results)

    def execute(files, command):
        return queue.pop(0)

    return execute


def test_second_sample_can_pass_without_repair():
    generate = _generator([BAD, GOOD])
    execute = _runner([
        {"success": False, "exit_code": 1, "stderr": "assert 2 == -1"},
        {"success": True, "exit_code": 0},
    ])

    result = solve_best_of_n(
        "write add(a, b)", generate, execute, samples=2, attempts=2, log=lambda _: None
    )

    assert result.success is True
    assert result.attempts_used == 2
    assert result.code.strip() == GOOD.strip()
    # Two independent samples, no repair prompt on the second call.
    assert "failed when it was actually executed" not in generate.prompts[1]


def test_repairs_after_every_sample_fails():
    generate = _generator([BAD, BAD, GOOD])
    execute = _runner([
        {"success": False, "exit_code": 1, "stderr": "first failure"},
        {"success": False, "exit_code": 1, "stderr": "second failure"},
        {"success": True, "exit_code": 0},
    ])

    result = solve_best_of_n(
        "write add(a, b)", generate, execute, samples=2, attempts=2, log=lambda _: None
    )

    assert result.success is True
    assert result.attempts_used == 3
    assert "second failure" in generate.prompts[2]


def test_budget_exhausted_returns_failure():
    generate = _generator([BAD, BAD, BAD])
    execute = _runner([{"success": False, "exit_code": 1}] * 3)

    result = solve_best_of_n(
        "write add", generate, execute, samples=2, attempts=1, log=lambda _: None
    )

    assert result.success is False
    assert result.attempts_used == 3


def test_solve_best_of_n_validates_arguments():
    with pytest.raises(ValueError):
        solve_best_of_n("x", _generator([]), _runner([]), samples=0)
    with pytest.raises(ValueError):
        solve_best_of_n("x", _generator([]), _runner([]), attempts=-1)
