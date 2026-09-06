"""End-to-end verified training data pipeline.

Flow:

    load candidates
      → validate            (reject malformed_record)
      → safety scan         (reject unsafe_candidate)
      → verify in sandbox   (reject on timeout / tests_failed /
                             execution_failed / invalid_command /
                             unsupported_language)
      → score               (reject low_quality)
      → deduplicate         (reject duplicate)
      → split + export      (verified JSONL by split)
      → manifest

Rejected records are written to datasets/rejected/<reason>.jsonl and never
enter datasets/verified/. Executable candidates are always verified with the
existing Penthos Docker sandbox; there is no host execution fallback.
"""

from dataclasses import dataclass, field
from pathlib import Path

from training.data_pipeline import (
    __version__ as PIPELINE_VERSION,
)
from training.data_pipeline import (
    deduplicate,
    export,
    score,
    verify,
)
from training.data_pipeline.deduplicate import assign_split, content_fingerprint
from training.data_pipeline.export import DATASET_VERSION, SCHEMA_VERSION

REPO_ROOT = Path(__file__).resolve().parents[2]

DEFAULT_CANDIDATE_DIRS = (
    "datasets/candidates",
    "datasets/generated",
    "datasets/agentic",
)


@dataclass
class PipelineReport:
    total_candidates: int = 0
    malformed_count: int = 0
    unsafe_count: int = 0
    verified_count: int = 0
    rejected_count: int = 0
    duplicate_count: int = 0
    lowest_score: float = 100.0
    counts_by_category: dict = field(default_factory=dict)
    counts_by_language: dict = field(default_factory=dict)
    counts_by_difficulty: dict = field(default_factory=dict)
    counts_by_split: dict = field(default_factory=dict)
    rejection_reasons: dict = field(default_factory=dict)
    verification_statistics: dict = field(default_factory=dict)
    manifest_path: str = ""

    def to_dict(self) -> dict:
        return {
            "dataset_version": DATASET_VERSION,
            "pipeline_version": PIPELINE_VERSION,
            "schema_version": SCHEMA_VERSION,
            "generated_at": export.utcnow(),
            "total_candidates": self.total_candidates,
            "malformed_count": self.malformed_count,
            "unsafe_count": self.unsafe_count,
            "verified_count": self.verified_count,
            "rejected_count": self.rejected_count,
            "duplicate_count": self.duplicate_count,
            "lowest_score": self.lowest_score,
            "counts_by_category": dict(self.counts_by_category),
            "counts_by_language": dict(self.counts_by_language),
            "counts_by_difficulty": dict(self.counts_by_difficulty),
            "counts_by_split": dict(self.counts_by_split),
            "rejection_reasons": dict(self.rejection_reasons),
            "verification_statistics": dict(self.verification_statistics),
        }


