# Penthos Model Benchmark

- model: `Qwen/Qwen3-4B-MLX-4bit`
- mlx_lm: 0.31.3
- temperature: 0.0
- max_tokens: 4096
- generated: 2026-09-07T11-23-27+00-00
- total: 26 | passed: 16 | failed: 10 | unscored: 0

## By category

| category | total | passed | failed | pass rate |
| --- | ---: | ---: | ---: | ---: |
| agentic | 2 | 0 | 2 | 0.0 |
| coding | 8 | 4 | 4 | 0.5 |
| debugging | 5 | 3 | 2 | 0.6 |
| general_chat | 1 | 1 | 0 | 1.0 |
| reasoning | 4 | 4 | 0 | 1.0 |
| security | 4 | 3 | 1 | 0.75 |
| software_engineering | 2 | 1 | 1 | 0.5 |

## Tasks

- [FAIL] `coding_001` (coding): freeform
    - missed rubric terms: set, o(n), space
- [FAIL] `debug_001` (debugging): freeform
    - missed rubric terms: setcount, useeffect, infinite
- [PASS] `reasoning_001` (reasoning): freeform
- [FAIL] `repo_001` (software_engineering): freeform
    - missed rubric terms: git, test, secret, structure
- [FAIL] `agent_001` (agentic): freeform
    - missed rubric terms: test, fix, verify
- [PASS] `security_001` (security): freeform
    - missed rubric terms: .env
- [FAIL] `coding_002` (coding): freeform
    - missed rubric terms: settimeout, cleartimeout, delay
- [FAIL] `debug_002` (debugging): freeform
    - missed rubric terms: log, replicat, environment, memory
- [FAIL] `seed-agentic-loop-0012` (agentic): freeform
    - missed rubric terms: fix, test, report
- [PASS] `challenge-substr-1001` (coding): sandbox_test
- [PASS] `challenge-merge-1002` (coding): sandbox_test
- [PASS] `challenge-revwords-1004` (debugging): sandbox_test
- [PASS] `challenge-flatten-1005` (debugging): sandbox_test
- [PASS] `challenge-passcmp-1006` (security): sandbox_test
- [FAIL] `challenge-xss-1007` (security): sandbox_test
- [PASS] `challenge-endpoint-1008` (software_engineering): freeform
- [PASS] `seed-python-add-0001` (coding): sandbox_test
- [FAIL] `seed-python-fizzbuzz-0002` (coding): sandbox_test
- [PASS] `seed-ts-add-0003` (coding): sandbox_test
- [PASS] `seed-debug-max-0005` (debugging): sandbox_test
- [PASS] `seed-reason-sheep-0008` (reasoning): freeform
- [PASS] `seed-reason-ml-0009` (reasoning): freeform
    - missed rubric terms: unlabeled
- [PASS] `seed-sec-passlen-0006` (security): sandbox_test
- [FAIL] `challenge-lru-1003` (coding): sandbox_test
- [PASS] `challenge-cycle-1009` (reasoning): freeform
- [PASS] `seed-chat-penthos-0010` (general_chat): freeform
