# Penthos Model Benchmark

- model: `Qwen/Qwen3-4B-MLX-4bit`
- mlx_lm: 0.31.3
- temperature: 0.0
- max_tokens: 4096
- generated: 2026-09-07T11-27-55+00-00
- total: 7 | passed: 0 | failed: 7 | unscored: 0

## By category

| category | total | passed | failed | pass rate |
| --- | ---: | ---: | ---: | ---: |
| agentic | 2 | 0 | 2 | 0.0 |
| coding | 2 | 0 | 2 | 0.0 |
| debugging | 2 | 0 | 2 | 0.0 |
| software_engineering | 1 | 0 | 1 | 0.0 |

## Tasks

- [FAIL] `coding_001` (coding): freeform
    - missed rubric terms: set, o(n), space
- [FAIL] `debug_001` (debugging): freeform
    - missed rubric terms: setcount, useeffect, infinite
- [FAIL] `repo_001` (software_engineering): freeform
    - missed rubric terms: git, test, secret, structure
- [FAIL] `agent_001` (agentic): freeform
    - missed rubric terms: test, fix, verify
- [FAIL] `coding_002` (coding): freeform
    - missed rubric terms: settimeout, cleartimeout, delay
- [FAIL] `debug_002` (debugging): freeform
    - missed rubric terms: log, replicat, environment, memory
- [FAIL] `seed-agentic-loop-0012` (agentic): freeform
    - missed rubric terms: fix, test, report
