"""Interactive Penthos chat.

Runs the local Penthos model with the shared Penthos system prompt,
chain-of-thought, tuned sampling, a guarded tool layer (web search, web
fetch, files, shell, code search, git, sandboxed test execution), automatic
file output for generated code, and Penth text blocks that continue long
outputs seamlessly past the per-chunk token limit.

Commands: /quit, /reset, /tools
"""

from mlx_lm import load, stream_generate
from mlx_lm.generate import make_sampler

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from agent.core import PenthosAgent
from inference.loop_kit import (
    auto_save_code,
    continue_penth_blocks,
    drive_tool_loop,
    maybe_wrap_code_prompt,
)
from inference.prompt import (
    COMPANY,
    CREATOR,
    ENABLE_THINKING,
    MAX_TOKENS,
    MODEL,
    MODEL_DISPLAY,
    PENTHOS_SYSTEM_PROMPT,
    TEMP,
    TOP_P,
    apply_chat,
)
from inference.security import Guard

MAX_PENTH_BLOCKS = 6
AUTO_SAVE_MIN_CHARS = 3000
OUTPUTS_DIR = "Penthos/outputs"

print(f"Loading {MODEL_DISPLAY}...")
model, tokenizer = load(MODEL)
agent = PenthosAgent(".")
guard = Guard()

print(f"{MODEL_DISPLAY} by {COMPANY} · created by {CREATOR}")
print("Commands: /quit, /reset, /tools\n")


def generate(messages: list[dict], max_tokens: int = MAX_TOKENS) -> str:
    prompt = apply_chat(messages, tokenizer, thinking=ENABLE_THINKING)
    sampler = make_sampler(temp=TEMP, top_p=TOP_P)
    output = ""
    for response in stream_generate(
        model,
        tokenizer,
        prompt=prompt,
        max_tokens=max_tokens,
        sampler=sampler,
    ):
        text = response.text
        output += text
        print(text, end="", flush=True)
    print()
    return output


def run_tool_calls(messages: list[dict], user_text: str) -> None:
    """Drive the observe -> act -> verify loop until the model answers.

    History is mutated in place: the user turn and the final assistant answer
    are both left in ``messages`` (read ``messages[-1]`` afterwards). All the
    robustness lives in :func:`loop_kit.drive_tool_loop` so chat.py and
    agent_chat.py behave identically.
    """
    drive_tool_loop(messages, user_text, generate, agent)


messages = [
    {"role": "system", "content": PENTHOS_SYSTEM_PROMPT},
]

while True:
    try:
        query = input(">> ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        break

    if not query:
        continue

    if query == "/quit":
        break

    if query == "/reset":
        messages = [{"role": "system", "content": PENTHOS_SYSTEM_PROMPT}]
        print("Chat reset.\n")
        continue

    if query == "/tools":
        for tool in agent.tool_descriptions():
            print(f"- {tool['name']}: {tool['description']}")
        continue

    blocked, reason = guard.check_input(query)
    if blocked:
        print(guard.refusal(reason) + "\n")
        continue

    print()
    run_tool_calls(messages, maybe_wrap_code_prompt(query))

    output = messages[-1]["content"] if messages else ""
    if not output.strip():
        messages.pop()
        continue

    # Continue long outputs in numbered Penth blocks.
    if len(tokenizer.encode(output)) >= MAX_TOKENS:
        output = continue_penth_blocks(
            messages, output, generate, tokenizer,
            MAX_PENTH_BLOCKS, MAX_TOKENS,
        )
        messages[-1]["content"] = output

    output = guard.sanitize_output(output)
    messages[-1]["content"] = output

    # Generated code gets written to disk instead of flooding the terminal.
    auto_save_code(output, AUTO_SAVE_MIN_CHARS, OUTPUTS_DIR)
    print()