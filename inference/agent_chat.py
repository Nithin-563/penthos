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
from agent.protocol import (
    arg_schema,
    partial_tool_call,
    parse_tool_call,
    tool_prompt,
    tool_result,
)
from agent.tools import validate_arguments
from inference.loop_kit import auto_save_code, continue_penth_blocks, trim_context
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
AGENT_MAX_MSGS = 14


def generate(messages: list[dict]) -> str:
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

    All message appends happen here so the caller never doubles anything.
    Fixes applied compared to the original agent_chat.py:
    - Tool sheet is generated but never stored in messages (avoids prompt bloat).
    - A partial ``<tool_call`` that was cut off by the token cap gets one
      explicit chance to be finished instead of silently dropped.
    - Unknown/invalid arguments are caught and explained to the model instead of
      throwing a confusing TypeError.
    - If the model emits the exact same tool call it just tried and that call
      already failed, the loop warns once, and on the third identical call it
      stops instead of running in circles.
    - User confirmation is required for the same risky tools (shell, write,
      sandbox) that chat.py requires.
    - Tool execution errors print ``[Tool FAILED]`` instead of ``[Tool OK]``.
    """
    ctx_idx = len(messages)
    messages.append({"role": "user", "content": user_text})

    tool_sheet = tool_prompt(agent.tool_descriptions())
    last_call_key: str | None = None
    last_call_failed = False
    duplicate_warned = False
    partial_nudged = False

    for _ in range(MAX_TOOL_CALLS):
        # Build the prompt for this generation round WITHOUT storing the tool
        # sheet in the message history (the sheet would accumulate and degrade
        # every subsequent turn if left in).
        gen_messages = messages + [{"role": "user", "content": tool_sheet}]
        output = generate(gen_messages)

        call = parse_tool_call(output)

        if call is None:
            if partial_tool_call(output) and not partial_nudged:
                partial_nudged = True
                messages.append({"role": "assistant", "content": output})
                messages.append({
                    "role": "user",
                    "content": (
                        "Your tool call was cut off by the token limit. "
                        "Reply with ONLY the complete, closed "
                        '{"name":"...","arguments":{...}} JSON.'
                    ),
                })
                continue
            messages.append({"role": "assistant", "content": output})
            break

        tool = agent.tools.get(call["name"])

        if tool is None:
            messages.append({"role": "assistant", "content": output})
            messages.append({
                "role": "user",
                "content": (
                    f"Unknown tool: {call['name']}. "
                    f"Available tools: "
                    f"{', '.join(t.name for t in agent.tools.list())}. "
                    "Answer directly."
                ),
            })
            break

        call_key = json.dumps(
            {"name": call["name"], "args": call["arguments"]},
            sort_keys=True,
        )
        if call_key == last_call_key and last_call_failed:
            if not duplicate_warned:
                duplicate_warned = True
                messages.append({"role": "assistant", "content": output})
                messages.append({
                    "role": "user",
                    "content": (
                        "That exact tool call just failed — do not repeat it. "
                        "Fix the arguments or answer the question directly."
                    ),
                })
                continue
            messages.append({"role": "assistant", "content": output})
            break

        if tool.requires_confirmation:
            try:
                confirm = input(
                    f"\n[Allow {call['name']}({call['arguments']})? y/N] "
                ).strip().lower()
            except (EOFError, KeyboardInterrupt):
                confirm = "n"
            if confirm not in ("y", "yes"):
                messages.append({"role": "assistant", "content": output})
                messages.append({
                    "role": "user",
                    "content": "User declined this action.",
                })
                last_call_key = call_key
                last_call_failed = True
                continue

        unknown, missing = validate_arguments(tool, **call["arguments"])
        if unknown or missing:
            msg_parts = []
            if unknown:
                msg_parts.append(f"unexpected argument(s): {', '.join(unknown)}")
            if missing:
                msg_parts.append(
                    f"missing required argument(s): {', '.join(missing)}"
                )
            messages.append({"role": "assistant", "content": output})
            messages.append({
                "role": "user",
                "content": (
                    f"Tool '{call['name']}' failed validation — "
                    f"{'; '.join(msg_parts)}. "
                    "Try again or answer the question directly."
                ),
            })
            last_call_key = call_key
            last_call_failed = True
            continue

        print(f"\n[Penthos → {call['name']}]", flush=True)
        try:
            result = agent.tools.execute(call["name"], **call["arguments"])
        except Exception as exc:
            result = (
                f"Tool execution failed: {exc.__class__.__name__}: {exc}"
            )
            last_call_key = call_key
            last_call_failed = True
            print("[Tool FAILED]")
        else:
            if isinstance(result, dict):
                for key in ("stdout", "stderr", "content", "result", "message"):
                    val = result.get(key)
                    if isinstance(val, str) and len(val) > 20000:
                        result[key] = f"[trimmed] ... {val[-20000:]}"
                failed = result.get("success") is False
            else:
                failed = False
            last_call_failed = failed
            if failed:
                print("[Tool FAILED]")
            else:
                print("[Tool OK]")

        messages.append({"role": "assistant", "content": output})
        messages.append({
            "role": "user",
            "content": f"\n\n<tool_result>{result}\n</tool_result>",
        })
        last_call_key = call_key

    messages.pop(ctx_idx)          # remove the original user_text we just moved
    messages.pop(ctx_idx)          # remove the user sheet we injected

    # Restore the user text at the original position (before the assistant
    # answer) so the history stays logically clean.
    messages.insert(ctx_idx, {"role": "user", "content": user_text})


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
    run_tool_calls(messages, query)

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
