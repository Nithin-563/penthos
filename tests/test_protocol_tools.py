"""Tests for the new protocol helpers (arg_schema, validate_arguments, partial_tool_call)."""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from agent.tools import Tool, validate_arguments
from agent.protocol import arg_schema, parse_tool_call, partial_tool_call


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
