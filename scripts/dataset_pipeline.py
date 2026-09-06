#!/usr/bin/env python3
"""Penthos dataset pipeline CLI.

Commands:
  validate      validate candidate files against the schema
  verify        verify executable candidates inside the Docker sandbox
  deduplicate   write only unique candidates to an output file
  score         score candidates and emit a JSONL report
  export        export record JSONL grouped by deterministic splits
  generate      generate synthetic candidates through a teacher interface
  run           run the full pipeline (validate → verify → score → export)

Examples:
  python scripts/dataset_pipeline.py validate
  python scripts/dataset_pipeline.py verify
  python scripts/dataset_pipeline.py score
  python scripts/dataset_pipeline.py export
  python scripts/dataset_pipeline.py run
"""

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from training.data_pipeline import deduplicate, export, generate, pipeline, score, verify  # noqa: E402
from sandbox import runner  # noqa: E402


def _load_candidates(paths: list[str]) -> list[dict]:
    candidates = []
    for raw in paths:
        path = Path(raw)
        if not path.exists():
            raise SystemExit(f"no such file or directory: {raw}")
        if path.is_dir():
            for jsonl in sorted(path.glob("*.jsonl")):
                candidates.extend(export.read_jsonl(jsonl))
        else:
            candidates.extend(export.read_jsonl(path))
    return candidates


