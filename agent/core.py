"""Penthos lightweight agent core."""

from agent.tools import Tool, ToolRegistry
from agent.memory import Memory
from tools.filesystem import ProjectFilesystem
from tools.web import fetch_url, search_web


SYSTEM_PROMPT = """You are Penthos, an open-source coding AI.

You are optimized for:
- software engineering
- debugging
- repository understanding
- reasoning
- agentic coding
- security
- efficient problem solving

Respond naturally. Do not force headings, numbered lists,
JSON, or rigid formatting unless they genuinely improve the answer.

When tools are available, use them when they provide information
you cannot reliably know from the conversation.

Never claim that you used a tool when you did not.

Prefer inspecting existing code over inventing or rewriting an
entire project.

Verify code changes whenever possible.
"""


class PenthosAgent:
    def __init__(self, project_root="."):
        self.memory = Memory()
        self.filesystem = ProjectFilesystem(project_root)
        self.tools = ToolRegistry()

        self._register_tools()

    def _register_tools(self):
        self.tools.register(
            Tool(
                name="list_files",
                description="List files inside the current project.",
                function=self.filesystem.list_files,
            )
        )

        self.tools.register(
            Tool(
                name="read_file",
                description="Read a text file inside the current project.",
                function=self.filesystem.read_file,
            )
        )

        self.tools.register(
            Tool(
                name="write_file",
                description="Write a text file inside the current project.",
                function=self.filesystem.write_file,
            )
        )

        self.tools.register(
            Tool(
                name="web_search",
                description="Search the public web for information.",
                function=search_web,
            )
        )

        self.tools.register(
            Tool(
                name="web_fetch",
                description="Fetch and extract readable text from a URL.",
                function=fetch_url,
            )
        )

    def tool_descriptions(self):
        return [
            {
                "name": tool.name,
                "description": tool.description,
            }
            for tool in self.tools.list()
        ]

    def execute_tool(self, name, **kwargs):
        return self.tools.execute(name, **kwargs)
