"""Penthos Agent Core."""

from agent.tools import Tool, ToolRegistry
from agent.memory import Memory
from tools.filesystem import ProjectFilesystem
from tools.web import fetch_url, search_web
from tools.shell import Shell
from tools.code_search import CodeSearch
from tools.git import GitTools


SYSTEM_PROMPT = """You are Penthos, an open-source coding AI.

Your goal is to solve software engineering problems with the
smallest amount of unnecessary work.

Core strengths:
- coding
- debugging
- repository understanding
- reasoning
- architecture
- security
- performance
- agentic software engineering

You have tools for inspecting and modifying projects, executing
commands, searching code, inspecting Git, and researching the web.

Use tools when they provide information you cannot reliably know.

For coding tasks:
1. Inspect relevant existing code.
2. Understand the root cause or requirement.
3. Make the smallest correct change.
4. Run relevant verification.
5. If verification fails, diagnose and fix it.
6. Verify again.
7. Report what actually happened.

Do not claim that a command, test, search, or file operation happened
unless the corresponding tool actually returned a result.

Do not unnecessarily rewrite projects.

Respond naturally. Do not force headings, JSON, numbered lists,
or rigid structures unless they genuinely improve the answer.

Never expose secrets, credentials, private keys, or environment
variables containing sensitive values.
"""


class PenthosAgent:
    def __init__(self, project_root="."):
        self.memory = Memory()
        self.filesystem = ProjectFilesystem(project_root)
        self.shell = Shell(project_root)
        self.code_search = CodeSearch(project_root)
        self.git = GitTools(project_root)

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
                requires_confirmation=True,
            )
        )

        self.tools.register(
            Tool(
                name="shell_exec",
                description="Run a shell command inside the project workspace.",
                function=self.shell.run,
                requires_confirmation=True,
            )
        )

        self.tools.register(
            Tool(
                name="search_code",
                description="Search project source code for a pattern.",
                function=self.code_search.search,
            )
        )

        self.tools.register(
            Tool(
                name="git_status",
                description="Show current Git working tree status.",
                function=self.git.status,
            )
        )

        self.tools.register(
            Tool(
                name="git_diff",
                description="Show current uncommitted Git changes.",
                function=self.git.diff,
            )
        )

        self.tools.register(
            Tool(
                name="git_log",
                description="Show recent Git commits.",
                function=self.git.log,
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
                description="Fetch readable text from a public URL.",
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
