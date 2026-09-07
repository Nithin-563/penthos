# Penthos Baseline Evaluation

This suite measures Penthos before training. The same prompts are reused
after every major training change so results can be compared objectively.

## Categories

- coding
- debugging
- reasoning
- software engineering
- agentic behavior
- security
- general chat

## Running the full benchmark

```
python evaluation/run_benchmark.py
```

The runner loads the local Penthos weights (loader handle `Qwen/Qwen3-4B-MLX-4bit`), runs every task
in `evaluation/baseline/tasks.json` plus every record in
`datasets/verified/verified.jsonl`, and writes results to
`evaluation/results/<stamp>/` (`report.json`, per-task `outputs/*.txt`, and
`summary.md`).

Task grading:
- Free-form tasks are graded by rubric-term coverage (terms are lowercase
  substrings; see `rubric` in `tasks.json`). Every output is also saved for
  manual review — rubric misses are a signal, not a verdict.
- Executable tasks (code/debugging/security records in the verified dataset)
  place the model's generated source next to the reference tests and run it
  **inside the Docker sandbox**. Pass/fail is decided by the sandbox exit code
  and expected output. No model output is executed on the host.

Useful flags:

```
python evaluation/run_benchmark.py --categories coding,reasoning
python evaluation/run_benchmark.py --ids coding_001 seed-ts-add-0003
python evaluation/run_benchmark.py --temp 0.2 --max-tokens 1024
```

The default run is greedy decode (temperature 0) so results are reproducible;
repeat runs before/after any training change for comparison.