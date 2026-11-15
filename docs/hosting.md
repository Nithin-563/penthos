# Hosting Pari — free options, compared

Pari is your model. Everything on this page runs **your own weights** on
hardware you control: there is no API key, no provider account, and nothing here
forwards your prompts to somebody else's model. What changes between options is
where the compute lives and how long it stays awake.

Quotas below were checked in November 2026 and free tiers change often — verify
on each provider's own page before committing.

---

## The short version

| Option | What you get free | Runs on | Keep it awake? | Best for |
| --- | --- | --- | --- | --- |
| Your own Mac (MLX) | Unlimited | Your hardware | Yes, while the laptop is on | Daily use, fastest path |
| Google Colab (T4) | ~Unpublished GPU allowance | 16 GB T4 | No, 12 h max + idle kill | GPU bursts, demos |
| Kaggle Notebooks | 30 GPU h/week | P100 or 2×T4 | No, 12 h sessions | More GPU hours than Colab |
| Lightning AI Studio | 1 CPU Studio + ~30 credits | CPU 24/7, GPU by credit | CPU yes (4 h restarts) | Always-on-ish testing |
| Oracle Cloud Always Free | 2 OCPU / 12 GB ARM | CPU only | Yes, 24/7 | A box that stays up |
| Hugging Face Spaces | Static free; 2 ZeroGPU Gradio Spaces | Shared GPU | No, sleeps | A public demo page |
| Modal Starter | $30 credit/month | Serverless GPU | No, scales to zero | Occasional runs |
| GitHub Codespaces | 60 core-hours/month | 2-core / 8 GB CPU | No, auto-stops | Editing and light tests |
| Your PC + tunnel | Unlimited | Your hardware | Yes | A private always-on endpoint |

**Honest summary:** no free tier is an always-on GPU service. Use your own
machine for real work, Kaggle/Colab for GPU bursts, and Oracle or Lightning for
a host that stays up.

---

## Why the Mac path is different

`inference/chat.py` and `inference/agent_chat.py` use MLX, which is Apple
Silicon only. On Linux GPU hosts (Colab, Kaggle, Lightning, Oracle, Spaces) run
the weights through `transformers` or `llama.cpp` instead. The model files are
standard weights — only the runtime changes.

```bash
# Apple Silicon (this repo's supported path)
pip install -r requirements.txt
python inference/chat.py

# Linux / GPU host, PyTorch runtime
pip install torch transformers accelerate
python - <<'PY'
from transformers import AutoModelForCausalLM, AutoTokenizer
model_id = "YOUR/PARI-WEIGHTS"          # or a local path
tok = AutoTokenizer.from_pretrained(model_id)
model = AutoModelForCausalLM.from_pretrained(model_id, device_map="auto")
text = tok.apply_chat_template(
    [{"role": "user", "content": "Write a Rust LRU cache with tests."}],
    tokenize=False, add_generation_prompt=True,
)
out = model.generate(**tok(text, return_tensors="pt").to(model.device), max_new_tokens=1024)
print(tok.decode(out[0][len(tok(text)["input_ids"]):], skip_special_tokens=True))
PY
```

For CPU-only hosts, `llama.cpp` is far faster than PyTorch. Convert once:

```bash
python convert_hf_to_gguf.py path/to/pari-weights --outfile pari-q4.gguf --outtype q4_k_m
./llama-cli -m pari-q4.gguf -p "Write a Python CLI that renames photos by date." -n 1024
```

There is no service call in any of this: the weights load into the process you
started.

---

## Calling Pari over local HTTP

The repo includes a small wrapper (`inference/server.py`) so your own tools, a
browser UI or a script can talk to the model. It loads your local weights and
serves them; it never forwards a request to another model or provider. The
request/response shape is OpenAI-compatible only because that is the format
existing clients already speak.

```bash
# loopback only (the default) — nothing is reachable from outside this machine
python inference/server.py --port 8080

curl -s http://127.0.0.1:8080/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"messages":[{"role":"user","content":"write a 3D cube renderer"}],"stream":true}'
```

On a remote host (Colab, Kaggle, Lightning, Oracle), bind to `0.0.0.0` and add a
key, then reach it through a tunnel:

```bash
python inference/server.py --host 0.0.0.0 --port 8080 --api-key "$PARI_API_KEY"
cloudflared tunnel --url http://127.0.0.1:8080   # free quick tunnel
```

Rules that keep this safe: never expose the port without `--api-key`; keep the
quick-tunnel URL private (it is public, random and temporary); stop the server
when you are done. The server logs requests only in `--verbose` mode and never
logs prompt or completion content.

