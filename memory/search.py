"""Simple low-compute memory and repository search."""

from pathlib import Path
import json


class MemorySearch:
    def __init__(self, root="memory"):
        self.root = Path(root)

    def search(self, query, limit=8):
        query_terms = {
            term.lower()
            for term in query.split()
            if len(term) > 2
        }

        results = []

        if not self.root.exists():
            return results

        for path in self.root.rglob("*.json"):
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue

            lowered = text.lower()
            score = sum(
                lowered.count(term)
                for term in query_terms
            )

            if score:
                results.append({
                    "file": str(path),
                    "score": score,
                    "content": text[:8000],
                })

        results.sort(
            key=lambda item: item["score"],
            reverse=True,
        )

        return results[:limit]
