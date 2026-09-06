"""Penthos permission and command safety layer."""

import shlex


BLOCKED_COMMANDS = {
    "rm",
    "rmdir",
    "shutdown",
    "reboot",
    "mkfs",
    "diskutil",
    "sudo",
    "passwd",
    "chown",
    "chmod",
}


BLOCKED_PATTERNS = [
    "/",
    "~/.ssh",
    "~/.aws",
    "~/.config",
    ".env",
    "id_rsa",
    "private_key",
]


class PermissionManager:
    def inspect_command(self, command: str):
        if not command.strip():
            return False, "Empty command"

        try:
            tokens = shlex.split(command)
        except ValueError:
            return False, "Invalid shell syntax"

        if not tokens:
            return False, "Empty command"

        executable = tokens[0].split("/")[-1]

        if executable in BLOCKED_COMMANDS:
            return False, f"Blocked command: {executable}"

        lowered = command.lower()

        for pattern in BLOCKED_PATTERNS:
            if pattern.lower() in lowered:
                return False, f"Blocked sensitive path/pattern: {pattern}"

        return True, "Allowed"

    def require_confirmation(self, command: str):
        allowed, reason = self.inspect_command(command)

        if not allowed:
            return {
                "allowed": False,
                "requires_confirmation": False,
                "reason": reason,
            }

        return {
            "allowed": True,
            "requires_confirmation": True,
            "reason": "Command requires confirmation.",
        }
