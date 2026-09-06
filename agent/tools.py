"""Tool registry for Penthos."""

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
            raise ValueError(f"Unknown tool: {name}")

        return tool.function(**kwargs)
