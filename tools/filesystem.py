"""Safe project filesystem tools."""

from pathlib import Path


class ProjectFilesystem:
    def __init__(self, root="."):
        self.root = Path(root).resolve()

    def _safe(self, path: str) -> Path:
        target = (self.root / path).resolve()

        if target != self.root and self.root not in target.parents:
            raise PermissionError("Path escapes Penthos project directory")

        return target

    def list_files(self, path="."):
        directory = self._safe(path)

        if not directory.is_dir():
            raise ValueError("Not a directory")

        return [
            str(p.relative_to(self.root))
            for p in directory.rglob("*")
            if p.is_file()
        ]

    def read_file(self, path: str):
        return self._safe(path).read_text(encoding="utf-8")

    def read_readme(self):
        candidates = ["README.md", "README.rst", "README.txt", "ReadMe.md", "README", "readme.md"]
        for name in candidates:
            target = self.root / name
            if target.is_file():
                try:
                    return (
                        f"# PROJECT README ({name})\n"
                        + target.read_text(encoding="utf-8")[:20000]
                    )
                except OSError:
                    continue
        return "No README file found in the project root."

    def write_file(self, path: str, content: str):
        target = self._safe(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return str(target.relative_to(self.root))
