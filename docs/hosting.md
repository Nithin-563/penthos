# Hosting Penthos — Step-by-Step Guides

Penthos runs entirely on your own hardware. This page covers two ways to
demo or evaluate the project without paying for cloud GPUs.

---

## Option A — Hugging Face Spaces (Free CPU)

Hugging Face lets you run a Docker-based Gradio app for free. Because
Penthos uses MLX (Apple Silicon), a HF Space (Linux / x86) cannot run
`mlx_lm` directly. Two practical workarounds:

### A1 — Static demo with a pre-recorded output

This is the easiest way to show Penthos working — no GPU required.

```bash
# On your Mac
git clone https://github.com/Karthik-B-007/Penthos.git
cd Penthos
pip install gradio mlx-lm

# Record a short demo
python -c "
from mlx_lm import load, generate
model, tok = load('Qwen/Qwen3-4B-MLX-4bit')
prompt = tok.apply_chat_template([{'role':'system','content':'You are Penthos.'},{'role':'user','content':'Write a Python function to check if a number is prime.'}], tokenize=False, add_generation_prompt=True)
print(generate(model, tok, prompt=prompt, max_tokens=512))
" > demo_output.txt

# Build a Gradio app that shows the output
cat > app.py << 'EOF'
import gradio as gr
with open("demo_output.txt") as f:
    demo = f.read()
def respond(msg):
    return demo  # pre-recorded for demo
gr.Interface(fn=respond, inputs="text", outputs="text", title="Penthos Demo").launch()
EOF
```

Then push to a HF Space:

1. Go to [huggingface.co/new-space](https://huggingface.co/new-space)
2. Select **Gradio** as the SDK, **CPU Basic** as the hardware
3. Name it `penthos-demo`
4. Push `app.py` and `demo_output.txt` to that repo

### A2 — Full Penthos with Colab backend

If you want a live model on a HF Space, you can point it at a Colab
runtime running the real Penthos backend (see Option B below) via a
gradio Client connection.

---

## Option B — Google Colab (Free T4 GPU)

Colab's free tier includes a T4 GPU. This lets Penthos run with its full
tool loop and streaming output.

### Step 1 — Open a new Colab notebook

Go to [colab.research.google.com](https://colab.research.google.com/) and
create a **GPU** notebook (Runtime → Change runtime type → T4 GPU).

### Step 2 — Install dependencies

```python
!git clone https://github.com/Karthik-B-007/Penthos.git
%cd Penthos
!pip install -r requirements.txt
```

### Step 3 — Download the model

```python
from huggingface_hub import snapshot_download
snapshot_download(
    "Qwen/Qwen3-4B",
    local_dir="models/qwen3-4b",
    local_dir_use_symlinks=False,
)
```

### Step 4 — Launch the Gradio UI

```python
!python inference/chat.py --share
```

The `--share` flag gives you a public URL you can open in any browser.

### Step 5 — Optional: launch the agent chat

```python
!python inference/agent_chat.py
```

This starts the interactive REPL in the Colab terminal (View → Terminal).

---

## Option C — Docker (Local or Remote)

```bash
docker build -f docker/Dockerfile.sandbox -t penthos-sandbox:python . && \
docker build -f docker/Dockerfile.sandbox-node -t penthos-sandbox:node . && \
docker build -f docker/Dockerfile.sandbox-typescript -t penthos-sandbox:typescript . && \
docker build -f Dockerfile -t penthos .
docker run -p 7860:7860 penthos
```

Open `http://localhost:7860` in your browser.

---

## Option D — Bare Metal (macOS)

Best for development and daily use on Apple Silicon.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python inference/chat.py
```

---

## Hardware Requirements

| Option | GPU Required | Model Size | Quality |
|--------|-------------|------------|---------|
| HF Spaces (static demo) | No | N/A | Pre-recorded |
| Google Colab (free) | T4 (16 GB) | 4-bit Qwen3-4B (~2.5 GB) | Full |
| Docker | No | 4-bit Qwen3-4B (~2.5 GB) | Full |
| Bare Metal (macOS) | Apple Silicon (≥16 GB) | 4-bit Qwen3-4B (~2.5 GB) | Full |

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `mlx_lm` not found | Make sure you are running on macOS with Apple Silicon |
| Colab OOM | Reduce `MAX_TOKENS` in `inference/prompt.py` or use a smaller model |
| Docker sandbox fails | Ensure Docker daemon is running: `docker ps` |
| Agent loops forever | The new loop cap (6 iterations) should prevent this; if it persists, file an issue |
