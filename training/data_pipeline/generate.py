"""Provider-agnostic teacher interface and synthetic candidate generation.

The pipeline does not require a teacher: it works entirely from candidate
files. When a teacher is connected it must expose a small `generate` method;
any of Penthos' own inference backends (or a free/open model) can implement
that interface later. Generated examples are always labeled as synthetic and
carry a `source.teacher` provenance. Synthetic examples are never labeled as
human-authored.
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

from training.data_pipeline import verify


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Teacher(Protocol):
    """Interface a provider must implement.

        class MyTeacher:
            name = "provider-model"

            def generate(self, task: str) -> dict:
                ...
    """

    name: str

    def generate(self, task: str) -> dict: ...


def generate_candidates(
    teacher: Teacher,
    tasks: list[str],
    output_path: str | Path | None = None,
) -> list[dict]:
    """Generate synthetic candidates from tasks and stamp provenance.

    Provenance is always:

        source.type = "synthetic"
        source.teacher = <teacher.name>
        source.generated_at = <timestamp>
    """

    candidates = []
    for task in tasks:
        candidate = teacher.generate(task)
        if not isinstance(candidate, dict):
            raise ValueError(
                f"Teacher {teacher.name!r} returned a non-dict from "
                f"{task!r}: {candidate!r}"
            )
        candidate["source"] = {
            "type": "synthetic",
            "teacher": teacher.name,
            "generated_at": utcnow(),
        }
        candidates.append(candidate)

    if output_path is not None:
        target = Path(output_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, "w", encoding="utf-8") as handle:
            for candidate in candidates:
                handle.write(json.dumps(candidate, ensure_ascii=False) + "\n")

    return candidates


class StubTeacher:
    """A no-op teacher for tests and dry runs.

    It emits plain reasoning-style candidates and never calls a paid
    provider or opens a network connection.
    """

    name = "stub"

    def __init__(self, category: str = "reasoning", difficulty: str = "easy", language: str = ""):
        self.category = category
        self.difficulty = difficulty
        self.language = language
        self._counter = 0

    def generate(self, task: str) -> dict:
        self._counter += 1
        return {
            "id": f"stub-synthetic-{self._counter:05d}",
            "instruction": task,
            "category": self.category,
            "difficulty": self.difficulty,
            "language": self.language,
            "expected_answer": f"Baseline stub answer for: {task}",
            "metadata": {"license": "MIT", "notes": "Stub teacher output; not fit for training."},
        }


__all__ = [
    "Teacher",
    "StubTeacher",
    "generate_candidates",
    "utcnow",
]