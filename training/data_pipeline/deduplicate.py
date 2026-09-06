"""Deterministic deduplication and split assignment.

Normalization collapses incidental whitespace; the content fingerprint is a
SHA-256 of the normalized, schema-relevant fields. Timestamps, ids, and
provenance are deliberately excluded so identical examples hash identically
across runs and across synthetic regeneration.
"""

import hashlib
import json
import re
import unicodedata


_WS_RE = re.compile(r"\s+")


def normalize_prose(text: str) -> str:
    """Normalize prose for comparison: NFC, casefold, collapse whitespace."""

    if not isinstance(text, str):
        text = str(text)
    text = unicodedata.normalize("NFC", text)
    return _WS_RE.sub(" ", text).strip().casefold()


def normalize_code(text: str) -> str:
    """Normalize code for comparison: keep case, strip trailing whitespace,
    collapse blank-line runs. Identifier casing is significant."""

    if not isinstance(text, str):
        text = str(text)
    text = unicodedata.normalize("NFC", text.replace("\r\n", "\n"))
    lines = [line.rstrip() for line in text.split("\n")]
    collapsed = []
    blank_run = 0
    for line in lines:
        if not line.strip():
            blank_run += 1
            if blank_run > 1:
                continue
        else:
            blank_run = 0
        collapsed.append(line)
    return "\n".join(collapsed).strip()


def _normalized_json(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def content_fingerprint(candidate: dict) -> str:
    """SHA-256 fingerprint over normalized, schema-relevant fields."""

    if not isinstance(candidate, dict):
        raise ValueError("candidate must be a dict")

    content = {
        "category": candidate.get("category", ""),
        "difficulty": candidate.get("difficulty", ""),
        "language": candidate.get("language", ""),
        "instruction": normalize_prose(candidate.get("instruction", "")),
        "context": normalize_prose(candidate.get("context", "")),
        "expected_answer": normalize_prose(
            candidate.get("expected_answer", "")
        ),
        "code": normalize_code(candidate.get("code", "")),
        "files": {
            k: normalize_code(v)
            for k, v in sorted((candidate.get("files") or {}).items())
        },
        "tests": candidate.get("tests") or [],
        "test_command": candidate.get("test_command") or [],
    }

    canonical = _normalized_json(content)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def instruction_fingerprint(candidate: dict) -> str:
    """Secondary fingerprint used for conservative near-duplicate detection."""

    if not isinstance(candidate, dict):
        raise ValueError("candidate must be a dict")

    content = {
        "category": candidate.get("category", ""),
        "difficulty": candidate.get("difficulty", ""),
        "language": candidate.get("language", ""),
        "instruction": normalize_prose(candidate.get("instruction", "")),
    }
    canonical = _normalized_json(content)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def assign_split(fingerprint: str) -> str:
    """Deterministic split assignment (80/10/10).

    The same fingerprint always maps to the same split, so no example can
    appear in more than one split across runs.
    """

    bucket = _hash_int(f"split:{fingerprint}") % 100
    if bucket < 80:
        return "train"
    if bucket < 90:
        return "validation"
    return "test"


def _hash_int(value: str) -> int:
    return int(hashlib.sha256(value.encode("utf-8")).hexdigest(), 16)


def deduplicate(candidates: list[dict]) -> tuple[list[dict], list[dict]]:
    """Conservative deduplication.

    Returns (kept, duplicates). An example is a duplicate when its content
    fingerprint matches a kept example (exact) or its instruction fingerprint
    matches a kept example (near duplicate sharing the same normalized
    instruction). The first occurrence is kept; order is preserved.
    """

    kept: list[dict] = []
    duplicates: list[dict] = []

    seen_content: dict[str, str] = {}
    seen_instruction: dict[str, str] = {}

    for candidate in candidates:
        content_hash = content_fingerprint(candidate)
        instruction_hash = instruction_fingerprint(candidate)

        duplicate_of = None
        duplicate_type = None

        if content_hash in seen_content:
            duplicate_of = seen_content[content_hash]
            duplicate_type = "exact"
        elif instruction_hash in seen_instruction:
            duplicate_of = seen_instruction[instruction_hash]
            duplicate_type = "near_instruction"

        if duplicate_of is not None:
            duplicates.append(
                {
                    "candidate": candidate,
                    "duplicate_type": duplicate_type,
                    "duplicate_of": duplicate_of,
                    "fingerprint": content_hash,
                }
            )
            continue

        kept_id = candidate.get("id") or f"penthos-{content_hash[:16]}"
        seen_content[content_hash] = kept_id
        seen_instruction[instruction_hash] = kept_id

        kept.append(candidate)

    return kept, duplicates