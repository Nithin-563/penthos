"""Tool registry for Penthos."""

import inspect
from dataclasses import dataclass
from typing import Callable, Any


@dataclass
class Tool:
    name: str
    description: str
    function: Callable[..., Any]
    requires_confirmation: bool = False


class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool):
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def list(self) -> list[Tool]:
        return list(self._tools.values())

    def execute(self, name: str, **kwargs):
        tool = self.get(name)

        if tool is None:
            raise ValueError(
                f"Unknown tool: {name}. "
                f"Available tools: {', '.join(sorted(self._tools))}."
            )

        return tool.function(**kwargs)


def validate_arguments(tool: Tool, **kwargs) -> tuple[list[str], list[str]]:
    """Sanity-check tool arguments against the tool's signature.

    Returns (unknown_keys, missing_keys). Wrong argument names are the most
    common cause of silent tool failures, so validate before calling so the
    error message can tell the model exactly what to fix instead of leaving a
    confusing TypeError.
    """
    unknown: list[str] = []
    missing: list[str] = []

    try:
        signature = inspect.signature(tool.function)
    except (TypeError, ValueError):
        return unknown, missing

    params = signature.parameters
    accepts_kwargs = any(
        param.kind == inspect.Parameter.VAR_KEYWORD
        for param in params.values()
    )

    if not accepts_kwargs:
        unknown = [key for key in kwargs if key not in params]

    missing = [
        param_name
        for param_name, param in params.items()
        if param.default is inspect.Parameter.empty
        and param.kind == inspect.Parameter.POSITIONAL_OR_KEYWORD
        and param_name not in kwargs
    ]
    return unknown, missing
