"""Penthos Agent Core."""

from agent.tools import Tool, ToolRegistry
from agent.memory import Memory
from agent.repository import RepositoryIntelligence

from tools.filesystem import ProjectFilesystem
from tools.web import fetch_url, search_web
from tools.shell import Shell
from tools.code_search import CodeSearch
from tools.git import GitTools
from sandbox import tool as sandbox_tool


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

You have tools for projects, shell commands, code search, Git,
web research, repository intelligence, and isolated sandboxed test
execution.

Before making significant coding decisions, inspect the relevant
existing project context.

Use repository intelligence to avoid repeatedly scanning files
that have not changed.

For coding tasks:
1. Understand the request.
2. Inspect relevant existing code.
3. Identify the smallest correct change.
4. Implement it.
5. Run relevant verification.
6. Diagnose failures.
7. Fix them.
8. Verify again.

When verifying generated code or tests, prefer the `run_tests` tool, which
executes inside a disposable, network-isolated Docker sandbox with resource
limits and no access to host secrets. Do not run generated code directly on
the host machine.

Do not claim that a tool was used unless it actually returned a result.

Do not unnecessarily rewrite projects.

Respond naturally. Do not force headings, numbered lists, JSON,
or rigid formatting unless they genuinely improve the answer.

Never expose secrets, credentials, private keys, API keys, or
sensitive environment variables.
"""


class PenthosAgent:
    def __init__(self, project_root="."):
        self.memory = Memory()
        self.repository = RepositoryIntelligence(project_root)
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

        self.tools.register(
            Tool(
                name="index_repository",
                description="Index the current repository for efficient future inspection.",
                function=self.repository.index_repository,
            )
        )

        self.tools.register(
            Tool(
                name="project_context",
                description="Return compact information about the current repository.",
                function=self.repository.project_context,
            )
        )

        self.tools.register(
            Tool(
                name="changed_files",
                description="Find files that changed since the previous repository index.",
                function=self.repository.changed_files,
            )
        )

        self.tools.register(
            Tool(
                name="search_memory",
                description="Search Penthos persistent project and conversation memory.",
                function=self.repository.search_memory,
            )
        )

        self.tools.register(
            Tool(
                name="run_tests",
                description=(
                    "Run generated code/tests inside an isolated, disposable "
                    "Docker sandbox. Accepts: language (python, node, or "
                    "typescript), files ({filename: contents}), and command "
                    "(entrypoint argv, e.g. ['python', '-m', 'pytest', '-q']). "
                    "The sandbox has no network access, host secrets, or host "
                    "filesystem, and the container is removed after each run."
                ),
                function=sandbox_tool.run_tests,
                requires_confirmation=True,
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
