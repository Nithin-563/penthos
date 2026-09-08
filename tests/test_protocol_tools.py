"""Tests for the new protocol helpers (arg_schema, validate_arguments, partial_tool_call)."""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from agent.tools import Tool, validate_arguments
from agent.protocol import (
    looks_like_tool_call,
    arg_schema,
    parse_tool_call,
    partial_tool_call,
)


# ---------------------------------------------------------------------------
# arg_schema
# ---------------------------------------------------------------------------

def add(a: int, b: int = 0) -> int:
    return a + b

def greet(name: str) -> str:
    return f"Hi {name}"

def versatile(*args, **kwargs):
    pass

def no_annotations(foo, bar="x"):
    pass


class Demo:
    def method(self, x: int) -> int:
        return x


def test_arg_schema_required_and_optional():
    schema = arg_schema(add)
    assert "a" in schema
    assert "b" in schema
    assert schema["a"]["required"] is True
    assert schema["b"]["required"] is False
    assert schema["a"]["type"] == "int"
    assert schema["b"]["type"] == "int"


def test_arg_schema_single_required():
    schema = arg_schema(greet)
    assert "name" in schema
    assert schema["name"]["required"] is True
    assert schema["name"]["type"] == "str"


def test_arg_schema_skips_varargs_and_kwargs():
    schema = arg_schema(versatile)
    assert len(schema) == 0


def test_arg_schema_no_annotations():
    schema = arg_schema(no_annotations)
    assert "foo" in schema
    assert "bar" in schema
    assert schema["foo"]["required"] is True
    assert schema["bar"]["required"] is False
    # no type key when there is no annotation
    assert "type" not in schema["foo"]


def test_arg_schema_skips_self():
    schema = arg_schema(Demo.method)
    assert "self" not in schema
    assert "x" in schema
    assert schema["x"]["type"] == "int"


# ---------------------------------------------------------------------------
# validate_arguments
# ---------------------------------------------------------------------------

from agent.tools import Tool

def echo(message: str, loud: bool = False) -> str:
    return message.upper() if loud else message

def compute(x: int, y: int, z: int) -> int:
    return x + y + z

def flexible(*args, **kwargs):
    return "ok"


_echo_tool = Tool(name="echo", description="echo", function=echo)
_compute_tool = Tool(name="compute", description="compute", function=compute)
_flex_tool = Tool(name="flex", description="flex", function=flexible)


def test_validate_arguments_all_good():
    unknown, missing = validate_arguments(_echo_tool, message="hi")
    assert unknown == []
    assert missing == []


def test_validate_arguments_optional_skipped():
    unknown, missing = validate_arguments(_echo_tool, message="hi")
    assert missing == []


def test_validate_arguments_missing_required():
    unknown, missing = validate_arguments(_compute_tool, x=1)
    assert "y" in missing
    assert "z" in missing
    assert unknown == []


def test_validate_arguments_unknown_keys():
    unknown, missing = validate_arguments(_echo_tool, message="hi", foo="bar")
    assert "foo" in unknown
    assert missing == []


def test_validate_arguments_both():
    unknown, missing = validate_arguments(
        _echo_tool, message="hi", extra="x"
    )
    assert "extra" in unknown
    assert missing == []


def test_validate_arguments_accepts_kwargs():
    unknown, missing = validate_arguments(_flex_tool, anything="ok")
    assert unknown == []
    assert missing == []


# ---------------------------------------------------------------------------
# partial_tool_call
# ---------------------------------------------------------------------------

def test_partial_tool_call_true():
    assert partial_tool_call("text <tool_call>{\"name\"") is True

def test_partial_tool_call_false_closed():
    assert partial_tool_call(
        "text <tool_call>{\"name\":\"echo\"}</tool_call>"
    ) is False

def test_partial_tool_call_no_tool_call():
    assert partial_tool_call("plain text") is False

def test_partial_tool_call_garbage():
    assert partial_tool_call("<tool_call> garbage no close") is True


# ---------------------------------------------------------------------------
# parse_tool_call edge cases
# ---------------------------------------------------------------------------

