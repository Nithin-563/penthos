# Penthos — model fact sheet, evaluation, and hosting options

*Internal working report updated 2026-09-07. The fine-tune line is an active
experiment; the numbers below change as new experiments land.*

Penthos is a fully local, open-source coding AI made by **Deoid**
(created by **K Nithin Reddy**). It runs on one laptop, uses no API keys, and
is rebuilt continuously with the goal of competing with the leading closed
models at a fraction of their cost.

---

## 1. Model facts

| Property | Value |
| --- | --- |
| Architecture | Dense decoder-only, GQA (32 Q-heads / 8 KV-heads), 36 layers |
| Total parameters | 4.0B (3.6B non-embedding) |
| Context length | 32,768 native; 131,072 with YaRN |
| Weights format | MLX 4-bit quantized |
| On-disk size | ~2.0 GB |
| Runtime memory | ~2-3 GB at normal chat lengths; ~6-10 GB during long-sequence LoRA training |
| Hardware tested | Apple Silicon, 16 GB unified memory (MLX) |
| Vocab | Same as base; identity surfaced purely through Penthos's own system prompt and tooling |
| Public identity | Penthos by Deoid, created by K Nithin Reddy (never presents as the base or any provider) |

Decoding defaults: temperature 0.3 / top-p 0.9 in the interactive chat,
greedy (temperature 0.0) in the benchmark. Thinking (chain-of-thought) is on
by default and is what makes the base model strong on the suite below.

## 2. Evaluation

The Penthos benchmark suite currently holds **51 tasks** (8 baseline + 43
verified) spanning agentic coding, algorithms, debugging, reasoning, security,
general chat, and software engineering. Verdicts come from either running the
model's code in an isolated Docker sandbox or rubric-grading its answer.
**Experiment B** below used the 26-task "B-numbered" subset (8 baseline + 18
verified) shared across every run in this row of work so results are directly
comparable.

| Experiment | Adapter | Result (26 tasks) | Notes |
| --- | --- | --- | --- |
| B — base, thinking on | none | **23/26** (88%) | shipping config today; hardest for it: debug_001, seed-python-fizzbuzz-0002, challenge-lru-1003 |
| C — LoRA on 14 records | overfit tiny set | 14/26 | fixed 2 sandbox bugs, catastrophic freeform collapse (repetition) |
| E — LoRA on 165 self-distilled rows | raw distilled set (contaminated) | 14/26 | empty outputs everywhere; root-caused to thinking-scaffold contamination of training rows |
| E-2 — LoRA on 157 clean distilled rows | clean set | 14/26 | thinking off during distillation, LR 2e-6; reasoning 4/4, but long freeform tasks now emit empty scaffolds |
| E-3 — clean rows + thinking-mode exemplars for stalling tasks | clean + exemplar mix | 16/26 | fixed endpoint/passcmp regression; best adapter, still below B |

By-category, all five runs (verified numbers straight from each `report.json`):

| Category | B | C | E | E-2 | E-3 |
| --- | --- | --- | --- | --- | --- |
| agentic (2) | 2/2 | 0/2 | 2/2 | 0/2 | 0/2 |
| coding (8) | 6/8 | 6/8 | 6/8 | 4/8 | 4/8 |
| debugging (5) | 4/5 | 3/5 | 3/5 | 3/5 | 3/5 |
| general chat (1) | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 |
| reasoning (4) | 4/4 | 2/4 | 0/4 | 4/4 | 4/4 |
| security (4) | 4/4 | 2/4 | 2/4 | 2/4 | 3/4 |
| software engineering (2) | 2/2 | 0/2 | 0/2 | 0/2 | 1/2 |

The verdict is unambiguous: **the base model with thinking on (B, 23/26) is the
best configuration and stays the shipping one.** Every LoRA fine-tune so far —
regardless of data cleanliness or learning rate — degrades the long freeform
generation path (the fine-tuned adapter emits ` thinking\n\n response\n\n`
scaffolds with no content, or 0 tokens with thinking off), while the short
code/sandbox tasks survive. The winning line is a healthy data pipeline, not a
fine-tune: a self-teacher that distills verified, thinking-free completions has
made the *evaluation methodology* cleaner but cannot beat the base because
distilling a model's own output can never exceed the teacher. Exceeding B
requires a stronger generation source or reward-weighted selection (verifier
voting / RLHF-style tuning on sandbox-verified outcomes), not more distillation.

## 3. Context: how a 4B-scale model compares to the frontier

The base architecture behind Penthos (Qwen3-4B) publishes strong small-model
results; the 2507 thinking chip reports, e.g., MMLU-Pro 74.3, GPQA 66.7,
AIME25 82.7, and 5.9 on Humanity's Last Exam. The current frontier models land
roughly at MMLU-Pro ~89-90, GPQA ~93-94, and AIME25 ~100. So a 4B model fits on
a laptop and costs nothing to run, but there is a real capability gap to the
frontier that a 4B-parameter class simply has to be honest about. Penthos's
edge is being *good enough*, private, keyless, fully open, and improvable; its
benchmark line is trending up as the data pipeline gets healthier.

## 4. Free hosting options

Penthos is an MLX 4-bit model, so the simplest and truly free path is a Mac
with Apple Silicon (which is what the repo targets). For providers that don't
run MLX, the recommended port is a GGUF export (via `mlx_lm.convert`, which the
MLX ecosystem provides); a 4B Q4 GGUF runs on any of the free tiers below.

| Option | Type | Cost | Notes |
| --- | --- | --- | --- |
| Your own Mac | local | free, forever | MLX native, all scripts included; the primary target |
| Hugging Face Spaces (CPU, 16 GB) | cloud | free tier | needs GGUF + llama.cpp; slow but works, public link available |
| Google Colab free (T4 16 GB) | cloud GPU | free tier (~12 GPU h/wk) | llama-cpp-python or transformers; good for demos |
| Kaggle free | cloud GPU | free (~30 GPU h/wk) | P100/T4; solid for batch runs |
| Modal / Replicate / RunPod | cloud GPU | free credits, then paid | convenient spares for one-off demos, not permanent free hosting |

For a self-hosted, privacy-first setup, the Mac-local path is the only one with
zero external dependency and no data leaving the machine.

## 5. Storage & run instructions

First run downloads ~2.0 GB once (cached locally); after that everything is
offline. `inference/chat.py` is the chatting entry point,
`inference/agent_chat.py` adds the tool-driving agent loop
(files/shell/git/code-search/web/sandboxed tests), and
`evaluation/run_benchmark.py` reproduces every number in this document.

See `README.md` for the full quick start.