class DatasetPipeline:
    def __init__(
        self,
        root: str | Path | None = None,
        candidate_dirs: list[str] | tuple[str, ...] | None = None,
        verified_dir: str = "datasets/verified",
        rejected_dir: str = "datasets/rejected",
        manifest_dir: str = "datasets/manifests",
        min_score: float = score.DEFAULT_MIN_SCORE,
        docker_binary: str = "docker",
    ):
        self.root = Path(root or REPO_ROOT)
        self.candidate_dirs = [
            self._resolve(directory)
            for directory in (
                candidate_dirs if candidate_dirs is not None else DEFAULT_CANDIDATE_DIRS
            )
        ]
        self.verified_dir = self._resolve(verified_dir)
        self.rejected_dir = self._resolve(rejected_dir)
        self.manifest_dir = self._resolve(manifest_dir)
        self.min_score = min_score
        self.docker_binary = docker_binary

    def _resolve(self, path: str | Path) -> Path:
        candidate = Path(path)
        return candidate if candidate.is_absolute() else self.root / candidate

    # ------------------------------------------------------------------ load

    def load_candidates(self) -> list[dict]:
        candidates = []
        for directory in self.candidate_dirs:
            if not directory.is_dir():
                continue
            for path in sorted(directory.glob("*.jsonl")):
                try:
                    candidates.extend(export.read_jsonl(path))
                except ValueError as exc:
                    # A malformed file must not silently drop candidates.
                    raise ValueError(f"Failed to load {path}: {exc}") from exc
        return candidates

    # ------------------------------------------------------------------- run

    def run(self) -> PipelineReport:
        candidates = self.load_candidates()
        report = PipelineReport(total_candidates=len(candidates))

        rejected: list[dict] = []
        pending: list[dict] = []  # dicts of candidate/verification/safety

        for candidate in candidates:
            errors = verify.validate_candidate(candidate)
            if errors:
                report.malformed_count += 1
                rejected.append(verify.reject_record(
                    candidate, verify.REASON_MALFORMED, "; ".join(errors)
                ))
                continue

            safety = verify.safety_scan(candidate)
            if safety["unsafe"]:
                report.unsafe_count += 1
                rejected.append(verify.reject_record(
                    candidate,
                    verify.REASON_UNSAFE,
                    "dangerous content: " + ", ".join(safety["labels"]),
                ))
                continue

            decision = verify.executable_decision(candidate)

            if decision == "unsupported_language":
                rejected.append(verify.reject_record(
                    candidate,
                    verify.REASON_UNSUPPORTED_LANGUAGE,
                    f"language {candidate.get('language')!r} is not supported "
                    f"by the sandbox ({verify.EXECUTABLE_LANGUAGES})",
                ))
                continue

            if decision == "verify":
                outcome = verify.verify_candidate(
                    candidate, docker_binary=self.docker_binary
                )
                verification = outcome["verification"]
                if outcome["reason"] is not None:
                    rejected.append(verify.reject_record(
                        candidate,
                        outcome["reason"],
                        f"exit_code={verification['exit_code']} "
                        f"timed_out={verification['timed_out']}",
                    ))
                    continue
            else:
                verification = verify.not_required_verification()

            pending.append({
                "candidate": candidate,
                "verification": verification,
                "safety": safety,
            })

        # ------------------------------------------------------------- scoring

        passing = []
        for item in pending:
            dims = score.score_candidate(
                item["candidate"],
                item["verification"],
                item["safety"],
            )
            report.lowest_score = min(report.lowest_score, dims["total"])
            if score.is_pass_score(dims["total"], self.min_score):
                item["score"] = dims
                passing.append(item)
            else:
                rejected.append(verify.reject_record(
                    item["candidate"],
                    verify.REASON_LOW_QUALITY,
                    f"score {dims['total']:.1f} below threshold {self.min_score}",
                ))

        # --------------------------------------------------------- deduplicate

        dedup_input = [item["candidate"] for item in passing]
        kept_candidates, duplicates = deduplicate.deduplicate(dedup_input)
        report.duplicate_count = len(duplicates)
        for duplicate in duplicates:
            rejected.append(verify.reject_record(
                duplicate["candidate"],
                verify.REASON_DUPLICATE,
                f"{duplicate['duplicate_type']} duplicate of "
                f"{duplicate['duplicate_of']}",
            ))

        kept_ids = {id(candidate) for candidate in kept_candidates}
        final = [item for item in passing if id(item["candidate"]) in kept_ids]

        # --------------------------------------------------- splits and export

        splits = {"train": [], "validation": [], "test": []}
        for item in final:
            fingerprint = content_fingerprint(item["candidate"])
            split = assign_split(fingerprint)
            record = export.build_record(
                item["candidate"],
                item["verification"],
                fingerprint,
                split,
            )
            splits[split].append(record)

        report.verified_count = len(final)

        verified_records = []
        for split, records in splits.items():
            report.counts_by_split[split] = len(records)
            export.write_jsonl(self.verified_dir / f"{split}.jsonl", records)
            verified_records.extend(records)

        if verified_records:
            export.write_jsonl(self.verified_dir / "verified.jsonl", verified_records)

        for record in verified_records:
            report.counts_by_category[record["category"]] = (
                report.counts_by_category.get(record["category"], 0) + 1
            )
            language = record.get("language") or "(none)"
            report.counts_by_language[language] = (
                report.counts_by_language.get(language, 0) + 1
            )
            report.counts_by_difficulty[record["difficulty"]] = (
                report.counts_by_difficulty.get(record["difficulty"], 0) + 1
            )
            status = record.get("verification", {}).get("status", "unknown")
            report.verification_statistics[status] = (
                report.verification_statistics.get(status, 0) + 1
            )

        # ----------------------------------------------------------- rejection

        report.rejected_count = len(rejected)
        for entry in rejected:
            reason = entry["reason"]
            report.rejection_reasons[reason] = (
                report.rejection_reasons.get(reason, 0) + 1
            )
        self._write_rejected(rejected)

        # ------------------------------------------------------------ manifest

        manifest = export.build_manifest(report.to_dict(), splits)
        report.manifest_path = export.write_manifest(self.manifest_dir, manifest)

        return report

    def _write_rejected(self, entries: list[dict]) -> None:
        by_reason: dict[str, list[dict]] = {}
        for entry in entries:
            by_reason.setdefault(entry["reason"], []).append(entry)
        for reason, records in by_reason.items():
            export.write_jsonl(self.rejected_dir / f"{reason}.jsonl", records)