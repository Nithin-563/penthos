"""Model-facing sandbox tool adapter.

This layer is what the agent exposes to the model. It accepts only a
narrow, safe subset of the runner's inputs (language, files, test command)
and never exposes Docker-specific controls such as mounts, network mode,
environment variables, capabilities, resource limits, or privileged mode.

All validation failures are returned as structured result dicts so the
agent loop can feed them back to the model without raising.
"""

from sandbox import runner


def run_tests(
    language: str,
    files: dict,
    command: list[str] | None = None,
) -> dict:
    """Run generated code/tests inside the disposable sandbox.

    Model-visible parameters:
      - language: "python" | "node" | "typescript"
      - files: {filename: contents}
      - command: entrypoint argv, e.g. ["python", "-m", "pytest", "-q"].
                 Defaults to the matching language default when omitted.

    Docker controls (network, mounts, env, limits, capabilities, timeout,
    etc.) are intentionally not exposed here and are fixed by Penthos
    policy. The model cannot request resource changes.
    """

    try:
        if command is None:
            command = _default_command(language)

        payload = {
            "language": language,
            "files": files,
            "command": command,
        }

        return runner.execute(payload)
    except Exception as exc:
        return _error_result(language, str(exc))


def _default_command(language: str) -> list[str]:
    defaults = {
        "python": ["python", "-m", "pytest", "-q"],
        "node": ["node", "index.js"],
        "typescript": ["tsx", "index.ts"],
    }
    if language not in defaults:
        raise ValueError(f"Unsupported language: {language}")
    return defaults[language]


def _error_result(language: str, message: str) -> dict:
    return {
        "success": False,
        "exit_code": -1,
        "stdout": "",
        "stderr": str(message),
        "timed_out": False,
        "duration_ms": 0,
        "language": str(language),
        "error": str(message),
    }