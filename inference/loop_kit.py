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

import re
from datetime import datetime, timezone
from pathlib import Path


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