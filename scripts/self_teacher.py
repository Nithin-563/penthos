#!/usr/bin/env python3
"""Self-teacher: distil the model's verified outputs into LoRA training rows.

For every task in the benchmark suite (baseline tasks + verified dataset
records) the teacher samples several model completions, grades each one with
the same harness logic used by the benchmark (Docker sandbox for code,
rubric-term coverage for free-form), and keeps only the *passing* outputs as
training rows. Gold rows are also emitted for executable records, anchored to
the reference solution.

Each row is written in the raw inference-matching format:
    {"prompt": <applied_chat_template(system+user)>, "completion": <output>}
so mlx_lm.lora trains on the exact sequence the model sees at inference.

Usage:
  python scripts/self_teacher.py --samples-per-task 3 --out datasets/mlx/self_teacher.jsonl
  python scripts/self_teacher.py --categories coding,security --limit 5
"""

import argparse
import json
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from inference.prompt import PENTHOS_SYSTEM_PROMPT  # noqa: E402
from evaluation import run_benchmark as bench  # noqa: E402


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Self-teacher distillation.")
    parser.add_argument("--sources", nargs="*", default=["baseline", "verified"],
                        choices=["baseline", "verified"])
    parser.add_argument("--categories", default=None)
    parser.add_argument("--ids", default=None)
    parser.add_argument("--limit", type=int, default=0,
                        help="only run the first N matching tasks")
    parser.add_argument("--samples-per-task", type=int, default=3)
    parser.add_argument("--temp", type=float, default=0.7)
    parser.add_argument("--max-tokens-code", type=int, default=1536)
    parser.add_argument("--max-tokens-freeform", type=int, default=3072)
    parser.add_argument("--docker", default="docker")
    parser.add_argument("--out", default=str(REPO_ROOT / "datasets/mlx/self_teacher.jsonl"))
    parser.add_argument("--seed", type=int, default=1234)
    parser.add_argument("--thinking-freeform", action="store_true", default=False,
                        help="generate freeform completions with thinking enabled "
                             "(default off: clean, straight answers train better; "
                             "inference still uses thinking)")
    parser.add_argument("--gold", action="store_true", default=True,
                        help="also emit gold rows for executable records (default on)")
    args = parser.parse_args(argv)

    categories = {c.strip() for c in (args.categories or "").split(",") if c.strip()}
    ids = {i.strip() for i in (args.ids or "").split(",") if i.strip()}

    tasks = bench.build_suite(tuple(args.sources), categories, ids)
    if args.limit:
        tasks = tasks[: args.limit]
    if not tasks:
        print("no tasks matched")
        return 2

    print(f"loading model {bench.MODEL} ...")
    from mlx_lm import load

    model, tokenizer = load(bench.MODEL)

    rng = random.Random(args.seed)
    start_all = time.monotonic()
    rows: list[dict] = []
    stats: dict[str, dict] = {}

    for task_index, task in enumerate(tasks, start=1):
        grading = task.get("grading")
        is_sandbox = bool(grading and grading["type"] == "sandbox_test")
        use_thinking = args.thinking_freeform and not is_sandbox
        max_tokens = (
            args.max_tokens_code if grading and grading["type"] == "sandbox_test"
            else args.max_tokens_freeform
        )
        sid = task["id"]
        passed = 0
        for sample in range(args.samples_per_task):
            prompt = bench.build_prompt(tokenizer, task, PENTHOS_SYSTEM_PROMPT, use_thinking)
            started = time.monotonic()
            try:
                output, tokens, _ = bench.generate(model, tokenizer, prompt, max_tokens, args.temp)
            except RuntimeError as exc:
                print(f"  [{sid}] sample {sample} error: {exc}")
                continue
            elapsed = time.monotonic() - started

            if grading and grading["type"] == "sandbox_test":
                grade = bench.grade_executable(task, output, args.docker)
            else:
                grade = bench.grade_freeform(task, output)

            if grade["pass"] is True:
                passed += 1
                clean = bench.clean_completion(output) if use_thinking else output
                if use_thinking and not clean.strip():
                    print(f"[{task_index}/{len(tasks)}] {sid} dropped: no clean answer")
                    continue
                rows.append({
                    "id": sid,
                    "sample": sample,
                    "category": task["category"],
                    "difficulty": task.get("difficulty"),
                    "reason": "distilled",
                    "prompt": prompt,
                    "completion": clean,
                    "tokens": tokens,
                })
            print(f"[{task_index}/{len(tasks)}] {sid} [{grade['type']}] "
                  f"sample {sample + 1}, pass={grade['pass']} ({tokens} tok, "
                  f"{round(elapsed, 1)}s)")
        stats[sid] = {
            "category": task["category"],
            "type": "sandbox" if grading else "freeform",
            "samples": args.samples_per_task,
            "passed": passed,
        }

    if args.gold:
        record_index = 0
        verified = bench.read_jsonl(bench.VERIFIED_JSONL)
        for record in verified:
            if not record.get("files"):
                continue
            record_index += 1
            task = {
                "id": record["id"],
                "category": record["category"],
                "difficulty": record["difficulty"],
                "language": record.get("language") or None,
                "source": "verified",
                "prompt": record["prompt"],
                "grading": bench._build_grading(record),
            }
            prompt = bench.build_prompt(tokenizer, task, PENTHOS_SYSTEM_PROMPT, thinking=False)
            rows.append({
                "id": record["id"],
                "sample": -1,
                "category": record["category"],
                "difficulty": record["difficulty"],
                "reason": "gold",
                "prompt": prompt,
                "completion": record["code"],
                "tokens": len(tokenizer.encode(record["code"])),
            })
            passed_count = stats.get(record["id"], {}).get("passed", 0)
            key = record["id"]
            stats.setdefault(key, {"category": record["category"], "type": "sandbox",
                                   "samples": 0, "passed": 0})
            stats[key]["samples"] += 1
            stats[key]["passed"] += 1

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    distilled = sum(1 for r in rows if r["reason"] == "distilled")
    gold = sum(1 for r in rows if r["reason"] == "gold")
    stats_out = {
        "generated_at": utcnow(),
        "model": bench.MODEL,
        "temp": args.temp,
        "samples_per_task": args.samples_per_task,
        "thinking_freeform": args.thinking_freeform,
    "tasks": len(tasks),
        "rows_total": len(rows),
        "rows_distilled": distilled,
        "rows_gold": gold,
        "rows_by_category": {},
        "per_task": stats,
        "elapsed_s": round(time.monotonic() - start_all, 1),
    }
    for row in rows:
        stats_out["rows_by_category"].setdefault(row["category"], 0)
        stats_out["rows_by_category"][row["category"]] += 1
    (out_path.parent / "self_teacher_stats.json").write_text(
        json.dumps(stats_out, indent=2, ensure_ascii=False), encoding="utf-8")

    print("\n=== self-teacher complete ===")
    print(f"rows: {len(rows)} (distilled={distilled}, gold={gold})")
    print(f"by_category: {stats_out['rows_by_category']}")
    print(f"elapsed: {stats_out['elapsed_s']}s")
    print(f"rows: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())