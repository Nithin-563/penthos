# Pari

A small, open-source coding AI and coding agent built to punch far above its
weight class. It runs entirely on one laptop, costs nothing to operate, and is
improved continuously with the goal of competing with the leading closed models.

**Pari is made by the Fubrio company.**

## Why it exists

Most capable models are big, closed, and expensive. Pari takes the opposite
path:

- **Small.** A few gigabytes of weights; runs in real time on a single Mac with
  Apple Silicon, GPU or not.
- **Cheap.** No API keys, no per-token bills, no hosting fees. Run it forever
  for the price of the electricity.
- **Open.** The weights recipe, the training data pipeline, the evaluation
  harness, and every script that built Pari are in this repository.
- **Honest to its identity.** Pari presents itself only as Pari by Fubrio, and
  is never prompted to claim any other identity.

## What it can do

- Chat with the model: `python inference/chat.py`
- Run it as a **local HTTP service** for your own tools and UIs:
  `python inference/server.py --port 8080` (see below).
- Autonomous coding agent with tools for files, shell, code search, git, and
  sandboxed tests: `python inference/agent_chat.py`
- **Build a whole project** from one request: `/build a Flask todo app with
  SQLite and tests` plans the files, writes each one, reviews its own work,
  rewrites what the review flags, and saves the project under `Pari/builds/`.
- **Domain playbooks** for web/UI, games and 3D graphics: the prompt detects the
  domain and injects the checklist that matters (breakpoints and contrast for
  web, fixed timestep and input buffering for games, matrix spaces and depth
  for 3D) before a line of code is written.
- **Category playbooks** for debugging, security, reasoning, engineering and
  agentic work: the procedure changes with the job — reproduce before editing,
  validate at the trust boundary, one hypothesis at a time.
- **Solve with verification** (`/solve <task>`): writes a pytest suite for the
  task, generates the implementation, runs both in the sandbox, and repairs the
  real failure it sees, up to three attempts.
- Search the web **without any API key** through an engine fallback chain
  (DuckDuckGo lite/html, Brave, Bing, Wikipedia), verified end to end.
- Run code and tests in a disposable, network-isolated Docker sandbox instead of
  trusting the model's output on your machine.
