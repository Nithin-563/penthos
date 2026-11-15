"""Generate -> execute -> repair, and best-of-N sampling.

A small model's first attempt is often 80% right: one off-by-one, one missing
import, one unhandled edge case. Throwing that away wastes the model's
strength. This module feeds the real failure back and asks for a correction,
which is the cheapest reliable way to raise pass rates at this model size.

Nothing here loads a model or touches Docker: the caller injects
``generate(messages) -> str`` and ``execute(files, command) -> dict`` (the
sandbox runner fits the second signature through a small adapter). That keeps
the loop testable on any machine and reusable by the chat, the agent, the build
pipeline and the benchmark.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from inference.codegen import strip_code_fences
from inference.prompt import PARI_SYSTEM_PROMPT, code_prompt_notes

GenerateFn = Callable[[list[dict]], str]
ExecuteFn = Callable[[dict[str, str], list[str]], dict]

MAX_FAILURE_CHARS = 4000

SOLVE_PROMPT = """TASK: {request}
{contract}
DELIVERABLE: one complete file named `{filename}`.

Rules:
- Output ONLY the complete contents of `{filename}`: no markdown fences, no prose.
- Include every import and the full implementation. No TODOs or placeholders.
- Hidden tests import this file and call the functions exactly as named in the task.
- Handle empty/null input, boundaries, invalid types and the error paths.
- Prefer the simple correct solution; state complexity only when asked.
{notes}"""

REPAIR_PROMPT = """The file you wrote failed when it was actually executed.

TASK: {request}

FAILING FILE (`{filename}`):
{code}

FAILURE OUTPUT:
{failure}

Fix the root cause of that failure. Reply with ONLY the complete corrected
contents of `{filename}`: no fences, no explanation, no partial diff. Keep
everything that already worked and make sure this failure cannot happen again."""

BEST_OF_PROMPT = """TASK: {request}
{contract}
Answer the task completely and concretely. Cover the edge cases and state the
reasoning that matters, then give the final answer. Do not pad.
{notes}"""


@dataclass
class Attempt:
    index: int
    code: str
    success: bool
    exit_code: int = -1
    stdout: str = ""
    stderr: str = ""


@dataclass
class SolveResult:
    success: bool
    code: str
    attempts: list[Attempt] = field(default_factory=list)
    result: dict[str, Any] | None = None

    @property
    def attempts_used(self) -> int:
        return len(self.attempts)


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------

def extract_code(text: str) -> str:
    """Reduce a model reply to file contents (fences and path labels removed)."""
    return strip_code_fences(text or "").strip("\n")


def format_failure(result: dict[str, Any], limit: int = MAX_FAILURE_CHARS) -> str:
    """Build the repair prompt's evidence block from an execution result."""
    parts: list[str] = []
    if result.get("timed_out"):
        parts.append("The run timed out before finishing.")
    if result.get("error"):
        parts.append(f"Runner error: {result['error']}")
    stderr = str(result.get("stderr") or "").strip()
    stdout = str(result.get("stdout") or "").strip()
    if stderr:
        parts.append(f"STDERR:\n{stderr[-limit:]}")
    if stdout:
        parts.append(f"STDOUT:\n{stdout[-limit:]}")
    if not parts:
        parts.append(f"The run failed with exit code {result.get('exit_code')}.")
    return "\n\n".join(parts)


def run_files(execute: ExecuteFn, files: dict[str, str], command: list[str]) -> dict:
    """Call the injected executor, converting a crash into a failure result."""
    try:
        return execute(files, command)
    except Exception as exc:  # pragma: no cover - runner/sandbox failure
        return {
            "success": False,
            "exit_code": -1,
            "stdout": "",
            "stderr": f"runner error: {exc}",
            "error": str(exc),
        }


