"""Sandboxed shell execution for Penthos."""

import subprocess
from pathlib import Path


DEFAULT_TIMEOUT = 30
MAX_OUTPUT = 12000


class Shell:
    def __init__(self, root="."):
        self.root = Path(root).resolve()

    def run(self, command: str, timeout: int = DEFAULT_TIMEOUT):
        if not command.strip():
            raise ValueError("Command cannot be empty")

        try:
            timeout = min(int(timeout), 120)
        except (TypeError, ValueError):
            timeout = DEFAULT_TIMEOUT

        result = subprocess.run(
            command,
            shell=True,
            cwd=self.root,
            capture_output=True,
            text=True,
            timeout=timeout,
            env={
                "PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin",
                "HOME": str(self.root),
            },
        )

        stdout = result.stdout[-MAX_OUTPUT:]
        stderr = result.stderr[-MAX_OUTPUT:]

        return {
            "exit_code": result.returncode,
            "stdout": stdout,
            "stderr": stderr,
            "success": result.returncode == 0,
        }
