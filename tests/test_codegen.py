"""Tests for the multi-file build pipeline and the Pari identity."""

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from inference.codegen import (
    clean_file_output,
    generate_project,
    normalize_path,
    parse_file_plan,
    static_checks,
    strip_code_fences,
)
from inference.prompt import PARI_SYSTEM_PROMPT

PLAN = json.dumps({
    "project": "Demo App",
    "language": "python",
    "entrypoint": "app.py",
    "test_command": ["python", "-m", "pytest", "-q"],
    "files": [
        {"path": "app.py", "purpose": "entry point, exports main()"},
        {"path": "./math_utils.py", "purpose": "exports add(a, b)"},
    ],
})


# ---------------------------------------------------------------------------
# Identity
# ---------------------------------------------------------------------------

def test_identity_is_pari_by_fubrio():
    assert "Pari" in PARI_SYSTEM_PROMPT
    assert "Fubrio" in PARI_SYSTEM_PROMPT


def test_no_old_branding_in_system_prompt():
    lowered = PARI_SYSTEM_PROMPT.lower()
    for stale in ("penthos", "penth", "deoid", "nithin", "reddy"):
        assert stale not in lowered


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def test_strip_code_fences_takes_fenced_block():
    assert strip_code_fences("here:\n```python\nprint(1)\n```\ndone") == "print(1)"


def test_strip_code_fences_passthrough():
    assert strip_code_fences("print(1)") == "print(1)"


def test_clean_file_output_removes_path_label_and_fence():
    raw = "```python\napp.py\nprint('hi')\n```"
    assert clean_file_output(raw) == "print('hi')"


def test_normalize_path_rejects_traversal():
    with pytest.raises(ValueError):
        normalize_path("../evil.py")


def test_normalize_path_rejects_absolute_and_binary():
    with pytest.raises(ValueError):
        normalize_path("/etc/passwd")
    with pytest.raises(ValueError):
        normalize_path("payload.exe")


def test_normalize_path_strips_dot_slash():
    assert normalize_path("./src/app.py") == "src/app.py"


def test_parse_file_plan_normalizes_and_dedupes():
    plan = parse_file_plan(PLAN)
    assert plan["project"] == "demo-app"
    assert plan["entrypoint"] == "app.py"
    paths = [item["path"] for item in plan["files"]]
    assert paths == ["app.py", "math_utils.py"]
    assert plan["test_command"] == ["python", "-m", "pytest", "-q"]


def test_parse_file_plan_fallback_from_bullets():
    text = "Plan:\n- main.py: entry point\n- utils/io.py: helpers"
    plan = parse_file_plan(text)
    assert [item["path"] for item in plan["files"]] == ["main.py", "utils/io.py"]


def test_parse_file_plan_raises_without_files():
    with pytest.raises(ValueError):
        parse_file_plan("I could not plan this.")


def test_parse_file_plan_bad_entrypoint_falls_back():
    raw = json.dumps({"files": ["a.py"], "entrypoint": "../../etc/passwd"})
    plan = parse_file_plan(raw)
    assert plan["entrypoint"] == "a.py"


# ---------------------------------------------------------------------------
# Static checks
# ---------------------------------------------------------------------------

def test_static_checks_flag_placeholder_and_unbalanced():
    issues = static_checks({
        "a.py": "def f():\n    # TODO implement\n    return 1\n",
        "b.py": "def g(:\n    return 2\n",
        "c.py": "",
    })
    paths = {issue["path"] for issue in issues}
    assert paths == {"a.py", "b.py", "c.py"}


def test_static_checks_clean_code_has_no_issues():
    code = "def add(a: int, b: int) -> int:\n    return a + b\n"
    assert static_checks({"add.py": code}) == []


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

def _builder_generate(calls, review_reply=None, rewrite_reply="print('fixed')"):
    def generate(messages):
        prompt = messages[-1]["content"]
        calls.append(prompt)
        if "Break this build request" in prompt:
            return PLAN
        if review_reply is not None and "You are reviewing code you just wrote" in prompt:
            return review_reply
        if "A reviewer found these problems" in prompt:
            return rewrite_reply
        return "print('hi')"

    return generate


def test_generate_project_writes_planned_files(tmp_path):
    calls = []
    result = generate_project(
        "build the demo app",
        _builder_generate(calls),
        tmp_path,
        review=False,
    )
    assert result.plan["project"] == "demo-app"
    assert set(result.files) == {"app.py", "math_utils.py"}
    assert (tmp_path / "app.py").read_text(encoding="utf-8") == "print('hi')"
    assert (tmp_path / "math_utils.py").exists()
    assert len(result.written) == 2
    assert any("Break this build request" in prompt for prompt in calls)


def test_generate_project_rewrites_flagged_file(tmp_path):
    review = json.dumps({
        "verdict": "needs_fixes",
        "issues": [{"path": "app.py", "problem": "prints nothing useful", "fix": "print fixed"}],
        "files_to_rewrite": ["app.py"],
    })
    calls = []
    result = generate_project(
        "build the demo app",
        _builder_generate(calls, review_reply=review),
        tmp_path,
        review=True,
    )
    assert result.review["verdict"] == "needs_fixes"
    assert result.files["app.py"] == "print('fixed')"
    assert (tmp_path / "app.py").read_text(encoding="utf-8") == "print('fixed')"


def test_generate_project_runs_checks_callback(tmp_path):
    seen = {}

    def checks(files, plan):
        seen["files"] = sorted(files)
        seen["entrypoint"] = plan["entrypoint"]
        return {"success": True}

    result = generate_project(
        "build the demo app",
        _builder_generate([]),
        tmp_path,
        review=False,
        run_checks=checks,
    )
    assert seen == {"files": ["app.py", "math_utils.py"], "entrypoint": "app.py"}
    assert result.checks == {"success": True}


def test_generate_project_can_skip_writing(tmp_path):
    result = generate_project(
        "build the demo app",
        _builder_generate([]),
        tmp_path / "none",
        review=False,
        write=False,
    )
    assert result.written == []
    assert not (tmp_path / "none").exists()


def test_generate_project_never_writes_outside_workspace(tmp_path):
    evil = json.dumps({
        "project": "evil",
        "files": [{"path": "../../escape.py", "purpose": "escape"}],
    })

    def generate(messages):
        return evil

    with pytest.raises(ValueError):
        generate_project("x", generate, tmp_path / "ws", review=False)
    assert not (tmp_path / "escape.py").exists()
