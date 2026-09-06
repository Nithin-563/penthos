"""Read-only Git inspection tools for Penthos."""

import subprocess
from pathlib import Path


MAX_OUTPUT = 12000


class GitTools:
    def __init__(self, root="."):
        self.root = Path(root).resolve()

    def _run(self, args):
        result = subprocess.run(
            ["git", *args],
            cwd=self.root,
            capture_output=True,
            text=True,
            timeout=20,
        )

        return result.stdout[-MAX_OUTPUT:]

    def status(self):
        return self._run(["status", "--short"])

    def diff(self):
        return self._run(["diff"])

    def log(self):
        return self._run(
            ["log", "--oneline", "-20"]
        )
