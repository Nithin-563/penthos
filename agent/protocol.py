"""Penthos tool-calling protocol."""

import inspect
import json
import re


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
- Wrap the JSON in <tool_call> ... </tool_call> tags. Do NOT use markdown
  fences, raw JSON, or OpenAI-style bare objects.
- After receiving the tool result, continue reasoning or call the next tool.

When no more tools are needed, respond normally. For greetings, chit-chat, or
clarifying questions, reply in plain text — do NOT emit a tool call.
"""
    )


_END_MARKERS = ("<|im_end|>", "<|tool_call|>", "<|assistant|>")

# Tokenizers from different model families end turns / tool turns with these
# markers. Stripping them lets the tool parser see the JSON object cleanly
# even when the base used its own chat template instead of our <tool_call> tags.
def _strip_end_markers(text: str) -> str:
    for marker in _END_MARKERS:
        text = text.replace(marker, " ")
    return text.strip()


def _find_json_object(text: str):
    """Return the first balanced {...} region in ``text``, or None."""
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    in_string = False
    escaped = False
    for i in range(start, len(text)):
        char = text[i]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None


def _repair_arguments_colon(payload: str) -> str:
    """Repair the common Qwen tokenizer slip ``"arguments:{...}"`` (the colon
    landed inside the quoted key) back into a valid ``"arguments":{...}`` field."""
    repaired = re.sub(
        r'"arguments\s*:\s*(\{.*?\})\s*"',
        r'"arguments":\1',
        payload,
        flags=re.DOTALL,
    )
    return repaired


def _json_payloads(text: str):
    """Yield the candidate JSON payloads to try, in priority order.

    1. The body between explicit <tool_call> ... </tool_call> tags.
    2. The first balanced {...} object anywhere in the text (tolerates bare
       JSON, ```json fences, and trailing end-turn markers like <|im_end|>).
    """
    start = text.find("<tool_call>")
    end = text.find("</tool_call>")
    if start != -1 and end != -1 and end > start:
        yield text[start + len("<tool_call>") : end].strip()

    bare = _find_json_object(_strip_end_markers(text))
    if bare:
        yield bare


def parse_tool_call(text):
    for payload in _json_payloads(text):
        for candidate in (payload, _repair_arguments_colon(payload)):
            try:
                data = json.loads(candidate)
            except (json.JSONDecodeError, TypeError):
                continue

            if not isinstance(data, dict):
                continue
            name = data.get("name")
            if not isinstance(name, str) or not name:
                continue

            arguments = data.get("arguments", {})
            # Some bases emit "arguments": null when they meant {}.
            if arguments is None:
                arguments = {}
            if not isinstance(arguments, dict):
                continue

            return {"name": name, "arguments": arguments}
    return None


def looks_like_tool_call(text) -> bool:
    """True when the output reads like a tool-call attempt, even a malformed one.

    Used to decide whether a failed parse should be fed back to the model for a
    retry instead of surfacing raw JSON junk as if it were the final answer.
    """
    stripped = _strip_end_markers(text).strip()
    if not stripped:
        return False
    if re.search(r'"name"\s*:', stripped) is None:
        return False
    return re.search(r'"arguments', stripped) is not None or stripped.startswith("{")


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
