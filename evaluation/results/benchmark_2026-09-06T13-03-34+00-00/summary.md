# Penthos Model Benchmark

- model: `Qwen/Qwen3-4B-MLX-4bit`
- mlx_lm: 0.31.3
- temperature: 0.0
- max_tokens: 2048
- generated: 2026-09-06T13-03-34+00-00
- total: 17 | passed: 10 | failed: 7 | unscored: 0

## By category

| category | total | passed | failed | pass rate |
| --- | ---: | ---: | ---: | ---: |
| agentic | 2 | 1 | 1 | 0.5 |
| coding | 5 | 3 | 2 | 0.6 |
| debugging | 3 | 2 | 1 | 0.67 |
| general_chat | 1 | 0 | 1 | 0.0 |
| reasoning | 3 | 3 | 0 | 1.0 |
| security | 2 | 1 | 1 | 0.5 |
| software_engineering | 1 | 0 | 1 | 0.0 |

## Tasks

- [PASS] `coding_001` (coding): freeform
- [PASS] `debug_001` (debugging): freeform
- [PASS] `reasoning_001` (reasoning): freeform
- [FAIL] `repo_001` (software_engineering): freeform
    - missed rubric terms: read
- [FAIL] `agent_001` (agentic): freeform
    - missed rubric terms: isolate, rerun
- [FAIL] `security_001` (security): freeform
    - missed rubric terms: gitignore, rotate
- [FAIL] `coding_002` (coding): freeform
    - missed rubric terms: timer
- [FAIL] `debug_002` (debugging): freeform
    - missed rubric terms: reproduce
- [PASS] `seed-agentic-loop-0012` (agentic): freeform
- [PASS] `seed-python-add-0001` (coding): sandbox_test
- [PASS] `seed-python-fizzbuzz-0002` (coding): sandbox_test
- [FAIL] `seed-ts-add-0003` (coding): sandbox_test
- [PASS] `seed-debug-max-0005` (debugging): sandbox_test
- [PASS] `seed-dup-sheep-0019` (reasoning): freeform
- [PASS] `seed-reason-ml-0009` (reasoning): freeform
- [PASS] `seed-sec-passlen-0006` (security): sandbox_test
- [FAIL] `seed-chat-penthos-0010` (general_chat): freeform
    - missed rubric terms: agent, sandbox, training
