"""Lightweight persistent memory for Penthos."""

import json
from pathlib import Path
from datetime import datetime, timezone


class Memory:
    def __init__(self, root="memory"):
        self.root = Path(root)
        self.conversation = self.root / "conversation"
        self.project = self.root / "project"
        self.long_term = self.root / "long_term"

        for directory in (
            self.conversation,
            self.project,
            self.long_term,
        ):
            directory.mkdir(parents=True, exist_ok=True)

    def _write(self, directory: Path, name: str, data):
        path = directory / name
        path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return path

    def _read(self, directory: Path, name: str, default=None):
        path = directory / name

        if not path.exists():
            return default

        return json.loads(path.read_text(encoding="utf-8"))

    def save_conversation(self, messages):
        return self._write(
            self.conversation,
            "current.json",
            {
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "messages": messages,
            },
        )

    def load_conversation(self):
        return self._read(
            self.conversation,
            "current.json",
            {"messages": []},
        )

    def save_project(self, key: str, value):
        return self._write(
            self.project,
            f"{key}.json",
            {
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "value": value,
            },
        )

    def load_project(self, key: str, default=None):
        return self._read(
            self.project,
            f"{key}.json",
            default,
        )

    def save_long_term(self, key: str, value):
        return self._write(
            self.long_term,
            f"{key}.json",
            {
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "value": value,
            },
        )

    def load_long_term(self, key: str, default=None):
        return self._read(
            self.long_term,
            f"{key}.json",
            default,
        )
