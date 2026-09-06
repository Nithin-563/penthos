# Verified Training Data Pipeline

This directory implements Penthos' verified training data pipeline. It takes
candidate examples (raw, synthetic, or human-authored) and produces verified,
deduplicated, scored, split training records — reusing the existing Docker
sandbox for all executable verification. There is **no host execution
fallback**: executable candidates are either verified inside the sandbox or
rejected.

## Layout

```
training/data_pipeline/
├── __init__.py        package metadata (version)
├── verify.py          validation, safety scanning, sandbox routing
├── deduplicate.py     deterministic SHA-256 fingerprints, dedup, splits
├── score.py           transparent heuristic quality scorer
├── export.py          schema-compatible records, JSONL I/O, manifests
├── generate.py        provider-agnostic Teacher interface (optional)
└── pipeline.py        DatasetPipeline orchestration (the full run)
```

## Pipeline flow

```
load candidates
  → validate            reject malformed_record
  → safety scan         reject unsafe_candidate
  → verify in sandbox   reject timeout / tests_failed / execution_failed /
                        invalid_command / unsupported_language
  → score               reject low_quality (below min_score, default 30)
  → deduplicate         reject duplicate (exact + near-instruction)
  → split + export      verified/{train,validation,test,verified}.jsonl
  → manifest            manifests/manifest_latest.json
```

Rejected records are written to `datasets/rejected/<reason>.jsonl` and never
enter `datasets/verified/`.

## Running

From the repository root (Python 3.12, `.venv`):

```
python scripts/dataset_pipeline.py run               # full pipeline (needs Docker)
python scripts/dataset_pipeline.py validate          # schema validation only
python scripts/dataset_pipeline.py verify            # sandbox verification only
python scripts/dataset_pipeline.py deduplicate       # dedup only
python scripts/dataset_pipeline.py score             # scoring report
python scripts/dataset_pipeline.py export            # write deterministic splits
python scripts/dataset_pipeline.py generate --task "..."   # teacher-driven (stub)
python scripts/validate_dataset.py datasets/verified/verified.jsonl --record
```

`run` reads candidates from `datasets/candidates/`, `datasets/generated/`, and
`datasets/agentic/` by default.

## Candidate format

A candidate is a JSON object with these schema-relevant fields:

| field            | in schema | notes |
|------------------|-----------|-------|
| `id`             | ✓         | unique identifier |
| `instruction`    | → `prompt`| required, non-empty |
| `expected_answer`| → `solution` | required for scoring |
| `category`       | ✓         | coding, debugging, reasoning, software_engineering, agentic, security, general_chat |
| `difficulty`     | ✓         | easy, medium, hard, expert |
| `language`       | ✓         | python, node, typescript (or `""` for non-code) |
| `context`        | ✓         | optional |
| `code` / `files` | optional  | at least one required for executable candidates |
| `tests`          | ✓         | `[{input, expected}]` |
| `test_command`   | optional  | runs inside the sandbox; default per language |
| `trajectory`     | optional  | agentic traces; never executed as commands |
| `timeout_seconds`| optional  | verification timeout (bounded by sandbox policy) |
| `source`         | ✓         | `{type: human\|synthetic\|transformed, license, teacher?, generated_at?}` |

## Verification (verify.py)

- `validate_candidate` / `validate_record` check required fields, enum values,
  and value types against `datasets/schema.json`.
- `safety_scan` scans `code`, `files`, and `expected_answer` for hard-danger
  patterns (ssh keys, cloud credentials, `~/.ssh`, `/etc/shadow`, `rm -rf /`,
  host shell execution, secret leakage). Hard hits reject the candidate
  **before** anything is executed. Soft indicators (network, privilege) only
  lower the security score dimension — the sandbox blocks real network access.
- `executable_decision` routes candidates:
  - executable categories (`coding`, `debugging`, `software_engineering`,
    `security`) with supported language + code/files → `verify` in sandbox
  - executable category but missing code → `no_code`, or unsupported language
    → `unsupported_language` (rejected)
  - everything else (reasoning, general_chat, agentic) → `not_required`
- `verify_candidate` builds a sandbox payload (`{language, files, command,
  timeout_seconds}`) and calls `sandbox.runner.execute`. Pass-fail and
  rejection reasons derive only from the sandbox result. The verifier
  injectable `execute` parameter is resolved at call time and always defaults
  to the sandbox runner — never a host runner.
- There is **no host fallback**: if the sandbox is unavailable or the
  candidate fails, the candidate is rejected.

Rejection reasons: `malformed_record`, `unsafe_candidate`, `execution_failed`,
`tests_failed`, `timeout`, `invalid_command`, `unsupported_language`,
`duplicate`, `low_quality`.

## Deduplication and splits (deduplicate.py)

- `normalize_prose` (NFC, casefold, collapsed whitespace) and `normalize_code`
  (ASCII-style, keeps identifier casing, collapses blank runs) make examples
  comparable across runs and synthetic regeneration.
- `content_fingerprint` is a SHA-256 over the normalized schema-relevant
  content (id, timestamps, and provenance are excluded on purpose).
- `instruction_fingerprint` is a SHA-256 over the normalized instruction for
  **near-duplicate** detection: an example sharing a kept example's normalized
  instruction is rejected even if its answer differs.
- Splits are **deterministic and leakage-free**: `assign_split(fingerprint)`
  maps the same fingerprint to the same 80/10/10 bucket forever, so no example
  can appear in two splits.

## Scoring (score.py)

`score_candidate` returns `{total, dimensions}` — a transparent, low-cost,
deterministic heuristic over field completeness, instruction clarity, answer
and code/test presence, verification result, difficulty, reasoning markers,
and security indicators. It is explicitly **not** a measure of answer
correctness or model quality; pass/fail correctness comes exclusively from the
sandbox. Candidates scoring below `min_score` (default 30.0) are rejected as
`low_quality`.

## Provenance and manifests (export.py, generate.py)

- `export.build_record` maps `instruction → prompt`, `expected_answer →
  solution`, preserves all schema fields, and stamps
  `metadata.source`, `metadata.created_at`, `metadata.fingerprint`, and
  `metadata.provenance` for synthetic examples.
- Synthetic output always records `source.type = "synthetic"`, `source.teacher
  = "<provider/model>"`, and `source.generated_at`. Synthetic examples are
  never labeled as human-authored.
- `Teacher` is a provider-agnostic protocol (`name` + `generate(task)`); any of
  Penthos' inference backends can implement it. The pipeline does not require a
  teacher — it works entirely from candidate files. `StubTeacher` is a
  network-free stand-in for tests and dry runs.
- Manifests record dataset/pipeline/schema versions, generation time, counts
  (total/verified/rejected/duplicates, by category, language, difficulty, and
  split), rejection breakdown, verification statistics, and a
  `split_leakage_check` that fails if any fingerprint appears in more than one
  split.

## Security model

- Executable verification happens only inside disposable Docker containers
  (`penthos-sandbox:*`, see `sandbox/`). No candidate code is executed on the
  host.
- Hard-danger candidates are filtered statically before any container is
  started.
- Containers are removed after each run; the sandbox itself caps output,
  blocks network, and hides host secrets (see `tests/test_sandbox.py`).

## Tests

```
python -m pytest tests/test_dataset_pipeline.py -v   # functional (no Docker)
python -m pytest -q                                  # full suite incl. sandbox
```

The pipeline tests drive a fake sandbox that behaves like
`sandbox.runner.execute` and never runs anything on the host. The end-to-end
Docker-backed run is exercised via `scripts/dataset_pipeline.py run`.