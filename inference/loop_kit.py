"""Shared helper functions for the interactive chat loops.

These are pure functions with no model load, no module-level globals, and no
import cycles, so both inference/chat.py and inference/agent_chat.py can import
them without triggering a heavy model download/load.

- trim_context: keep the system prompt, the original user task, and the latest
  messages, so long sessions never silently overflow the context window.
- continue_penth_blocks: continue an output cut off by the per-call token cap
  in numbered "Penth" blocks.
- auto_save_code: write large fenced code blocks to a file instead of flooding
  the terminal.
"""

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from agent.protocol import (
    looks_like_tool_call,
    parse_tool_call,
    partial_tool_call,
    tool_prompt,
)
from agent.tools import validate_arguments


def trim_context(messages, max_msgs=14, keep_first_user=True):
    """Trim message history to fit the model's context window.

    Always keeps: 1) the system message(s) and 2) the first real user request
    (the task anchor), so the agent does not forget what it was asked to do.
    The newest messages are always preserved in full.

    Mutating callers should rebind with ``messages[:] = trim_context(messages)``.
    """
    if len(messages) <= max_msgs:
        return messages

    system = [m for m in messages if m.get("role") in ("system", "developer")]
    rest = [m for m in messages if m.get("role") not in ("system", "developer")]

    anchor = None
    if keep_first_user:
        for index, m in enumerate(rest):
            if m.get("role") == "user" and "<tool_result>" not in m.get("content", ""):
                anchor = m
                rest = rest[index + 1:]
                break

    budget = max_msgs - len(system) - (1 if anchor else 0)
    if budget < 1:
        budget = 1
    tail = rest[-budget:]

    result = list(system)
    if anchor:
        result.append(anchor)
    result.extend(tail)
    return result


