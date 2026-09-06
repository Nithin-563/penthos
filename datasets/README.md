# Penthos Dataset

Penthos uses high-quality, verified training data.

## Dataset pipeline

raw
  ↓
synthetic
  ↓
verification
  ↓
verified / rejected
  ↓
training

The verified pipeline lives in `training/data_pipeline/` (see its
[README](../training/data_pipeline/README.md)) and is driven by
`scripts/dataset_pipeline.py`. All executable candidates are verified inside
the existing Docker sandbox; rejected examples never reach training data.

Directory layout:

- `candidates/` — seed candidates for the pipeline (see `seed_*.jsonl`)
- `generated/` — synthetic candidates produced by teachers / CLI tools
- `agentic/` — agentic trajectory candidates
- `raw/` — raw donated/assets material (not yet candidate-format)
- `synthetic/` — earlier synthetic material (pre-pipeline)
- `verified/` — pipeline output: `train|validation|test|verified.jsonl`
- `rejected/` — pipeline-rejected candidates by reason (`<reason>.jsonl`)
- `manifests/` — dataset manifests (`manifest_latest.json` + timestamped)

## Running the pipeline

```
python scripts/dataset_pipeline.py run
python scripts/dataset_pipeline.py validate
python scripts/validate_dataset.py datasets/verified/verified.jsonl --record
```

## Principles

- Prefer executable and verifiable coding tasks.
- Reject incorrect or untestable solutions.
- Include debugging and repository-level tasks.
- Include tool-use and agentic trajectories.
- Preserve reasoning when legally and technically appropriate.
- Never include secrets, credentials, or private data.