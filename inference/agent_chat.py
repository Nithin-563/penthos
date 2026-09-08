"""Interactive Penthos agent chat.

Connects the local Penthos model to the Penthos Agent Core with the shared
Penthos system prompt, chain-of-thought, tuned sampling, a guarded tool layer
(web search, web fetch, files, shell, code search, git, sandboxed test
execution), automatic file output for generated code, Penth blocks that
continue long outputs seamlessly past the per-chunk token limit, and a bounded
tool loop that refuses to loop forever or repeat the exact same failed call.

Commands: /quit, /reset, /tools
"""

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from mlx_lm import load, stream_generate
from mlx_lm.generate import make_sampler

from agent.core import PenthosAgent
from agent.protocol import arg_schema
from inference.loop_kit import (
    auto_save_code,
    continue_penth_blocks,
    drive_tool_loop,
    maybe_wrap_code_prompt,
    trim_context,
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
AGENT_MAX_MSGS = 14


def generate(messages: list[dict]) -> str:
    prompt = apply_chat(messages, tokenizer, thinking=ENABLE_THINKING)
    sampler = make_sampler(temp=TEMP, top_p=TOP_P)
    output = ""
    for response in stream_generate(
        model,
        tokenizer,
        prompt=prompt,
        max_tokens=MAX_TOKENS,
        sampler=sampler,
    ):
        text = response.text
        output += text
        print(text, end="", flush=True)
    print()
    return output


def run_tool_calls(messages: list[dict], user_text: str) -> None:
    """Drive the observe -> act -> verify loop until the model answers.

    Robustness lives in :func:`loop_kit.drive_tool_loop`, shared with chat.py:
    tool results are never duplicated in history, partial/cut-off and malformed
    tool calls are nudged instead of silently dropped, repeated failed calls
    warn then stop, unknown tools and invalid arguments are explained, and the
    risky tools require confirmation.
    """
    drive_tool_loop(messages, user_text, generate, agent)


print(f"Loading {MODEL_DISPLAY}...")
model, tokenizer = load(MODEL)
agent = PenthosAgent(".")
guard = Guard()

SYSTEM_MESSAGE = {"role": "system", "content": PENTHOS_SYSTEM_PROMPT}
messages: list[dict] = [dict(SYSTEM_MESSAGE)]

print(f"\n{MODEL_DISPLAY} by {COMPANY} · created by {CREATOR}")
print("Commands: /quit, /reset, /tools\n")

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
        messages = [dict(SYSTEM_MESSAGE)]
        print("Chat reset.\n")
        continue

    if query == "/tools":
        for tool in agent.tools.list():
            schema = arg_schema(tool.function)
            args = f"  args: {json.dumps(schema)}" if schema else ""
            print(f"- {tool.name}: {tool.description}{args}")
        continue

    blocked, reason = guard.check_input(query)
    if blocked:
        print(guard.refusal(reason) + "\n")
        continue

    print()
    run_tool_calls(messages, maybe_wrap_code_prompt(query))

    output = messages[-1]["content"] if messages else ""
    if not output.strip():
        continue

    if len(tokenizer.encode(output)) >= MAX_TOKENS:
        output = continue_penth_blocks(
            messages, output, generate, tokenizer,
            MAX_PENTH_BLOCKS, MAX_TOKENS,
        )
        messages[-1]["content"] = output

    messages[-1]["content"] = guard.sanitize_output(output)
    output = messages[-1]["content"]

    auto_save_code(output, AUTO_SAVE_MIN_CHARS, OUTPUTS_DIR)
    messages[:] = trim_context(messages, max_msgs=AGENT_MAX_MSGS)
