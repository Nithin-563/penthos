"""Penthos tool-calling protocol."""

import json


def tool_prompt(tools):
    if not tools:
        return ""

    definitions = []

    for tool in tools:
        definitions.append({
            "name": tool["name"],
            "description": tool["description"],
        })

    return (
        "\n\nAVAILABLE TOOLS:\n"
        + json.dumps(definitions, indent=2)
        + """
        
When you need a tool, respond with ONLY:

<tool_call>
{"name":"TOOL_NAME","arguments":{"key":"value"}}
</tool_call>

After receiving the tool result, continue reasoning.

When no more tools are needed, respond normally.
"""
    )


def parse_tool_call(text):
    start = text.find("<tool_call>")
    end = text.find("</tool_call>")

    if start == -1 or end == -1:
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


def tool_result(name, result):
    return (
        f"\n\n<tool_result name=\"{name}\">\n"
        f"{result}\n"
        "</tool_result>\n"
    )
