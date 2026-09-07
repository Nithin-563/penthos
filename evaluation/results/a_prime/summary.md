# Penthos Model Benchmark

- model: `Qwen/Qwen3-4B-MLX-4bit`
- mlx_lm: 0.31.3
- temperature: 0.0
- max_tokens: 4096
- generated: 2026-09-06T14-03-47+00-00
- total: 17 | passed: 17 | failed: 0 | unscored: 0

## By category

| category | total | passed | failed | pass rate |
| --- | ---: | ---: | ---: | ---: |
| agentic | 2 | 2 | 0 | 1.0 |
| coding | 5 | 5 | 0 | 1.0 |
| debugging | 3 | 3 | 0 | 1.0 |
| general_chat | 1 | 1 | 0 | 1.0 |
| reasoning | 3 | 3 | 0 | 1.0 |
| security | 2 | 2 | 0 | 1.0 |
| software_engineering | 1 | 1 | 0 | 1.0 |

## Tasks

- [PASS] `coding_001` (coding): freeform
- [PASS] `debug_001` (debugging): freeform
- [PASS] `reasoning_001` (reasoning): freeform
- [PASS] `repo_001` (software_engineering): freeform
- [PASS] `agent_001` (agentic): freeform
- [PASS] `security_001` (security): freeform
- [PASS] `coding_002` (coding): freeform
- [PASS] `debug_002` (debugging): freeform
- [PASS] `seed-agentic-loop-0012` (agentic): freeform
- [PASS] `seed-python-add-0001` (coding): sandbox_test
- [PASS] `seed-python-fizzbuzz-0002` (coding): sandbox_test
- [PASS] `seed-ts-add-0003` (coding): sandbox_test
- [PASS] `seed-debug-max-0005` (debugging): sandbox_test
- [PASS] `seed-reason-sheep-0008` (reasoning): freeform
- [PASS] `seed-reason-ml-0009` (reasoning): freeform
- [PASS] `seed-sec-passlen-0006` (security): sandbox_test
- [PASS] `seed-chat-penthos-0010` (general_chat): freeform
    - missed rubric terms: agent