---

## Option A — Your own laptop (Apple Silicon, MLX)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python inference/chat.py
```

**Advantages**
- Fastest tokens per second of anything on this page, no quota, no queue.
- Private by construction: no network at all.
- Tools, sandbox, `/build`, and the agent loop all work.
- Costs nothing beyond electricity, forever.

**Disadvantages**
- macOS with Apple Silicon only (MLX).
- Not reachable from the internet unless you add a tunnel.
- Uses your laptop's RAM and battery while running.

---

## Option B — Google Colab, free T4

Create a notebook, set Runtime → Change runtime type → T4 GPU.

```python
!git clone https://github.com/Nithin-563/penthos.git
%cd penthos
!pip install torch transformers accelerate
# then run the transformers snippet above with your weights
```

To show a UI, run Gradio in the notebook and use the public share link it
prints:

```python
!pip install gradio
# write a small app.py that loads the model once, then:
!python app.py --share
```

**Advantages**
- Free 16 GB T4 GPU, quick to start, nothing to install locally.
- Notebook + Drive workflow is convenient for experiments.
- Gradio's share link gives you a browser UI without any hosting account.

**Disadvantages**
- Free GPU allowance is unpublished; you can be queued or refused.
- 12-hour session ceiling, idle timeouts, and the runtime dies when you close
  the tab unless it is actively executing.
- The share link is temporary and changes per session.
- GPU machine is wiped between sessions: reinstall and re-download weights each
  time unless you cache them on Drive.

---

## Option C — Kaggle Notebooks

A Kaggle notebook with a GPU accelerator is the best free GPU allowance
available: **30 hours per week**, one P100 or two T4s, 29 GB RAM, 20 GB of
persistent `/kaggle/working`, and 12-hour sessions.

```python
!pip install transformers accelerate -q
# same transformers load as above; save weights under /kaggle/working
```

You can run a Gradio share link from a notebook, or expose a local port with a
Cloudflare quick tunnel (`cloudflared tunnel --url http://127.0.0.1:7860`).

**Advantages**
- Most free GPU hours of any mainstream option, resets weekly.
- "Save & Run All" keeps executing after you close the browser.
- Persistent 20 GB working directory for weights and outputs.
- Free TPU quota too (20 h/week), if you port to JAX.

**Disadvantages**
- Notebook environment, not a server: no always-on HTTP endpoint of your own.
- Interactive sessions idle out (about 20 minutes) and GPU access queues at
  busy times.
- Tunnels are temporary and rate-limited on free plans.
- Model weights must be re-fetched for each new session unless stored in
  `/kaggle/working` or a Kaggle Dataset.

---

## Option D — Lightning AI Studio

One free CPU Studio that runs 24/7 (with a forced restart every 4 hours), plus
up to about 30 credits for GPU time (roughly 75 T4 hours at $0.55/h).

```bash
# inside the Studio terminal
git clone https://github.com/Nithin-563/penthos.git && cd penthos
pip install -r requirements.txt        # MLX won't work here: use llama.cpp or torch
python inference/chat.py               # only after switching the runtime
```

**Advantages**
- A real Linux box with a persistent disk, SSH, and VS Code in the browser.
- CPU Studio is free around the clock, which makes it a decent private host for
  a tunnel.
- GPU hours cost credits only, no subscription required.

**Disadvantages**
- 4-hour restart on the free tier; long jobs need checkpointing.
- GPU time is a finite credit balance, not a recurring free quota.
- Free tier runs one Studio at a time.

---

## Option E — Oracle Cloud Always Free (ARM VM)

2 Ampere A1 OCPUs and 12 GB RAM for free indefinitely (1,500 OCPU-hours and
9,000 GB-hours per month), plus 200 GB storage and 10 TB egress.

```bash
sudo apt install -y build-essential cmake git
git clone https://github.com/ggerganov/llama.cpp && cd llama.cpp
cmake -B build && cmake --build build -j
./build/bin/llama-cli -m pari-q4.gguf -p "Explain this stack trace" -n 512
```

**Advantages**
- Free, genuinely 24/7, with a public IP and no sleeping.
- 12 GB RAM comfortably holds a 4-bit 4B model.
- 10 TB/month egress is far beyond anything a personal demo needs.
- Full root: cron, systemd, a tunnel, whatever you want.

**Disadvantages**
- CPU inference only: expect a few tokens per second, not chat speed.
- Capacity errors in popular regions are common; retry or pick another region.
- Card required for identity verification.
- Idle instances can be reclaimed; the free ARM allowance was cut in 2026.

