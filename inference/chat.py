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
from agent.protocol import parse_tool_call, tool_prompt
from inference.loop_kit import maybe_wrap_code_prompt
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
)
from inference.security import Guard

MAX_TOOL_CALLS = 6
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
    prompt = tokenizer.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=True,
        enable_thinking=ENABLE_THINKING,
    )
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


def run_tool_calls(messages: list[dict]) -> str:
    """Drive the observe -> act -> verify loop until the model answers."""
    ctx_idx = len(messages)
    messages.append({"role": "user", "content": tool_prompt(agent.tool_descriptions())})

    for _ in range(MAX_TOOL_CALLS):
        output = generate(messages)
        call = parse_tool_call(output)

        if call is None:
            for index in range(len(messages) - 1, ctx_idx - 1, -1):
                del messages[index]
            return output

        # Keep the tool-call history in context, but drop the tool sheet.
        for index in range(len(messages) - 1, ctx_idx - 1, -1):
            del messages[index]

        tool = agent.tools.get(call["name"])
        if tool is None:
            messages.append({"role": "assistant", "content": output})
            messages.append({"role": "user", "content": f"Unknown tool: {call['name']}."})
            continue

        if tool.requires_confirmation:
            confirm = input(
                f"\n[Allow {call['name']}({call['arguments']})? y/N] "
            ).strip().lower()
            if confirm not in ("y", "yes"):
                messages.append({"role": "assistant", "content": output})
                messages.append({"role": "user", "content": "User declined this action."})
                continue

        print(f"\n[Penthos → {call['name']}]", flush=True)
        try:
            result = agent.execute_tool(call["name"], **call["arguments"])
        except Exception as exc:
            result = f"Tool execution failed: {exc}"

        if isinstance(result, dict):
            # Trim long tool payloads so output never floods context.
            for key in ("stdout", "stderr", "content", "result", "message"):
                if isinstance(result.get(key), str) and len(result[key]) > 20000:
                    result[key] = f"[trimmed] ... {result[key][-20000:]}"
            failed = result.get("success") is False
            result_text = str(result)
        else:
            failed = False
            result_text = str(result)
        print(f"[Tool {'OK' if not failed else 'FAILED'}]")

        messages.append({"role": "assistant", "content": output})
        messages.append({"role": "user", "content": f"\n\n<tool_result>{result_text}\n</tool_result>"})

    # Tool budget exhausted: ask once more for a plain final answer.
    output = generate(messages)
    return output


def continue_penth_blocks(messages: list[dict], initial: str) -> str:
    """Continue an output that hit the token cap in numbered Penth blocks."""
    full = initial
    block = 1
    while block < MAX_PENTH_BLOCKS:
        messages.append({"role": "assistant", "content": initial})
        messages.append({
            "role": "user",
            "content": (
                f"Your previous output was cut off by the token limit. "
                f"Continue the exact same document from exactly where it "
                f"stopped. Do not repeat earlier text, do not label the "
                f"section, just continue writing seamlessly. "
                f"[Penth #{block + 1}]"
            ),
        })
        print(f"\n[Penth #{block + 1}]", flush=True)
        continuation = generate(messages)
        messages.pop()
        messages.pop()

        if not continuation.strip():
            break
        full += continuation

        # The model finished when its turn did not hit the cap again.
        if len(tokenizer.encode(continuation)) < MAX_TOKENS:
            break
        initial = continuation
        block += 1

    if block >= MAX_PENTH_BLOCKS:
        print(f"\n[Reached the limit of {MAX_PENTH_BLOCKS} Penth blocks.]")
    return full


def auto_save_code(output: str) -> None:
    """Save large fenced code blocks to a file so the terminal stays clean."""
    import re
    from datetime import datetime, timezone
    from pathlib import Path

    blocks = re.findall(r"```(?:([a-zA-Z0-9_]+))?\s*\n(.*?)```", output, flags=re.DOTALL)
    large = [b for b in blocks if len(b[1]) >= AUTO_SAVE_MIN_CHARS]
    if not large:
        return

    lang, code = large[-1]
    ext = {
        "python": "py", "py": "py", "typescript": "ts", "ts": "ts",
        "javascript": "js", "js": "js", "node": "js", "html": "html",
        "css": "css", "json": "json", "bash": "sh", "shell": "sh",
    }.get(lang, "txt")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    path = Path(".") / OUTPUTS_DIR / f"penthos_{stamp}.{ext}"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(code, encoding="utf-8")
    print(f"\n[saved {len(code)} chars of code to {path} — cleaner to open than the terminal]")


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

    messages.append({"role": "user", "content": maybe_wrap_code_prompt(query)})

    print()
    output = run_tool_calls(messages)

    if not output.strip():
        messages.pop()
        continue

    # Continue long outputs in numbered Penth blocks.
    if len(tokenizer.encode(output)) >= MAX_TOKENS:
        output = continue_penth_blocks(messages, output)

    output = guard.sanitize_output(output)

    # Generated code gets written to disk instead of flooding the terminal.
    auto_save_code(output)

    messages.append({"role": "assistant", "content": output})
    print()