"""Interactive Penthos agent chat.

Connects the local Penthos model to the Penthos Agent Core with the shared
Penthos system prompt and chain-of-thought enabled.
"""

from mlx_lm import load, stream_generate
from mlx_lm.generate import make_sampler

from agent.core import SYSTEM_PROMPT
from agent.loop import AgentLoop
from inference.prompt import (
    ENABLE_THINKING,
    MAX_TOKENS,
    MODEL,
    TEMP,
    TOP_P,
)


MAX_TOOL_CALLS = 8

model, tokenizer = load(MODEL)
agent = AgentLoop(".")

SYSTEM_MESSAGE = {
    "role": "system",
    "content": SYSTEM_PROMPT,
}

messages = [dict(SYSTEM_MESSAGE)]


def generate(messages):
    prompt = tokenizer.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=True,
        enable_thinking=ENABLE_THINKING,
    )

    sampler = make_sampler(
        temp=TEMP,
        top_p=TOP_P,
    )

    output = ""

    for response in stream_generate(
        model,
        tokenizer,
        prompt=prompt,
        max_tokens=MAX_TOKENS,
        sampler=sampler,
    ):
        print(response.text, end="", flush=True)
        output += response.text

    print()
    return output


print("Penthos by Deoid · created by K Nithin Reddy")
print("Type /quit to exit.")
print("Type /tools to inspect available tools.")
print("Type /reset to clear conversation.")
print()

while True:
    try:
        user_input = input("You: ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        break

    if not user_input:
        continue

    if user_input == "/quit":
        break

    if user_input == "/reset":
        messages = [dict(SYSTEM_MESSAGE)]
        print("Conversation reset.")
        continue

    if user_input == "/tools":
        for tool in agent.available_tools():
            print(f"- {tool['name']}: {tool['description']}")
        continue

    messages.append({
        "role": "user",
        "content": user_input + agent.build_tool_context(),
    })

    tool_calls = 0

    while tool_calls < MAX_TOOL_CALLS:
        output = generate(messages)

        call = agent.process_model_output(output)

        if call is None:
            break

        tool_calls += 1

        print(
            f"\n[Penthos → {call['name']}]"
        )

        result = agent.execute_model_tool_call(output)

        if result is None:
            break

        print(
            f"[Tool {'OK' if result['success'] else 'FAILED'}]"
        )

        messages.append({
            "role": "assistant",
            "content": output,
        })

        messages.append({
            "role": "user",
            "content": result["message"],
        })

    if tool_calls >= MAX_TOOL_CALLS:
        print("\n[Agent limit reached for this request.]")
