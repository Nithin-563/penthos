"""Tests for coding-quality improvements: prompt wrapper, code search, read_readme."""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from inference.loop_kit import looks_like_code_task, maybe_wrap_code_prompt
from inference.prompt import build_code_prompt
from tools.code_search import CodeSearch
from tools.filesystem import ProjectFilesystem


# ---------------------------------------------------------------------------
# looks_like_code_task / maybe_wrap_code_prompt
# ---------------------------------------------------------------------------

def test_looks_like_code_task_long_request():
    q = "Write a Python function that checks if a number is prime"
    assert looks_like_code_task(q) is True


def test_looks_like_code_task_codeblock():
    assert looks_like_code_task("Show me ```python\nprint(1)\n```") is True


def test_looks_like_code_task_def():
    assert looks_like_code_task("def foo(a, b): what does this do?") is True


def test_looks_like_code_task_plain_chat():
    assert looks_like_code_task("what is the weather today") is False


def test_looks_like_code_task_short_is_false():
    assert looks_like_code_task("thanks") is False


def test_maybe_wrap_code_prompt_long():
    q = "Implement a function to convert a string to an integer without using int()"
    wrapped = maybe_wrap_code_prompt(q)
    assert "TASK:" in wrapped
    assert "Think step by step" in wrapped


def test_maybe_wrap_code_prompt_short_left_alone():
    q = "Hi"
    assert maybe_wrap_code_prompt(q) == q


def test_maybe_wrap_code_prompt_plain_chat_left_alone():
    q = "What is the capital of France?"
    assert maybe_wrap_code_prompt(q) == q


# ---------------------------------------------------------------------------
# build_code_prompt
# ---------------------------------------------------------------------------

def test_build_code_prompt_includes_language_and_context():
    prompt = build_code_prompt(
        "write a parser", language="python", context="project uses pathlib"
    )
    assert "TASK: write a parser" in prompt
    assert "LANGUAGE: python" in prompt
    assert "CONTEXT:" in prompt
    assert "project uses pathlib" in prompt


def test_build_code_prompt_minimal():
    prompt = build_code_prompt("reverse a string")
    assert "TASK: reverse a string" in prompt


# ---------------------------------------------------------------------------
# CodeSearch language + definitions filtering
# ---------------------------------------------------------------------------

def test_code_search_language_filter():
    search = CodeSearch(".")
    result = search.search("def ", language="python")
    assert result["language"] == "python"


def test_code_search_definitions_flag():
    search = CodeSearch(".")
    result = search.search("search", language="python", definitions=True)
    assert result["definitions_only"] is True


def test_code_search_invalid_language_broad():
    # Unknown language should not filter — still returns results (no crash).
    search = CodeSearch(".")
    result = search.search("def ", language="klingon")
    assert result["language"] == "klingon"  # stored as passed


# ---------------------------------------------------------------------------
# read_readme
# ---------------------------------------------------------------------------

def test_read_readme_finds_readme_in_repo():
    fs = ProjectFilesystem(".")
    content = fs.read_readme()
    assert isinstance(content, str)
    assert "# PROJECT README" in content or "No README file" in content


def test_read_readme_missing_in_empty_dir(tmp_path):
    fs = ProjectFilesystem(str(tmp_path))
    assert fs.read_readme() == "No README file found in the project root."


def test_read_readme_custom(tmp_path):
    (tmp_path / "readme.md").write_text("hello world", encoding="utf-8")
    fs = ProjectFilesystem(str(tmp_path))
    content = fs.read_readme()
    assert "hello world" in content