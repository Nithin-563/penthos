"""Fast project code search."""

import subprocess
from pathlib import Path


MAX_OUTPUT = 12000


class CodeSearch:
    def __init__(self, root="."):
        self.root = Path(root).resolve()

    def search(self, pattern: str):
        if not pattern.strip():
            raise ValueError("Search pattern cannot be empty")

        result = subprocess.run(
            [
                "grep",
                "-RIn",
                "--exclude-dir=.git",
                "--exclude-dir=node_modules",
                "--exclude-dir=.venv",
                "--exclude-dir=__pycache__",
                pattern,
                ".",
            ],
            cwd=self.root,
            capture_output=True,
            text=True,
            timeout=20,
        )

        return {
            "matches": result.stdout[-MAX_OUTPUT:],
            "exit_code": result.returncode,
        }