def test_parse_tool_call_malformed_json():
    assert parse_tool_call("<tool_call>{broken json}</tool_call>") is None

def test_parse_tool_call_missing_name():
    assert parse_tool_call(
        "<tool_call>{\"arguments\":{\"msg\":\"hi\"}}</tool_call>"
    ) is None

def test_parse_tool_call_empty_arguments():
    result = parse_tool_call(
        "<tool_call>{\"name\":\"echo\"}</tool_call>"
    )
    assert result is not None
    assert result["name"] == "echo"
    assert result["arguments"] == {}


def test_parse_tool_call_text_before_after():
    result = parse_tool_call(
        'I will use the tool:\n<tool_call>\n{"name":"echo","arguments":{"message":"hi"}}\n</tool_call>\nDone.'
    )
    assert result is not None
    assert result["name"] == "echo"


# ---------------------------------------------------------------------------
# Cross-base tool calls: bare JSON (Qwen2.5 style), fences, end markers
# ---------------------------------------------------------------------------

def test_parse_bare_json_in_code_fence_with_end_marker():
    # Exact reproduction of what the 7B shipped base emitted for "hi":
    output = '```json\n{"name":"read_readme","arguments:{}"}\n```<|im_end|>\n'
    result = parse_tool_call(output)
    assert result is not None
    assert result["name"] == "read_readme"
    assert result["arguments"] == {}


def test_parse_bare_json_no_fence():
    result = parse_tool_call('{"name":"echo","arguments":{"message":"hi"}}<|im_end|>')
    assert result is not None
    assert result["name"] == "echo"
    assert result["arguments"] == {"message": "hi"}


def test_parse_null_arguments_becomes_empty():
    result = parse_tool_call('{"name":"echo","arguments":null}')
    assert result is not None
    assert result["arguments"] == {}


def test_parse_repair_only_arguments_key_not_name():
    # The repair must not corrupt a valid name field or reject valid calls.
    result = parse_tool_call('{"name":"echo","arguments":{"message":"hi"}}')
    assert result is not None
    assert result["name"] == "echo"
    assert result["arguments"] == {"message": "hi"}


def test_parse_malformed_still_none():
    assert parse_tool_call("```json\n{broken json}\n```") is None
    assert parse_tool_call("plain prose only") is None


# ---------------------------------------------------------------------------
# looks_like_tool_call
# ---------------------------------------------------------------------------

def test_looks_like_tool_call_broken_blob():
    assert looks_like_tool_call('```json\n{"name":"read_readme","arguments:{}"}\n```<|im_end|>') is True


def test_looks_like_tool_call_bare_json():
    assert looks_like_tool_call('{"name":"echo","arguments":{}}') is True


def test_looks_like_not_tool_call():
    assert looks_like_tool_call("Hi! I'm Penthos. How can I help?") is False
    assert looks_like_tool_call("") is False
    assert looks_like_tool_call("<|im_end|>") is False


def test_looks_like_prose_with_keywords_is_false():
    # Prose that merely mentions the words is not a call attempt (no colon
    # after "name"), so it is not misclassified.
    assert looks_like_tool_call('The output should have a "name" and arguments.') is False


# ---------------------------------------------------------------------------
# tool_call_feedback (loop nudges malformed calls instead of surfacing junk)
# ---------------------------------------------------------------------------

from inference.loop_kit import tool_call_feedback


def test_feedback_for_malformed_call():
    # Repairable slips (e.g. "arguments:{}") are parsed and executed directly,
    # so no feedback is produced; truly unparseable shapes get a nudge.
    out = '```json\n{"name":"read_readme","arguments:{}"}\n```<|im_end|>'
    assert tool_call_feedback(out) is None
    broken = '{"name":"echo","arguments":[1,"x"]}'
    assert tool_call_feedback(broken) is not None
    assert "tool call" in tool_call_feedback(broken)


def test_no_feedback_for_valid_call():
    assert tool_call_feedback('{"name":"echo","arguments":{}}<|im_end|>') is None


def test_no_feedback_for_prose():
    assert tool_call_feedback("Hi! How can I help today?") is None
    assert tool_call_feedback("") is None