def solve_messages(prompt: str) -> list[dict]:
    return [
        {"role": "system", "content": PARI_SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
    ]


# ---------------------------------------------------------------------------
# Verified solving
# ---------------------------------------------------------------------------

def solve(
    request: str,
    generate: GenerateFn,
    execute: ExecuteFn,
    *,
    filename: str = "main.py",
    command: list[str] | None = None,
    tests: dict[str, str] | None = None,
    language: str = "python",
    attempts: int = 3,
    contract: str = "",
    log: Callable[[str], None] = print,
) -> SolveResult:
    """Generate code, execute it, and repair the real failure until it passes.

    Args:
        request: the task, in the user's words.
        generate: ``generate(messages) -> str`` for the loaded model.
        execute: ``execute(files, command) -> dict``; the sandbox runner adapter.
        filename: the file the hidden tests import (``main.py`` by default).
        command: test command; defaults to pytest for Python.
        tests: extra files (usually the test suite) placed beside the solution.
        language: used only to label the code in the repair prompt.
        attempts: total generations allowed, including the first.
        contract: extra line about the expected interface.
        log: progress sink.
    """
    if attempts < 1:
        raise ValueError("attempts must be at least 1")
    if command is None:
        command = ["python", "-m", "pytest", "-q"]
    if tests is None and filename.endswith(".py"):
        # A solution with no visible tests still has to be importable; py_compile
        # is the minimum executable contract.
        command = list(command)

    notes = code_prompt_notes(request)
    contract_block = f"\nINTERFACE: {contract}\n" if contract else ""
    first_prompt = SOLVE_PROMPT.format(
        request=request,
        filename=filename,
        contract=contract_block,
        notes=f"\n{notes}",
    )

    outcome: SolveResult = SolveResult(success=False, code="")
    for index in range(1, attempts + 1):
        if index == 1:
            prompt = first_prompt
        else:
            prompt = REPAIR_PROMPT.format(
                request=request,
                filename=filename,
                code=outcome.code,
                failure=format_failure(outcome.result or {}, ),
            )

        output = generate(solve_messages(prompt))
        code = extract_code(output)
        outcome.code = code

        files = dict(tests or {})
        files[filename] = code
        result = run_files(execute, files, list(command))
        success = bool(result.get("success"))
        outcome.result = result
        outcome.attempts.append(
            Attempt(
                index=index,
                code=code,
                success=success,
                exit_code=int(result.get("exit_code", -1) or -1),
                stdout=str(result.get("stdout") or ""),
                stderr=str(result.get("stderr") or ""),
            )
        )
        log(
            f"[Pari solve] attempt {index}/{attempts}: "
            f"{'passed' if success else 'failed'}"
        )
        if success:
            outcome.success = True
            return outcome

    return outcome


def solve_best_of_n(
    request: str,
    generate: GenerateFn,
    execute: ExecuteFn,
    *,
    samples: int = 2,
    attempts: int = 2,
    filename: str = "main.py",
    command: list[str] | None = None,
    tests: dict[str, str] | None = None,
    contract: str = "",
    log: Callable[[str], None] = print,
) -> SolveResult:
    """Sample several independent solutions, then repair the best failure.

    Pass@N is the highest-value inference trick available to a small model: an
    independent second sample often passes where the first did not, and testing
    it is cheap compared with retraining. Only when every sample fails does the
    loop spend generations on repair, starting from the most recent failure.

    Total generations = ``samples + attempts`` at most.
    """
    if samples < 1:
        raise ValueError("samples must be at least 1")
    if attempts < 0:
        raise ValueError("attempts must be non-negative")
    if command is None:
        command = ["python", "-m", "pytest", "-q"]

    notes = code_prompt_notes(request)
    contract_block = f"\nINTERFACE: {contract}\n" if contract else ""
    first_prompt = SOLVE_PROMPT.format(
        request=request,
        filename=filename,
        contract=contract_block,
        notes=f"\n{notes}",
    )

    outcome = SolveResult(success=False, code="")
    index = 0
    failure: tuple[str, dict[str, Any]] | None = None

    for sample in range(1, samples + 1):
        index += 1
        code = extract_code(generate(solve_messages(first_prompt)))
        files = dict(tests or {})
        files[filename] = code
        result = run_files(execute, files, list(command))
        success = bool(result.get("success"))
        outcome.code = code
        outcome.result = result
        outcome.attempts.append(
            Attempt(
                index=index,
                code=code,
                success=success,
                exit_code=int(result.get("exit_code", -1) or -1),
                stdout=str(result.get("stdout") or ""),
                stderr=str(result.get("stderr") or ""),
            )
        )
        log(f"[Pari solve] sample {sample}/{samples}: {'passed' if success else 'failed'}")
        if success:
            outcome.success = True
            return outcome
        failure = (code, result)

    for repair_index in range(1, attempts + 1):
        index += 1
        code, result = failure or ("", {})
        prompt = REPAIR_PROMPT.format(
            request=request,
            filename=filename,
            code=code,
            failure=format_failure(result),
        )
        fixed = extract_code(generate(solve_messages(prompt)))
        files = dict(tests or {})
        files[filename] = fixed
        result = run_files(execute, files, list(command))
        success = bool(result.get("success"))
        outcome.code = fixed
        outcome.result = result
        outcome.attempts.append(
            Attempt(
                index=index,
                code=fixed,
                success=success,
                exit_code=int(result.get("exit_code", -1) or -1),
                stdout=str(result.get("stdout") or ""),
                stderr=str(result.get("stderr") or ""),
            )
        )
        log(
            f"[Pari solve] repair {repair_index}/{attempts}: "
            f"{'passed' if success else 'failed'}"
        )
        if success:
            outcome.success = True
            return outcome
        failure = (fixed, result)

    return outcome


# ---------------------------------------------------------------------------
# Best-of-N sampling (reasoning, explanations, design tasks)
# ---------------------------------------------------------------------------

def best_of_n(
    request: str,
    generate: GenerateFn,
    *,
    n: int = 4,
    score: Callable[[str], float] | None = None,
    contract: str = "",
    log: Callable[[str], None] = print,
) -> dict[str, Any]:
    """Sample several independent answers and keep the best-scoring one.

    For tasks without executable tests (reasoning, design, explanations) this
    is the equivalent of the repair loop: independent samples plus a cheap
    scorer beat one greedy sample at this model size. ``score`` defaults to a
    length-and-structure heuristic so the helper still works standalone; pass a
    rubric, a checker, or a model-graded score for real selection.
    """
    if n < 1:
        raise ValueError("n must be at least 1")
    picker = score or default_score
    contract_block = f"\nINTERFACE: {contract}\n" if contract else ""
    prompt = BEST_OF_PROMPT.format(
        request=request,
        contract=contract_block,
        notes=f"\n{code_prompt_notes(request)}",
    )
    messages = solve_messages(prompt)

    samples: list[tuple[float, str]] = []
    for index in range(1, n + 1):
        text = (generate(messages) or "").strip()
        value = float(picker(text))
        samples.append((value, text))
        log(f"[Pari best-of-{n}] sample {index}: score {value:.2f}")

    best_score, best_text = max(samples, key=lambda item: (item[0], len(item[1])))
    return {"text": best_text, "score": best_score, "samples": samples}


def default_score(text: str) -> float:
    """Cheap quality proxy: structure and substance, not verbosity alone.

    Rewards headings, lists, code, numbers and concrete detail; penalises
    placeholders and empty answers. Deliberately transparent and replaceable.
    """
    if not text or not text.strip():
        return -100.0
    lowered = text.lower()
    score = 0.0
    words = len(text.split())
    score += min(words / 120.0, 3.0)
    if "\n\n" in text:
        score += 0.5
    for marker in ("1.", "2.", "- ", "##"):
        if marker in text:
            score += 0.75
    if "```" in text:
        score += 0.5
    if any(char.isdigit() for char in text):
        score += 0.25
    for bad in ("todo", "placeholder", "i think maybe", "lorem ipsum"):
        if bad in lowered:
            score -= 1.5
    if lowered.strip().endswith(("?", "...")):
        score -= 1.0
    return round(score, 2)
