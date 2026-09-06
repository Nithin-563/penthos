from mlx_lm import load, stream_generate
from mlx_lm.generate import make_sampler

MODEL = "Qwen/Qwen3-4B-MLX-4bit"
MAX_TOKENS = 4096

print("Loading model...")
model, tokenizer = load(MODEL)

print("Penthos local inference")
print("Commands: /quit, /reset\n")

messages = []

while True:
    query = input(">> ")

    if query == "/quit":
        break

    if query == "/reset":
        messages = []
        print("Chat reset.\n")
        continue

    messages.append({
        "role": "user",
        "content": query,
    })

    prompt = tokenizer.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=True,
        enable_thinking=False,
    )

    print()

    generated = ""

    for response in stream_generate(
        model,
        tokenizer,
        prompt,
        max_tokens=MAX_TOKENS,
        sampler=make_sampler(0.2, 0.9),
    ):
        text = response.text
        generated += text
        print(text, end="", flush=True)

    print("\n")

    messages.append({
        "role": "assistant",
        "content": generated,
    })
