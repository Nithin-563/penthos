# Penthos

A small, open-source coding AI and coding agent built to punch far above its
weight class. It runs entirely on one laptop, costs nothing to operate, and
is being improved continuously with the goal of competing with the leading
closed models.

Penthos is made by **Deoid** and was created, designed, and run by its founder
**K Nithin Reddy**.

## Why it exists

Most capable models are big, closed, and expensive. Penthos takes the opposite
path:

- **Small.** It fits comfortably in memory (a few gigabytes of weights) and
  runs in real time on a single Mac with Apple Silicon, GPU or not.
- **Cheap.** No API keys, no per-token bills, no hosting fees. Run it forever
  for the price of the electricity.
- **Open.** The weights recipe, the training data pipeline, the evaluation
  harness, and every script that built Penthos are in this repository.
- **Honest to its identity.** Penthos presents itself only as Penthos by
  Deoid. It is built on the permissively licensed Qwen3-4B open-weights base,
  and at inference time it is never prompted, told, or encouraged to claim any
  other identity.

## What it can do

- Chat with a real working model: `python inference/chat.py`
- Autonomous coding agent with tools for files, shell, code search, git, and
  sandboxed tests: `python inference/agent_chat.py`
- Search the web **without any API key** through an engine fallback chain
  (DuckDuckGo lite/html, Brave, Bing, Wikipedia), verified end to end.
- Run code and tests in a disposable, network-isolated Docker sandbox instead
  of trusting the model's output on your machine.
- Continue its own long answers seamlessly past the per-call token budget
  ("Penth blocks"), so long explanations and big code outputs don't get cut.
- Guard against prompt injection, jailbreak attempts, and accidental secret
  leakage, scrubbing API keys, bearer tokens, and private keys.
- Automatically save any large code block it writes to `Penthos/outputs/`.

## What's in the repo

```
agent/        Agent core: tools, registry, protocol, memory, repository intelligence
bench/        Benchmark suite builder, generation, and grading
inference/    Chat entry points, shared prompt/sampling config, security guards
evaluation/   The benchmark harness and result history
datasets/     Candidate tasks, verified records, MLX training splits
scripts/      Self-teacher distillation + dataset folding utilities
tools/        Web, shell, filesystem, code search, git tool implementations
sandbox/      Isolated Docker test execution
training/     LoRA fine-tune configs
adapters/     Fine-tuned adapter weights
```

## Quick start

```bash
python3 -m venv .venv
.venv/bin/pip install -U pip
.venv/bin/pip install mlx-lm mlx docker pytest rich tqdm safetensors huggingface_hub
.venv/bin/python inference/chat.py          # plain chat
.venv/bin/python inference/agent_chat.py    # chat + tools + sandbox
```

First run downloads the ~2.2 GB 4-bit model weights once, then everything is
local. The chat accepts `/quit`, `/reset`, and `/tools`.

## Training Penthos further

This repository contains a full fine-tuning path with no data-license doubts:
the model teaches itself. `scripts/self_teacher.py` generates a batch of task
rows, actually runs or rubrics each one, keeps the correct generations, and
writes them out as training data. `scripts/make_mlx_data.py` splits the result
into train/valid/test, and the LoRA config in `training/configs/` fine-tunes it.

Experiments so far:

- B — base model with thinking enabled: **23/26** on the verified suite.
- C — LoRA on a too-small batch of records: **14/26** and a clear lesson in
  catastrophic forgetting. The proper distillation dataset is the current work.

## How it's measured

`evaluation/run_benchmark.py` runs a 51-task suite spanning agentic coding,
algorithm problems, debugging, reasoning, security, general chat, and
software engineering. Each task is graded either by executing the model's code
in an isolated sandbox or by rubric. Results are kept in `evaluation/results/`.

## Roadmap

- Fine-tune on the distilled dataset and close the gap to (and then past) the
  leading closed models at a fraction of the cost.
- Expand the verified task suite every week.
- Keep improving the free, keyless, resilient tooling around the model.

## Environment

Tested on macOS with Apple Silicon and 16 GB RAM. Docker Desktop is used for
the sandboxed test tool. Python 3.12, MLX, and a few small utilities.

## License

MIT — the code in this repository is free to use, modify, and ship. The base
model weights and any model weights trained from them are distributed under
their own respective terms (contributors, see the acknowledements in
`training/configs/`).