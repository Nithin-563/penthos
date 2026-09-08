"""Penthos tool-calling protocol."""

import inspect
import json


def _type_name(hint):
    """Best-effort, human-friendly name for a type annotation."""
    if hint is None:
        return None
    if hint is inspect.Parameter.empty:
        return None
    origin = getattr(hint, "__origin__", None)
    if origin is not None:
        args = getattr(hint, "__args__", ()) or ()
        inner = ", ".join(_type_name(a) or "any" for a in args)
        return f"{getattr(origin, '__name__', str(origin))}<{inner}>"
    return getattr(hint, "__name__", str(hint))


def arg_schema(func):
    """Derive an argument schema from a tool's Python signature.

    The model has to guess argument names when it only reads a plain-text
    description; introspection gives it the exact keys, types, and required
    flags, which removes the most common source of "tool call failed" errors.
    """
    schema: dict[str, dict] = {}
    try:
        signature = inspect.signature(func)
    except (TypeError, ValueError):
        return schema

    annotations = getattr(func, "__annotations__", {}) or {}

    for param_name, param in signature.parameters.items():
        if param_name == "self" or param_name.startswith("_"):
            continue
        if param.kind in (
            inspect.Parameter.VAR_POSITIONAL,
            inspect.Parameter.VAR_KEYWORD,
        ):
            continue

        entry: dict = {"required": True}
        hint = annotations.get(param_name)
        if hint is not None:
            entry["type"] = _type_name(hint) or "any"

        if param.default is not inspect.Parameter.empty:
            entry["required"] = False
            if entry.get("type") is None:
                if isinstance(param.default, bool):
                    entry["type"] = "boolean"
                elif isinstance(param.default, int):
                    entry["type"] = "integer"
                elif isinstance(param.default, str):
                    entry["type"] = "string"
                else:
                    entry["type"] = "null_or_any"

        schema[param_name] = entry

    return schema


def tool_prompt(tools):
    if not tools:
        return ""

    definitions = []

    for tool in tools:
        entry = {
            "name": tool["name"],
            "description": tool["description"],
        }
        arguments = tool.get("arguments")
        if arguments:
            entry["arguments"] = arguments
        definitions.append(entry)

    return (
        "\n\nAVAILABLE TOOLS:\n"
        + json.dumps(definitions, indent=2)
        + """

When you need a tool, respond with ONLY:

<tool_call>
{"name":"TOOL_NAME","arguments":{"key":"value"}}
</tool_call>

Rules:
- Use exactly the argument names shown for the tool, with the correct types
  (string / integer / boolean). Do not invent extra keys.
- Provide every required argument; omit optional ones instead of passing null.
- Emit one complete, well-formed JSON object. Do not split it across turns.
- After receiving the tool result, continue reasoning or call the next tool.

When no more tools are needed, respond normally.
"""
    )


def parse_tool_call(text):
    start = text.find("<tool_call>")
    end = text.find("</tool_call>")

    if start == -1 or end == -1 or end < start:
        return None

    payload = text[start + len("<tool_call>"):end].strip()

    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return None

    if not isinstance(data, dict):
        return None

    name = data.get("name")
    arguments = data.get("arguments", {})

    if not isinstance(name, str):
        return None

    if not isinstance(arguments, dict):
        return None

    return {
        "name": name,
        "arguments": arguments,
    }


def partial_tool_call(text):
    """True when the model opened a tool call but never closed it.

    Usually means JSON was cut off by the token cap; the caller can ask the
    model to finish the call instead of silently dropping it.
    """
    start = text.find("<tool_call>")
    return start != -1 and text.find("</tool_call>") < start


def tool_result(name, result):
    return (
        f"\n\n<tool_result name=\"{name}\">\n"
        f"{result}\n"
        "</tool_result>\n"
    )