---

## Option F — Hugging Face Spaces

Free accounts can host **static** Spaces and up to **two Gradio Spaces on
ZeroGPU** (shared GPU, about 5 minutes of GPU per day, sleeps when idle).
Creating a normal CPU Gradio or Docker Space now needs a paid plan.

**Advantages**
- Zero-ops public demo page with a real URL — good for showing Pari off.
- ZeroGPU is a real GPU when your function runs, free.
- Git push to deploy; no server administration.

**Disadvantages**
- The daily GPU quota is minutes, not hours; 5 min/day on a free account.
- Spaces sleep, so the first request after idle waits for a cold start.
- Not a private or reliable endpoint; not suited to real workloads.
- Gradio-only for the free GPU path.

---

## Option G — Modal Starter

$30 of compute credits every month, serverless GPUs billed per second, 1 TiB
free egress.

```python
# modal_app.py — runs YOUR weights on Modal's GPUs
import modal
app = modal.App("pari")
image = modal.Image.debian_slim().pip_install("torch", "transformers", "accelerate")

@app.function(image=image, gpu="T4", timeout=900)
def generate(prompt: str) -> str:
    from transformers import AutoModelForCausalLM, AutoTokenizer
    ...  # load your weights, generate, return text
```

**Advantages**
- Real GPU for pennies per run; scales to zero, so idle costs nothing.
- Free monthly credit is enough for hundreds of short generations.
- Reproducible Python deployment, no machine to babysit.

**Disadvantages**
- $30/month cap, then you pay; big models or long contexts burn it fast.
- Cold starts of tens of seconds on T4.
- You write and maintain the app; no free always-on CPU.

---

## Option H — GitHub Codespaces

60 core-hours per month free on a 2-core, 8 GB machine.

**Advantages**
- Instant dev environment that matches the repo; edit and test from anywhere.
- Good for developing Pari, running the unit tests, and small CPU inferences.
- No local install.

**Disadvantages**
- 8 GB RAM and no GPU: 4-bit 4B inference is slow, and large contexts may OOM.
- Stops after inactivity and the monthly hours run out quickly.
- Not a hosting platform; ports are private to your session.

---

## Option I — Your own PC + a free tunnel

Run Pari locally and expose it with Cloudflare Tunnel (free quick tunnels) or
Tailscale Funnel (free tier). You get a real URL pointing at your own machine.

**Advantages**
- Full speed of your own GPU/CPU; unlimited use.
- Private: the model never leaves your hardware.
- Free and works behind NAT, no port forwarding.

**Disadvantages**
- Your machine must stay on and online; laptop sleep kills it.
- Quick tunnel URLs are random and change on restart (a free Cloudflare account
  plus a domain fixes that).
- Free tunnels are rate-limited and not meant for heavy public traffic.

---

## Options that look free but are not

- **Google Cloud e2-micro** — 1 GB RAM. A 4-bit 4B model needs roughly 2.5–3 GB
  just for weights. It will not run; do not plan around it.
- **Render / Railway / Fly.io free tiers** — 256–512 MB of RAM. Same problem.
- **Hugging Face Inference Endpoints, Replicate, Together, Groq** — these serve
  their models on their hardware. They are not you hosting Pari.
- **Paperspace free M4000** — 6-hour sessions, queueing, 5 GB storage, and
  capacity is frequently unavailable; workable for a demo, not a host.

---

## Choosing

- **Just want to use Pari every day:** your own Mac. Nothing else comes close.
- **Need GPU hours for free:** Kaggle first, Colab second.
- **Need something that stays online:** Oracle Always Free (CPU) or a Lightning
  CPU Studio, with a tunnel if it must be public.
- **Need to show it to someone:** a Gradio share link from Colab/Kaggle, or a
  free ZeroGPU Space.

## Troubleshooting

| Problem | Fix |
| --- | --- |
| `mlx_lm` not found | MLX is macOS/Apple Silicon only; use `transformers` or `llama.cpp` on Linux |
| Out of memory on a 16 GB GPU | Use a 4-bit GGUF build and cap context at 4k |
| Colab/Kaggle dies mid-run | Sessions are time- and idle-limited; checkpoint output to persistent storage |
| CPU host feels slow | Expected: a 4B model on CPU runs at a few tokens per second; quantize to q4_k_m |
| Tunnel URL changed | Quick tunnels are ephemeral; use a named tunnel with your own domain |
