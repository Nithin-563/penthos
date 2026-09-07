#!/usr/bin/env python3
"""Fold self-teacher rows into mlx_lm.lora train/valid/test datasets.

Reads datasets/mlx/self_teacher.jsonl (rows: {"prompt","completion",...}),
drops exact duplicates, and writes datasets/mlx/{train,valid,test}.jsonl in
the {"prompt","completion"} format consumed by mlx_lm.lora --data.

Usage:
  python scripts/make_mlx_data.py [--source datasets/mlx/self_teacher.jsonl]
"""

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _fold(key: str, seed: str = "penthos-mlx-v1") -> str:
    digest = hashlib.sha256(f"{seed}:{key}".encode()).hexdigest()
    bucket = int(digest[:8], 16) % 100
    if bucket < 5:
        return "validation"
    if bucket < 10:
        return "test"
    return "train"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fold teacher rows into mlx splits.")
    parser.add_argument("--source", default=str(REPO_ROOT / "datasets/mlx/self_teacher.jsonl"))
    parser.add_argument("--out", default=str(REPO_ROOT / "datasets/mlx"))
    args = parser.parse_args(argv)

    source = Path(args.source)
    rows = []
    for line in source.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    print(f"read {len(rows)} rows from {source}")

    seen = set()
    unique = []
    for row in rows:
        prompt = row.get("prompt", "")
        completion = row.get("completion", "")
        if not completion:
            continue
        key = f"{prompt}\x00{completion}"
        if key in seen:
            continue
        seen.add(key)
        unique.append((row, key))

    folds: "dict[str, list[dict]]" = {"train": [], "validation": [], "test": []}
    counts = Counter()
    for row, key in unique:
        # Fold by task id, not by sample, so every sample of one task lands in
        # a single split and validation/test never leak a trained-identical task.
        fold = _fold(str(row.get("id", "")))
        folds[fold].append({
            "prompt": row["prompt"],
            "completion": row["completion"],
        })
        counts[f"{row.get('reason')}/{fold}"] += 1

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    for fold, records in folds.items():
        with (out_dir / f"{fold}.jsonl").open("w", encoding="utf-8") as f:
            for record in records:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        print(f"{fold}: {len(records)} rows")

    print("counts:", dict(counts))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())