def continue_penth_blocks(messages, initial, generate, tokenizer, max_blocks=6, max_tokens=4096):
    """Continue an output that hit the token cap in numbered Penth blocks."""
    full = initial
    block = 1
    while block < max_blocks:
        messages.append({"role": "assistant", "content": initial})
        messages.append({
            "role": "user",
            "content": (
                "Your previous output was cut off by the token limit. "
                "Continue the exact same document from exactly where it "
                f"stopped. Do not repeat earlier text. [Penth #{block + 1}]"
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
        if len(tokenizer.encode(continuation)) < max_tokens:
            break
        initial = continuation
        block += 1

    if block >= max_blocks:
        print(f"\n[Reached the limit of {max_blocks} Penth blocks.]")
    return full


def auto_save_code(output, min_chars=3000, outputs_dir="Penthos/outputs"):
    """Save large fenced code blocks to a file so the terminal stays clean."""
    blocks = re.findall(
        r"```(?:([a-zA-Z0-9_]+))?\s*\n(.*?)```",
        output,
        flags=re.DOTALL,
    )
    large = [b for b in blocks if len(b[1]) >= min_chars]
    if not large:
        return

    lang, code = large[-1]
    ext = {
        "python": "py", "py": "py", "typescript": "ts", "ts": "ts",
        "javascript": "js", "js": "js", "node": "js", "html": "html",
        "css": "css", "json": "json", "bash": "sh", "shell": "sh",
    }.get(lang, "txt")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    path = Path(".") / outputs_dir / f"penthos_{stamp}.{ext}"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(code, encoding="utf-8")
    print(f"\n[saved {len(code)} chars of code to {path} — cleaner to open than the terminal]")


# Strong code-task markers. If two or more appear, the query is very likely a
# code generation task and benefits from the step-by-step scaffold.
_CODE_MARKERS = (
    "write", "create", "implement", "generate", "fix", "debug", "refactor",
    "function", "class", "def ", "api", "snippet", "algorithm", "sort",
    "parse", "script", "program", "method", "python", "javascript",
    "typescript", "golang", "rust", "java", "sql", "json", "html", "css",
    "component", "endpoint", "database", "regex", "loop",
)


def looks_like_code_task(query: str) -> bool:
    """Heuristic: is this user request a code generation/editing task?"""
    q = query.lower()
    hits = 0
    for marker in _CODE_MARKERS:
        if marker in q:
            hits += 1
            if hits >= 2:
                return True
    return bool(re.search(r"```|def |class |function |=>|import |from .+ import", q))


def maybe_wrap_code_prompt(query: str) -> str:
    """Wrap long coding requests in a reasoning scaffold when they look like code tasks.

    The scaffold forces the model to plan (input/edge cases, signature) before
    writing, which measurably improves code correctness on a 4B-scale model.
    Only short code asks are wrapped so the model does not think through trivia.
    """
    if looks_like_code_task(query) and len(query) >= 40:
        from inference.prompt import build_code_prompt
        return build_code_prompt(query)
    return query


def tool_call_feedback(output: str):
    """Return a corrective user message when the output reads like a tool-call
    attempt but failed to parse, else None.

    Some bases emit raw JSON (often in a ```json fence, sometimes malformed
    like ``"arguments:{}"`` instead of ``"arguments":{}``) instead of our
    ``<tool_call>`` tags. Instead of surfacing that junk as if it were the
    final answer, the loop feeds the model a short correction and retries.
    """
    if output.strip() and looks_like_tool_call(output) and parse_tool_call(output) is None:
        return (
            "Your response was treated as a tool call but it was not valid JSON. "
            "Either reply in plain text, or emit ONE complete JSON object "
            '{"name":"TOOL_NAME","arguments":{...}} wrapped INSIDE '
            "<tool_call>\n...\n</tool_call> tags. Do not use markdown fences "
            "or bare raw JSON."
        )
    return None


def drive_tool_loop(messages, user_text, generate, agent, max_calls=6):
    """Single shared observe -> act -> verify loop for chat.py and agent_chat.py.

    Contract: appends ``user_text``, appends the final plain-text answer as an
    assistant message, and returns None — callers read ``messages[-1]``.

    Robustness handled here once, for every entry point:
    - The tool sheet is generated per round but never stored in history.
    - Wrapped <tool_call>, bare JSON, ```json fenced JSON, and end-turn markers
      (``<|im_end|>``) are all accepted by the parser.
    - A tool call cut off by the token cap gets one chance to be finished.
    - A malformed tool call is explained to the model once; if it still emits
      JSON junk, the model is forced into a plain-text answer so the user never
      sees a blob of broken JSON.
    - Repeating the exact same failed tool call trips a warning and then stops.
    - Unknown tools and invalid arguments are explained instead of throwing.
    """
    messages.append({"role": "user", "content": user_text})

    tool_sheet = tool_prompt(agent.tool_descriptions())
    final = None

    last_call_key: str | None = None
    last_call_failed = False
    duplicate_warned = False
    partial_nudged = False
    malformed_nudged = False

    for _ in range(max_calls):
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
                        '{"name":"...","arguments":{...}} JSON wrapped inside '
                        "<tool_call> ... </tool_call>."
                    ),
                })
                continue

            feedback = tool_call_feedback(output)
            if feedback is not None:
                if not malformed_nudged:
                    malformed_nudged = True
                    messages.append({"role": "assistant", "content": output})
                    messages.append({"role": "user", "content": feedback})
                    continue
                messages.append({"role": "assistant", "content": output})
                messages.append({
                    "role": "user",
                    "content": (
                        "Your previous reply was not a valid tool call. "
                        "Answer the user's request now in plain text only — "
                        "do NOT emit any JSON."
                    ),
                })
                final = generate(messages)
                break

            final = output
            break

        tool = agent.tools.get(call["name"])
        call_key = json.dumps(
            {"name": call["name"], "args": call["arguments"]},
            sort_keys=True,
        )

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
            last_call_key = call_key
            last_call_failed = True
            continue

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
            final = generate(messages)
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
            result = agent.execute_tool(call["name"], **call["arguments"])
        except Exception as exc:
            result = f"Tool execution failed: {exc.__class__.__name__}: {exc}"
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
            last_call_key = call_key
            last_call_failed = failed
            print("[Tool FAILED]" if failed else "[Tool OK]")

        messages.append({"role": "assistant", "content": output})
        messages.append({
            "role": "user",
            "content": f"\n\n<tool_result>{result}\n</tool_result>",
        })

    if final is None:
        final = generate(messages + [{
            "role": "user",
            "content": (
                "You have used all available tool calls. Answer the user's "
                "request now in plain text, with no JSON."
            ),
        }])

    messages.append({"role": "assistant", "content": final})