def _default_candidates() -> list[str]:
    return [
        str(REPO_ROOT / "datasets/candidates"),
        str(REPO_ROOT / "datasets/generated"),
        str(REPO_ROOT / "datasets/agentic"),
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="dataset_pipeline",
        description="Penthos verified training data pipeline.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("validate", help="Validate candidate files against the schema.")

    verify_p = sub.add_parser("verify", help="Verify executable candidates in the sandbox.")
    verify_p.add_argument("--candidates", nargs="*", default=_default_candidates())
    verify_p.add_argument("--out", default=str(REPO_ROOT / "datasets/rejected"))
    verify_p.add_argument("--docker", default="docker")

    dedup_p = sub.add_parser("deduplicate", help="Deduplicate candidates.")
    dedup_p.add_argument("--candidates", nargs="*", default=_default_candidates())
    dedup_p.add_argument("--out", default=str(REPO_ROOT / "datasets/generated/deduped.jsonl"))
    dedup_p.add_argument("--duplicates-out", default=str(REPO_ROOT / "datasets/rejected/duplicate.jsonl"))

    score_p = sub.add_parser("score", help="Score candidates.")
    score_p.add_argument("--candidates", nargs="*", default=_default_candidates())
    score_p.add_argument("--out", default=str(REPO_ROOT / "datasets/generated/scored.jsonl"))
    score_p.add_argument("--min-score", type=float, default=score.DEFAULT_MIN_SCORE)

    export_p = sub.add_parser("export", help="Export records into deterministic splits.")
    export_p.add_argument("--candidates", nargs="*", default=_default_candidates())
    export_p.add_argument("--out", default=str(REPO_ROOT / "datasets/verified"))

    gen_p = sub.add_parser("generate", help="Generate synthetic candidates via a teacher.")
    gen_p.add_argument("--teacher", default="stub")
    gen_p.add_argument("--task", action="append", required=True)
    gen_p.add_argument("--out", default=str(REPO_ROOT / "datasets/generated/stub.jsonl"))

    run_p = sub.add_parser("run", help="Run the full pipeline.")
    run_p.add_argument("--min-score", type=float, default=score.DEFAULT_MIN_SCORE)
    run_p.add_argument("--docker", default="docker")

    args = parser.parse_args(argv)

    if args.command == "validate":
        return _cmd_validate()
    if args.command == "verify":
        return _cmd_verify(args)
    if args.command == "deduplicate":
        return _cmd_deduplicate(args)
    if args.command == "score":
        return _cmd_score(args)
    if args.command == "export":
        return _cmd_export(args)
    if args.command == "generate":
        return _cmd_generate(args)
    if args.command == "run":
        return _cmd_run(args)
    parser.error(f"unknown command: {args.command}")
    return 2


def _cmd_validate() -> int:
    candidates = _load_candidates(_default_candidates())
    bad = 0
    for index, candidate in enumerate(candidates):
        errors = verify.validate_candidate(candidate)
        if errors:
            bad += 1
            print(f"[{index}] {candidate.get('id', '<no id>')} INVALID:")
            for error in errors:
                print(f"    - {error}")
    print(f"validated {len(candidates)} candidate(s), {bad} invalid")
    return 1 if bad else 0


def _cmd_verify(args) -> int:
    candidates = _load_candidates(args.candidates)
    rejected_path = Path(args.out)
    rejected_path.mkdir(parents=True, exist_ok=True)

    accepted = []
    rejected = []
    for candidate in candidates:
        errors = verify.validate_candidate(candidate)
        if errors:
            rejected.append(verify.reject_record(candidate, verify.REASON_MALFORMED, "; ".join(errors)))
            continue
        if verify.executable_decision(candidate) == "verify":
            outcome = verify.verify_candidate(candidate, docker_binary=args.docker)
            if outcome["reason"] is not None:
                rejected.append(verify.reject_record(candidate, outcome["reason"], "verification failed"))
            else:
                accepted.append((candidate, outcome["verification"]))
        else:
            accepted.append((candidate, verify.not_required_verification()))

    export.write_jsonl(rejected_path / "rejected.jsonl", rejected)
    for candidate, _ in accepted:
        print(f"PASS {candidate.get('id', '<no id>')}")
    for entry in rejected:
        print(f"FAIL {entry['candidate'].get('id', '<no id>')} [{entry['reason']}]")
    return 0


def _cmd_deduplicate(args) -> int:
    candidates = _load_candidates(args.candidates)
    kept, duplicates = deduplicate.deduplicate(candidates)
    export.write_jsonl(args.out, kept)
    if args.duplicates_out:
        export.write_jsonl(args.duplicates_out, duplicates)
    print(f"{len(candidates)} candidates -> {len(kept)} kept, {len(duplicates)} duplicates")
    return 0


def _cmd_score(args) -> int:
    candidates = _load_candidates(args.candidates)
    records = []
    passed = 0
    for candidate in candidates:
        safety = verify.safety_scan(candidate)
        dims = score.score_candidate(
            candidate,
            verify.not_required_verification() if not candidate.get("code") else None,
            safety,
        )
        passed += score.is_pass_score(dims["total"], args.min_score)
        records.append({"candidate": candidate, "score": dims})
    export.write_jsonl(args.out, records)
    print(f"scored {len(candidates)} candidate(s), {passed} pass min threshold {args.min_score}")
    return 0


def _cmd_export(args) -> int:
    candidates = _load_candidates(args.candidates)
    out_dir = Path(args.out)
    splits = {"train": [], "validation": [], "test": []}
    seen_fingerprints = set()
    for candidate in candidates:
        fingerprint = deduplicate.content_fingerprint(candidate)
        seen_fingerprints.add(fingerprint)
        split = deduplicate.assign_split(fingerprint)
        splits[split].append(
            export.build_record(candidate, verify.not_required_verification(), fingerprint, split)
        )
    for split, records in splits.items():
        export.write_jsonl(out_dir / f"{split}.jsonl", records)
    print(
        f"exported {len(candidates)} candidate(s) "
        f"(train={len(splits['train'])}, validation={len(splits['validation'])}, "
        f"test={len(splits['test'])}), {len(seen_fingerprints)} unique fingerprints"
    )
    return 0


def _cmd_generate(args) -> int:
    if args.teacher == "stub":
        teacher = generate.StubTeacher()
    else:
        raise SystemExit(f"unknown teacher: {args.teacher} (only 'stub' is available)")
    candidates = generate.generate_candidates(teacher, args.task, output_path=args.out)
    print(f"generated {len(candidates)} synthetic candidate(s) -> {args.out}")
    return 0


def _cmd_run(args) -> int:
    driver = pipeline.DatasetPipeline(
        root=REPO_ROOT,
        min_score=args.min_score,
        docker_binary=args.docker,
    )
    report = driver.run()
    print("=== dataset pipeline complete ===")
    data = report.to_dict()
    for key in (
        "total_candidates",
        "malformed_count",
        "unsafe_count",
        "verified_count",
        "rejected_count",
        "duplicate_count",
    ):
        print(f"{key}: {data[key]}")
    print(f"counts_by_category: {data['counts_by_category']}")
    print(f"counts_by_language: {data['counts_by_language']}")
    print(f"counts_by_split: {data['counts_by_split']}")
    print(f"rejection_reasons: {data['rejection_reasons']}")
    print(f"verification_statistics: {data['verification_statistics']}")
    print(f"manifest: {report.manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())