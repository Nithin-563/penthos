# Pari — model card

| | |
| --- | --- |
| **Name** | Pari |
| **Company** | Fubrio |
| **Kind** | Open-source coding AI and coding agent |
| **Weights** | 4-bit quantized fine-tune of a permissively licensed open-weights base |
| **Parameters** | ~4B |
| **Context** | 32,768 tokens native (131,072 with YaRN scaling) |
| **On-disk size** | ~2.0–2.5 GB |
| **Runtime memory** | ~2–3 GB for chat; ~6–10 GB while LoRA training |
| **Runtimes** | MLX (Apple Silicon), `transformers`, `llama.cpp` (GGUF) |
| **License** | Code: MIT. Weights: the base model's license terms apply |

## What it is

Pari is a small coding model plus the tooling around it: a chat loop, an agent
that can read and edit a repository, a sandbox for running generated code, a
multi-file build pipeline, and a benchmark harness. It is designed to run on one
laptop with no API keys and no per-token cost.

Pari's identity is its own: it presents itself only as Pari by Fubrio. The
open-weights base it was trained from is an implementation detail, and its
license continues to apply to these weights.

## Intended use

- Writing and editing code in many languages, and explaining it.
- Debugging: reading an error, locating the cause, fixing it, re-testing.
- Multi-file projects: `/build` plans a file list, writes each file against a
  shared contract, reviews itself, and verifies the result.
- Agentic work in a repository with tools for files, shell, search, git, and
  sandboxed tests.
- Learning and prototyping on hardware you already own.

## Not intended for

- Safety-critical, medical, legal, or financial decisions without human review.
- Unattended execution of generated code on a host that holds real secrets —
  use the sandbox.
- Anything requiring knowledge after its training cutoff without web lookup.

## Limitations

- At ~4B parameters it is well below frontier models on long, novel reasoning.
  It is strongest with a concrete, well-specified task and tools.
- It can invent APIs or library details. The system prompt and tools are built
  to force verification rather than trust.
- Long freeform generation degrades more than short code generation; the build
  pipeline exists specifically to avoid one huge generation.
- Non-English performance is not benchmarked here.

## Evaluation

`evaluation/run_benchmark.py` runs a 51-task suite across agentic coding,
algorithms, debugging, reasoning, security, general chat, and software
engineering. Executable tasks are graded by running the generated code in a
network-isolated Docker sandbox; freeform tasks are rubric-graded and saved for
manual review.

Current shipping configuration: base weights, thinking enabled — 23/26 on the
verified 26-task subset (88%). LoRA experiments so far peak at 16/26; see
`docs/final_report.md` for the honest breakdown.

## Training data

Self-distilled: the model generates task solutions, each is executed or
rubric-checked, and only correct generations are kept. Splits and manifests live
in `datasets/`. Adapters are produced with the LoRA config in
`training/configs/pari-local.yaml`.

## Ethical and legal notes

- Do not use Pari to generate malware or to attack systems you do not own.
- Generated code is not reviewed by a human before you run it; review it or use
  the sandbox.
- Redistribution must keep the base model's license and attribution notices.
