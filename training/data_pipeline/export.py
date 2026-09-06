"""Schema-compatible record building, split assignment, JSONL export,
and dataset manifest generation."""

import json
from datetime import datetime, timezone
from pathlib import Path

from training.data_pipeline import verify

SCHEMA_VERSION = "1.1.0"
DATASET_VERSION = "1.0.0"


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def build_record(
    candidate: dict,
    verification: dict | None = None,
    fingerprint: str | None = None,
    split: str | None = None,
) -> dict:
    """Build a datasets/schema.json-compatible training record.

    The candidate's `instruction` maps to the schema's `prompt` and
    `expected_answer` maps to `solution`. All original schema fields are
    preserved; new optional fields pass through unchanged.
    """

    record = {
        "id": candidate.get("id") or (
            f"penthos-{fingerprint[:16]}" if fingerprint else verify.utcnow()
        ),
        "category": candidate.get("category", ""),
        "difficulty": candidate.get("difficulty", ""),
        "language": candidate.get("language", ""),
        "prompt": candidate.get("instruction", ""),
    }

    for key in ("context", "solution", "code", "files", "tests", "test_command"):
        if key in candidate and candidate[key]:
            record[key] = candidate[key]

    if "solution" not in record and candidate.get("expected_answer"):
        record["solution"] = candidate["expected_answer"]

    record["verification"] = verification or verify.not_required_verification()

    metadata = dict(candidate.get("metadata") or {})
    source = candidate.get("source") or {}
    metadata["source"] = source.get("type") or metadata.get("source") or verify.SCHEMA_SOURCE_DEFAULT
    metadata.setdefault(
        "created_at",
        source.get("generated_at") or metadata.get("generated_at") or utcnow(),
    )
    if source.get("teacher") or source.get("provenance") or source.get("type") == "synthetic":
        metadata["provenance"] = source
    if fingerprint:
        metadata["fingerprint"] = fingerprint

    record["metadata"] = metadata

    if split:
        record["split"] = split

    return record


# ---------------------------------------------------------------------------
# JSONL I/O
# ---------------------------------------------------------------------------

def read_jsonl(path: str | Path) -> list[dict]:
    records = []
    with open(path, "r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_no} is not valid JSON: {exc}") from exc
    return records


def write_jsonl(path: str | Path, records: list[dict]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, "w", encoding="utf-8") as handle:
        for record in records:
            handle.write(_json_line(record) + "\n")


def _json_line(record: dict) -> str:
    return json.dumps(record, ensure_ascii=False, sort_keys=False)


# ---------------------------------------------------------------------------
# Manifests
# ---------------------------------------------------------------------------

def build_manifest(
    report: dict,
    splits: dict[str, list[dict]],
) -> dict:
    """Build the dataset manifest from pipeline counts."""

    verified_records = []
    for split_records in splits.values():
        verified_records.extend(split_records)

    fingerprints = []
    for record in verified_records:
        fingerprint = record.get("metadata", {}).get("fingerprint")
        if fingerprint:
            fingerprints.append(fingerprint)

    leakage = {
        "passed": len(fingerprints) == len(set(fingerprints)),
        "distinct_fingerprints": len(set(fingerprints)),
        "total_fingerprints": len(fingerprints),
    }

    return {
        "dataset_version": report.get("dataset_version", DATASET_VERSION),
        "pipeline_version": report.get("pipeline_version", "unknown"),
        "schema_version": report.get("schema_version", SCHEMA_VERSION),
        "generated_at": report.get("generated_at", utcnow()),
        "total_candidates": report.get("total_candidates", 0),
        "malformed_count": report.get("malformed_count", 0),
        "unsafe_count": report.get("unsafe_count", 0),
        "verified_count": report.get("verified_count", 0),
        "rejected_count": report.get("rejected_count", 0),
        "duplicate_count": report.get("duplicate_count", 0),
        "counts_by_category": report.get("counts_by_category", {}),
        "counts_by_language": report.get("counts_by_language", {}),
        "counts_by_difficulty": report.get("counts_by_difficulty", {}),
        "counts_by_split": report.get("counts_by_split", {}),
        "rejection_reasons": report.get("rejection_reasons", {}),
        "verification_statistics": report.get("verification_statistics", {}),
        "split_leakage_check": leakage,
    }


def write_manifest(target_dir: str | Path, manifest: dict) -> str:
    directory = Path(target_dir)
    directory.mkdir(parents=True, exist_ok=True)
    stamp = manifest.get("generated_at", utcnow()).replace(":", "-")
    path = directory / f"manifest_v{manifest['dataset_version']}_{stamp}.json"
    path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    latest = directory / "manifest_latest.json"
    latest.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return str(path)