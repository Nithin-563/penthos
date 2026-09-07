"""Fast project code search."""

import subprocess
from pathlib import Path


MAX_OUTPUT = 12000

# File extensions per language for targeted searches.
EXTENSIONS = {
    "python": ("*.py", ".pyi"),
    "js": ("*.js", ".jsx", ".mjs"),
    "typescript": ("*.ts", ".tsx"),
    "go": ("*.go",),
    "rust": ("*.rs",),
    "java": ("*.java",),
    "c": ("*.c", "*.h"),
    "cpp": ("*.cpp", "*.cc", "*.hpp", "*.h"),
    "ruby": ("*.rb",),
    "php": ("*.php",),
    "html": ("*.html", "*.htm"),
    "css": ("*.css", "*.scss"),
    "sql": ("*.sql",),
    "shell": ("*.sh", ".bash"),
    "json": ("*.json",),
    "yaml": ("*.yaml", "*.yml"),
    "docker": ("Dockerfile*",),
    "markdown": ("*.md",),
}

# Definition patterns — lets the agent find where things are DEFINED, not just
# mentioned, which is the highest-value search for a coding agent.
DEFINITION_PATTERNS = {
    "python": r"^(class |def |async def )[A-Za-z_]",
    "typescript": r"^(export |function |class |const ).*=>",
    "js": r"^(export |function |class )",
    "go": r"^func ",
    "rust": r"^fn ",
    "java": r"^(public |private |protected )",
    "c": r"^(int|void|char|float|double|size_t|bool|uint|long|struct|static) ",
    "cpp": r"^(int|void|char|float|double|size_t|bool|uint|long|struct|class|static) ",
}


class CodeSearch:
    def __init__(self, root="."):
        self.root = Path(root).resolve()

    def _build_command(self, pattern: str, language: str | None, definitions: bool) -> list[str]:
        exclusions = [
            "--exclude-dir=.git",
            "--exclude-dir=node_modules",
            "--exclude-dir=.venv",
            "--exclude-dir=venv",
            "--exclude-dir=__pycache__",
            "--exclude-dir=.next",
            "--exclude-dir=dist",
            "--exclude-dir=build",
            "--exclude-dir=.cache",
            "--exclude-dir=.pytest_cache",
        ]

        cmd = ["grep", "-RIn"] + exclusions

        if definitions:
            # Match definition lines only — anchored with -E for regex.
            cmd += ["-E"]
            pattern = pattern
        if language and language in EXTENSIONS:
            # Filter to the requested language's extensions.
            for ext in EXTENSIONS[language]:
                cmd += ["--include", ext if ext.startswith("*.") else f"*{ext}"]

        cmd += [pattern, "."]

        return cmd

    def search(
        self,
        pattern: str,
        language: str | None = None,
        definitions: bool = False,
    ):
        """Search project source code.

        - pattern (str, required): the text or regex to search for.
        - language (str, optional): restrict to one language — python, js,
          typescript, go, rust, java, c, cpp, ruby, php, html, css, shell,
          json, yaml, markdown.
        - definitions (bool, optional, default false): only return lines that
          look like function/class definitions, so the agent can find where
          symbols are defined instead of every mention.
        """
        if not pattern.strip():
            raise ValueError("Search pattern cannot be empty")

        if language:
            language = language.strip().lower()

        search_pattern = pattern
        if definitions:
            base = DEFINITION_PATTERNS.get(language or "", "")
            if base:
                search_pattern = rf"{base}.*{pattern}"

        result = subprocess.run(
            self._build_command(search_pattern, language, definitions),
            cwd=self.root,
            capture_output=True,
            text=True,
            timeout=20,
        )

        return {
            "matches": result.stdout[-MAX_OUTPUT:],
            "exit_code": result.returncode,
            "language": language or "all",
            "definitions_only": definitions,
        }
