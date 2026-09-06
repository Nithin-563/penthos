"""Verification helpers for coding tasks."""

from dataclasses import dataclass


@dataclass
class VerificationResult:
    success: bool
    exit_code: int
    stdout: str
    stderr: str

    @classmethod
    def from_tool_result(cls, result):
        return cls(
            success=bool(result.get("success")),
            exit_code=int(result.get("exit_code", -1)),
            stdout=result.get("stdout", ""),
            stderr=result.get("stderr", ""),
        )

    def summary(self):
        if self.success:
            return "Verification passed."

        return (
            "Verification failed.\n"
            f"Exit code: {self.exit_code}\n"
            f"STDOUT:\n{self.stdout}\n"
            f"STDERR:\n{self.stderr}"
        )