- Continue long answers seamlessly past the per-call token budget ("Pari
  blocks"), so long explanations and big code outputs are not cut off.
- Guard against prompt injection, jailbreak attempts, and accidental secret
  leakage, scrubbing API keys, bearer tokens, and private keys.
- Automatically save any large code block it writes to `Pari/outputs/`.

## What's in the repo

```
agent/        Agent core: tools, registry, protocol, memory, repository intelligence
inference/    Chat entry points, shared prompt/sampling, build pipeline, local HTTP
              wrapper, security guards
evaluation/   Benchmark harness and result history
datasets/     Candidate tasks, verified records, MLX training splits
scripts/      Self-teacher distillation, dataset folding, curated seed-pack builder
tools/        Web, shell, filesystem, code search, git tool implementations
sandbox/      Isolated Docker test execution
training/     LoRA fine-tune configs and the data pipeline
tests/        Unit tests for the protocol, tools, sandbox, datasets, build pipeline
docs/         Hosting guide and the model report
```

## Quick start

```bash
python3 -m venv .venv
.venv/bin/pip install -U pip
.venv/bin/pip install -r requirements.txt
.venv/bin/python inference/chat.py          # chat + tools
.venv/bin/python inference/agent_chat.py    # agent loop
```

First run downloads the ~2.2 GB 4-bit weights once, then everything is local.
The chat accepts `/quit`, `/reset`, `/tools`, and `/build <request>`.

## Serve it over local HTTP

`inference/server.py` exposes the model you already have on this machine. The
wire format is OpenAI-compatible so existing clients and playgrounds can point
at it, but every token is generated locally — there is no upstream provider and
no second model involved.

```bash
python inference/server.py --port 8080          # loopback only by default

curl -s http://127.0.0.1:8080/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"messages":[{"role":"user","content":"Build a 2D platformer in one file"}]}'
```

Endpoints: `GET /health`, `GET /v1/models`, `POST /v1/chat/completions`
(`"stream": true` for server-sent events). Pass `--api-key` (or set
`PARI_API_KEY`) to require a Bearer token, and only bind `0.0.0.0` behind a
tunnel you control — see [`docs/hosting.md`](docs/hosting.md).

## How quality is improved

A 4B-scale model does not get better by being asked harder; it gets better when
the work is broken into pieces it can actually hold, and when failures are
fed back instead of thrown away. Five mechanisms enforce that:

1. **A specification-first system prompt** (`inference/prompt.py`): restate the
   goal, fix the interfaces, implement, verify, report. Edge cases, security and
   complexity are explicit checkpoints, not afterthoughts.
2. **A code-task scaffold** (`build_code_prompt`): requirements → edge cases →
   design → implementation → tests → trace → check, applied automatically to
   long coding requests.
3. **Domain and category playbooks, plus reference shapes**: the request is
   routed twice — once by subject (web, game, 3D graphics) and once by kind of
   work (debugging, security, reasoning, engineering, agentic) — and both
   checklists are injected into the prompt. A 3D task and a 3D *bug* get
   different procedures. For web, game and 3D work the prompt also carries a
   compact structural exemplar, because few-shot examples transfer architecture
   to a small model better than instructions do.
4. **A multi-file build pipeline** (`inference/codegen.py`): plan the file list
   as JSON, generate one focused file per call against a shared contract, run
   static checks (empty files, placeholders, unbalanced brackets), ask the model
   to review its own project, regenerate flagged files once, then write the
   project to disk. Big requests stop depending on a single lucky generation.
5. **A generate → execute → repair loop, with pass@N**
   (`inference/verify_loop.py`, `/solve`, and the build pipeline's `run_checks`
   hook): the model's code is executed, the actual stderr/stdout is fed back,
   and it is asked to fix the root cause. `solve_best_of_n` samples several
   independent solutions first and keeps the first that passes — the cheapest
   real accuracy gain at this model size — then repairs the best failure. For
   tasks without tests, `best_of_n` scores samples instead. `/solve` uses two
   samples by default (`PARI_SOLVE_SAMPLES` to change it).

The benchmark harness (`evaluation/run_benchmark.py`) grades every change by
executing code in the sandbox or by rubric, so improvements are measured rather
than assumed. The suite now covers 56 tasks, including web layout, game-loop and
3D-pipeline prompts so those gains are visible in the numbers.

### The regression gate

Fine-tuning small models is where checkpoints silently get worse — in this
repo the LoRA runs scored 14-16/26 where the base scored 23/26. The gate fails a
candidate that does not beat the shipping run overall or that gives up any
category:

```bash
python -m evaluation.gate --baseline evaluation/results/b_improved \
                          --candidate evaluation/results/e3_lora
# exit 1, with the per-category table and the regressions named
```

Use it before adopting an adapter: `min_overall_delta` and
`max_category_regression` are set in `training/configs/pari-local.yaml`.

## Host it yourself

A full comparison of free ways to run Pari yourself — your own laptop, Colab,
Kaggle, Lightning AI, Oracle Cloud, Hugging Face Spaces, Modal, Codespaces —
with the advantages, disadvantages, and limits of each, is in
[`docs/hosting.md`](docs/hosting.md). Every option runs **your** weights; none of
them needs an API key or another AI provider.

## Training Pari further

Two curated packs supply the knowledge a small model usually lacks, both
hand-authored and both rebuilt from a script:

- `datasets/candidates/seed_coding_domains.jsonl`
  (`scripts/build_seed_coding_domains.py`) — web layout and accessibility, 2D
  game loops/collision/tilemaps, 3D transforms, projection and lighting, the
  1D/2D math behind animation and procedural content.
- `datasets/candidates/seed_core_categories.jsonl`
  (`scripts/build_seed_categories.py`) — one balanced set per category: coding,
  debugging, security, software engineering, reasoning, agentic and general
  chat, so a fine-tune does not overfit to code-only data.

Every executable record ships a passing pytest suite and is re-verified inside
the Docker pipeline before it can reach training; the knowledge records are
non-executable by design. `training/configs/pari-local.yaml` points at both
packs and lists the domain and category focus.

Beyond that, the model teaches itself. `scripts/self_teacher.py` generates a
batch of task rows, actually runs or rubrics each one, keeps the correct
generations, and writes them out as training data. `scripts/make_mlx_data.py` splits the result
into train/valid/test, and the LoRA config in `training/configs/pari-local.yaml`
fine-tunes it.

Experiments so far (on the verified 26-task subset, thinking on):

- B — base model with thinking enabled: **23/26** (the shipping configuration).
- C — LoRA on a too-small batch of records: **14/26**.
- E — LoRA on the full self-distilled dataset: **14/26**.
- E-2 — LoRA with lower learning rate: **14/26**.
- E-3 — LoRA on a cleaned mix with thinking exemplars: **16/26**, recovering
  reasoning and security categories.

Conclusion, honestly: the base model still beats every LoRA attempt so far on
long freeform generation. The distilled datasets are good data, but the
fine-tuned adapters collapse on the narrative tasks. Closing the gap needs a
verifier/RLHF approach, not more of the same distillation — details in
[`docs/final_report.md`](docs/final_report.md).

## How it's measured

`evaluation/run_benchmark.py` runs a 56-task suite spanning agentic coding,
algorithm problems, debugging, reasoning, security, general chat, and software
engineering. Each task is graded either by executing the model's code in an
isolated sandbox or by rubric. Results are kept in `evaluation/results/`.

## Roadmap

- Close the gap to (and then past) the leading closed models at a fraction of
  the cost, using verifier-guided training rather than more distillation.
- Expand the verified task suite every week.
- Keep improving the free, keyless, resilient tooling around the model.

## Environment

Tested on macOS with Apple Silicon and 16 GB RAM. Docker Desktop is used for the
sandboxed test tool. Python 3.12, MLX, and a few small utilities.

## License and attribution

MIT — the code in this repository is free to use, modify, and ship.

The weights are a fine-tune of a permissively licensed open-weights base. That
base's license and copyright notice continue to apply to the weights and to
anything trained from them; the base is not affiliated with Fubrio and does not
endorse Pari. See `MODEL_CARD.md` for the model card.
