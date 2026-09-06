"""Lightweight repository intelligence for Penthos."""

from pathlib import Path
import hashlib
import json
from datetime import datetime, timezone


IGNORED = {
    ".git",
    "node_modules",
    ".venv",
    "venv",
    "__pycache__",
    ".next",
    "dist",
    "build",
    ".cache",
    ".pytest_cache",
}


IMPORTANT_FILES = {
    "package.json",
    "pyproject.toml",
    "requirements.txt",
    "Cargo.toml",
    "go.mod",
    "README.md",
    "README",
    "Dockerfile",
    "docker-compose.yml",
    "docker-compose.yaml",
    "tsconfig.json",
    "vite.config.ts",
    "vite.config.js",
    "next.config.js",
    "next.config.ts",
}


class ProjectIndex:
    def __init__(self, root="."):
        self.root = Path(root).resolve()
        self.index_dir = self.root / "memory" / "index"
        self.index_dir.mkdir(parents=True, exist_ok=True)
        self.index_file = self.index_dir / "repository.json"

    def _ignored(self, path: Path):
        return any(part in IGNORED for part in path.parts)

    def _hash(self, path: Path):
        digest = hashlib.sha256()

        try:
            with path.open("rb") as f:
                for chunk in iter(lambda: f.read(1024 * 1024), b""):
                    digest.update(chunk)
        except (OSError, PermissionError):
            return None

        return digest.hexdigest()

    def scan(self):
        files = []

        for path in self.root.rglob("*"):
            if not path.is_file():
                continue

            if self._ignored(path):
                continue

            try:
                relative = path.relative_to(self.root)
                stat = path.stat()
            except OSError:
                continue

            files.append({
                "path": str(relative),
                "size": stat.st_size,
                "extension": path.suffix.lower(),
                "hash": self._hash(path),
                "important": path.name in IMPORTANT_FILES,
            })

        files.sort(key=lambda x: x["path"])

        result = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "root": str(self.root),
            "file_count": len(files),
            "files": files,
        }

        self.index_file.write_text(
            json.dumps(result, indent=2),
            encoding="utf-8",
        )

        return result

    def load(self):
        if not self.index_file.exists():
            return self.scan()

        return json.loads(
            self.index_file.read_text(encoding="utf-8")
        )

    def changed_files(self):
        old = self.load()
        old_map = {
            item["path"]: item["hash"]
            for item in old.get("files", [])
        }

        current = self.scan()
        current_map = {
            item["path"]: item["hash"]
            for item in current.get("files", [])
        }

        changed = []

        for path, digest in current_map.items():
            if old_map.get(path) != digest:
                changed.append(path)

        for path in old_map:
            if path not in current_map:
                changed.append(path)

        return sorted(set(changed))

    def important_files(self):
        index = self.load()

        return [
            item["path"]
            for item in index.get("files", [])
            if item.get("important")
        ]
