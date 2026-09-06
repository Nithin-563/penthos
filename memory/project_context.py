"""Compact repository context builder."""

from pathlib import Path
import json


class ProjectContext:
    def __init__(self, root="."):
        self.root = Path(root).resolve()

    def build(self, max_files=20, max_chars=30000):
        index_file = self.root / "memory" / "index" / "repository.json"

        if not index_file.exists():
            return "Repository index not built yet."

        data = json.loads(
            index_file.read_text(encoding="utf-8")
        )

        important = [
            item["path"]
            for item in data.get("files", [])
            if item.get("important")
        ]

        selected = important[:max_files]

        output = [
            "PENTHOS PROJECT CONTEXT",
            f"Files indexed: {data.get('file_count', 0)}",
            "",
            "Important files:",
        ]

        for path in selected:
            output.append(f"- {path}")

        output.append("")
        output.append("Repository files:")

        for item in data.get("files", [])[:max_files]:
            output.append(f"- {item['path']}")

        text = "\n".join(output)

        return text[:max_chars]
