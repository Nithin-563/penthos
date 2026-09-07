# Penthos Model Benchmark

- model: `Qwen/Qwen3-4B-MLX-4bit`
- mlx_lm: 0.31.3
- temperature: 0.0
- max_tokens: 4096
- generated: 2026-09-06T14-43-26+00-00
- total: 26 | passed: 23 | failed: 3 | unscored: 0

## By category

| category | total | passed | failed | pass rate |
| --- | ---: | ---: | ---: | ---: |
| agentic | 2 | 2 | 0 | 1.0 |
| coding | 8 | 6 | 2 | 0.75 |
| debugging | 5 | 4 | 1 | 0.8 |
| general_chat | 1 | 1 | 0 | 1.0 |
| reasoning | 4 | 4 | 0 | 1.0 |
| security | 4 | 4 | 0 | 1.0 |
| software_engineering | 2 | 2 | 0 | 1.0 |

## Tasks

- [PASS] `coding_001` (coding): freeform
- [FAIL] `debug_001` (debugging): freeform
    - missed rubric terms: useeffect
- [PASS] `reasoning_001` (reasoning): freeform
    - missed rubric terms: memory
- [PASS] `repo_001` (software_engineering): freeform
- [PASS] `agent_001` (agentic): freeform
- [PASS] `security_001` (security): freeform
- [PASS] `coding_002` (coding): freeform
- [PASS] `debug_002` (debugging): freeform
- [PASS] `seed-agentic-loop-0012` (agentic): freeform
- [PASS] `challenge-substr-1001` (coding): sandbox_test
- [PASS] `challenge-merge-1002` (coding): sandbox_test
- [PASS] `challenge-revwords-1004` (debugging): sandbox_test
- [PASS] `challenge-flatten-1005` (debugging): sandbox_test
- [PASS] `challenge-passcmp-1006` (security): sandbox_test
- [PASS] `challenge-xss-1007` (security): sandbox_test
- [PASS] `challenge-endpoint-1008` (software_engineering): freeform
    - missed rubric terms: auth
- [PASS] `seed-python-add-0001` (coding): sandbox_test
- [FAIL] `seed-python-fizzbuzz-0002` (coding): sandbox_test
- [PASS] `seed-ts-add-0003` (coding): sandbox_test
- [PASS] `seed-debug-max-0005` (debugging): sandbox_test
- [PASS] `seed-reason-sheep-0008` (reasoning): freeform
- [PASS] `seed-reason-ml-0009` (reasoning): freeform
- [PASS] `seed-sec-passlen-0006` (security): sandbox_test
- [FAIL] `challenge-lru-1003` (coding): sandbox_test
- [PASS] `challenge-cycle-1009` (reasoning): freeform
- [PASS] `seed-chat-penthos-0010` (general_chat): freeform
