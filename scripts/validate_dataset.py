#!/usr/bin/env python3
"""Standalone dataset validation script.

Validates dataset JSONL/JSON files (candidates or exported training
records) against the Penthos schema and exits non-zero when invalid.

Examples:
  python scripts/validate_dataset.py datasets/verified/verified.jsonl
  python scripts/validate_dataset.py datasets/candidates
"""

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from training.data_pipeline import export, verify  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate Penthos dataset files.")
    parser.add_argument("path", nargs="+", help="JSONL files or directories to validate")
    parser.add_argument(
        "--record",
        action="store_true",
        help="Validate as exported training records (not candidates).",
    )
    args = parser.parse_args(argv)

    total = 0
    invalid = 0

    for raw in args.path:
        path = Path(raw)
        if path.is_dir():
            paths = sorted(path.glob("*.jsonl"))
        else:
            paths = [path]

        for jsonl in paths:
            records = export.read_jsonl(jsonl)
            for record in records:
                total += 1
                errors = (
                    verify.validate_record(record)
                    if args.record
                    else verify.validate_candidate(record)
                )
                if errors:
                    invalid += 1
                    print(f"{jsonl}: {record.get('id', '<no id>')} INVALID:")
                    for error in errors:
                        print(f"    - {error}")

    print(f"validated {total} record(s), {invalid} invalid")
    return 1 if invalid else 0


if __name__ == "__main__":
    raise SystemExit(main())