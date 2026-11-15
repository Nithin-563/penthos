"""Interactive Pari chat.

Runs the local Pari model with the shared Pari system prompt,
chain-of-thought, tuned sampling, a guarded tool layer (web search, web
fetch, files, shell, code search, git, sandboxed test execution), automatic
file output for generated code, and Pari text blocks that continue long
outputs seamlessly past the per-chunk token limit.

Commands: /quit, /reset, /tools, /build <request>, /solve <request>
"""

from mlx_lm import load, stream_generate
from mlx_lm.generate import make_sampler

import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from agent.core import PariAgent
from agent.protocol import parse_tool_call, tool_prompt
from inference.loop_kit import maybe_wrap_code_prompt
from inference.prompt import (
    COMPANY,
    ENABLE_THINKING,
    MAX_TOKENS,
    MODEL,
    MODEL_DISPLAY,
    PARI_SYSTEM_PROMPT,
    TEMP,
    TOP_P,
)
from inference.security import Guard

MAX_TOOL_CALLS = 6
MAX_PARI_BLOCKS = 6
AUTO_SAVE_MIN_CHARS = 3000
OUTPUTS_DIR = "Pari/outputs"

print(f"Loading {MODEL_DISPLAY}...")
model, tokenizer = load(MODEL)
agent = PariAgent(".")
guard = Guard()

print(f"{MODEL_DISPLAY} by {COMPANY}")
print("Commands: /quit, /reset, /tools, /build <request>, /solve <request>\n")


def generate(
    messages: list[dict],
    max_tokens: int = MAX_TOKENS,
    thinking: bool = ENABLE_THINKING,
) -> str:
    prompt = tokenizer.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=True,
        enable_thinking=thinking,
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

        print(f"\n[Pari → {call['name']}]", flush=True)
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


def continue_pari_blocks(messages: list[dict], initial: str) -> str:
    """Continue an output that hit the token cap in numbered Pari blocks."""
    full = initial
    block = 1
    while block < MAX_PARI_BLOCKS:
        messages.append({"role": "assistant", "content": initial})
        messages.append({
            "role": "user",
            "content": (
                f"Your previous output was cut off by the token limit. "
                f"Continue the exact same document from exactly where it "
                f"stopped. Do not repeat earlier text, do not label the "
                f"section, just continue writing seamlessly. "
                f"[Pari #{block + 1}]"
            ),
        })
        print(f"\n[Pari #{block + 1}]", flush=True)
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

    if block >= MAX_PARI_BLOCKS:
        print(f"\n[Reached the limit of {MAX_PARI_BLOCKS} Pari blocks.]")
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
    path = Path(".") / OUTPUTS_DIR / f"pari_{stamp}.{ext}"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(code, encoding="utf-8")
    print(f"\n[saved {len(code)} chars of code to {path} — cleaner to open than the terminal]")


messages = [
    {"role": "system", "content": PARI_SYSTEM_PROMPT},
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
        messages = [{"role": "system", "content": PARI_SYSTEM_PROMPT}]
        print("Chat reset.\n")
        continue

    if query == "/tools":
        for tool in agent.tool_descriptions():
            print(f"- {tool['name']}: {tool['description']}")
        continue

    if query.startswith("/solve "):
        request = query[len("/solve "):].strip()
        if not request:
            print("Usage: /solve <coding task>\n")
            continue

        from inference.codegen import clean_file_output
        from inference.verify_loop import solve_best_of_n
        from sandbox.tool import run_tests

        def execute(files: dict, command: list[str]) -> dict:
            return run_tests("python", files, command)

        print("\n[Pari solve] writing a test suite for the task...")
        tests_text = clean_file_output(
            generate(
                [
                    {
                        "role": "system",
                        "content": PARI_SYSTEM_PROMPT,
                    },
                    {
                        "role": "user",
                        "content": (
                            "Write ONLY a pytest file named test_main.py for this task.\n\n"
                            f"TASK: {request}\n\n"
                            "Rules:\n"
                            "- `from main import ...` and call the functions the task names.\n"
                            "- Cover the happy path, one boundary case and one error case.\n"
                            "- No prose, no fences, no TODOs.\n"
                        ),
                    },
                ],
                thinking=False,
            )
        )

        try:
            samples = max(1, int(os.environ.get("PARI_SOLVE_SAMPLES", "2")))
        except ValueError:
            samples = 2

        print(
            f"[Pari solve] sampling {samples} solution(s) and running the suite..."
        )
        result = solve_best_of_n(
            request,
            lambda messages: generate(messages, thinking=False),
            execute,
            tests={"test_main.py": tests_text},
            samples=samples,
            attempts=2,
        )

        if result.success:
            print(f"\n[solve] passed in {result.attempts_used} attempt(s).")
        else:
            print(f"\n[solve] still failing after {result.attempts_used} attempt(s).")
        if result.result:
            stdout = str(result.result.get("stdout") or "")
            stderr = str(result.result.get("stderr") or "")
            if stdout:
                print(stdout[-2000:])
            if stderr:
                print(stderr[-2000:])
        print()
        continue

    if query.startswith("/build "):
        request = query[len("/build "):].strip()
        if not request:
            print("Usage: /build <what to build>\n")
            continue
        from inference.codegen import generate_project

        try:
            # Files must be pure code: chain-of-thought would leak into them.
            result = generate_project(
                request, lambda messages: generate(messages, thinking=False)
            )
        except ValueError as exc:
            print(f"Could not plan the build: {exc}\n")
            continue
        print(f"\n[built {len(result.written)} file(s)]")
        for path in result.written:
            print(f"  {path}")
        if result.issues:
            print("[static checks]")
            for issue in result.issues:
                print(f"  {issue['path']}: {issue['problem']}")
        if result.review and result.review.get("verdict") == "needs_fixes":
            print("[review] flagged issues remain; run the entry point to verify.")
        print()
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

    # Continue long outputs in numbered Pari blocks.
    if len(tokenizer.encode(output)) >= MAX_TOKENS:
        output = continue_pari_blocks(messages, output)

    output = guard.sanitize_output(output)

    # Generated code gets written to disk instead of flooding the terminal.
    auto_save_code(output)

    messages.append({"role": "assistant", "content": output})
    print()