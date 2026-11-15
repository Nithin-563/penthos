"""Pari Agent Core."""

from agent.tools import Tool, ToolRegistry
from agent.memory import Memory
from agent.repository import RepositoryIntelligence
from agent.protocol import arg_schema
from inference.prompt import PARI_SYSTEM_PROMPT as SYSTEM_PROMPT

from tools.filesystem import ProjectFilesystem
from tools.web import fetch_url, search_web
from tools.shell import Shell
from tools.code_search import CodeSearch
from tools.git import GitTools
from sandbox import tool as sandbox_tool


class PariAgent:
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
                name="read_readme",
                description=(
                    "Return the project README so you understand the repo's "
                    "purpose, conventions, and build commands before editing."
                ),
                function=self.filesystem.read_readme,
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
                description=(
                    "Search project source code for a pattern. "
                    "Pass language (python, js, typescript, go, rust, java, c, "
                    "cpp, ruby, php, html, css, shell, sql, json, yaml, "
                    "markdown) to restrict the search, and definitions=True to "
                    "only find function/class definition lines."
                ),
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
                description="Search Pari persistent project and conversation memory.",
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
                "arguments": arg_schema(tool.function),
            }
            for tool in self.tools.list()
        ]

    def execute_tool(self, name, **kwargs):
        return self.tools.execute(name, **kwargs)
