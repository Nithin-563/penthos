"""Secure, disposable Docker-based code execution sandbox for Penthos.

Every execution runs inside a fresh, throwaway container with networking
disabled, host environment strictly excluded, resource limits applied, and
the container removed immediately after the run finishes (success, failure,
or timeout).

The runner never executes directly on the host and never falls back to host
execution if Docker is unavailable.
"""

import json
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from sandbox import policies
from sandbox.policies import ExecutionPolicy


class SandboxError(Exception):
    """Raised when the sandbox infrastructure itself fails.

    Distinct from a program returning a non-zero exit code, which is a
    legitimate execution result and not an error.
    """


def _validate_payload(payload: dict) -> None:
    """Validate the structure of the request payload."""

    if not isinstance(payload, dict):
        raise SandboxError("Payload must be a JSON object")

    language = payload.get("language")
    if not isinstance(language, str) or not policies.is_supported_language(language):
        raise SandboxError(
            f"Unsupported language: {language!r}. "
            f"Supported: {', '.join(policies.allowed_languages())}"
        )

    files = payload.get("files")
    if not isinstance(files, dict) or not files:
        raise SandboxError("Payload requires a non-empty 'files' object")

    for name, content in files.items():
        if not isinstance(name, str) or not name.strip():
            raise SandboxError("File names must be non-empty strings")
        if name.startswith("/") or ".." in name.split("/"):
            raise SandboxError(f"Illegal file name: {name!r}")
        if not isinstance(content, str):
            raise SandboxError(
                f"File content for {name!r} must be a string"
            )

    command = payload.get("command")
    if not isinstance(command, list) or not command:
        raise SandboxError("Payload requires a non-empty 'command' list")
    if not all(isinstance(token, str) for token in command):
        raise SandboxError("Command must be a list of strings")


def execute(
    payload: dict,
    policy: ExecutionPolicy | None = None,
    docker_binary: str = "docker",
) -> dict:
    """Run a code payload inside a disposable sandbox container.

    Expected payload:

        {
            "language": "python",                 # python | node | typescript
            "files": {
                "main.py": "...",
                "test_main.py": "...",
            },
            "command": ["python", "-m", "pytest", "-q"],
            "timeout_seconds": 20,                # optional
        }

    Returns a structured result (never raises for user-code failures):

        {
            "success": bool,
            "exit_code": int,
            "stdout": str,
            "stderr": str,
            "timed_out": bool,
            "duration_ms": int,
            "language": str,
            "error": str | None,                  # present only on error
        }
    """

    try:
        _validate_payload(payload)
    except SandboxError as exc:
        return _error_result(str(payload.get("language", "")), str(exc))

    language = payload["language"]
    files = payload["files"]
    command = payload["command"]

    # The command allowlist is always enforced regardless of policy.
    try:
        policies.validate_command(language, command)
    except ValueError as exc:
        return _error_result(str(language), str(exc))

    try:
        requested_timeout = payload.get("timeout_seconds", policies.DEFAULT_TIMEOUT_SECONDS)
        requested_timeout = int(requested_timeout)
        if requested_timeout < 1:
            raise ValueError
    except (TypeError, ValueError):
        return _error_result(
            str(language),
            "timeout_seconds must be a positive number of seconds",
        )

    # The payload may request a shorter timeout, but never a longer one than
    # the conservative bleed guard allows.
    policy = policy or ExecutionPolicy(
        timeout_seconds=min(requested_timeout, policies.MAX_HOST_TIMEOUT_SECONDS)
    )

    if not _command_available(docker_binary):
        return _error_result(
            language,
            f"Docker is required to run sandboxed code and is not "
            f"available ({docker_binary!r} not found on PATH). No host "
            f"fallback is performed.",
        )

    image = policies.image_for(language)

    if not _image_exists(docker_binary, image):
        return _error_result(
            language,
            f"Sandbox image '{image}' is not present. Build it first, e.g. "
            f"docker build -f sandbox/images/{language}.Dockerfile "
            f"-t {image} sandbox",
        )

    workspace_dir = None
    container_name = None

    try:
        with tempfile.TemporaryDirectory(prefix="penthos-sandbox-") as tmp:
            workspace_dir = Path(tmp)
            _write_files(workspace_dir, files)
            container_name = f"penthos-sandbox-{int(time.time() * 1000)}"

            result = _run_container(
                docker_binary=docker_binary,
                image=image,
                language=language,
                command=command,
                workspace=workspace_dir,
                policy=policy,
                container_name=container_name,
            )
            return result
    finally:
        if container_name:
            _remove_container(docker_binary, container_name)


def build_images(language: str | None = None, docker_binary: str = "docker") -> dict:
    """Build the sandbox images (all languages, or a single one).

    This is a Penthos-side operation only; it is never exposed to the model.
    """

    languages = [language] if language else list(policies.SUPPORTED_LANGUAGES)

    results = {}
    for lang in languages:
        image = policies.image_for(lang)
        dockerfile = f"images/{lang}.Dockerfile"

        build_result = subprocess.run(
            [
                docker_binary,
                "build",
                "-f",
                dockerfile,
                "-t",
                image,
                ".",
            ],
            cwd=str(Path(__file__).resolve().parent),
            capture_output=True,
            text=True,
        )
        results[lang] = {
            "image": image,
            "success": build_result.returncode == 0,
            "output": (
                build_result.stdout + build_result.stderr
            )[-policies.DEFAULT_MAX_OUTPUT_BYTES:],
        }
    return results


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------

def _write_files(workspace: Path, files: dict) -> None:
    for name, content in files.items():
        # Names are already validated (no traversal), but stay defensive.
        target = workspace / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")


def _command_available(docker_binary: str) -> bool:
    return shutil.which(docker_binary) is not None


def _image_exists(docker_binary: str, image: str) -> bool:
    probe = subprocess.run(
        [docker_binary, "image", "inspect", image],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return probe.returncode == 0


def _run_container(
    docker_binary: str,
    image: str,
    language: str,
    command: list[str],
    workspace: Path,
    policy: ExecutionPolicy,
    container_name: str,
) -> dict:
    """Build and run the docker run command, then clean up on timeout."""

    mem_limit = f"{int(policy.memory_mb)}m"
    cpus = f"{policy.cpus}"
    pids_limit = str(int(policy.pids))
    host_timeout = min(policy.timeout_seconds + 5, policies.MAX_HOST_TIMEOUT_SECONDS)

    argv = [
        docker_binary,
        "run",
        "--rm",
        "--name", container_name,
        # No network, by default.
        "--network", "none",
        # Do not inherit the host environment; provide only needed vars.
        "--env", "PYTHONUNBUFFERED=1",
        "--env", "LANG=C.UTF-8",
        # Resource limits.
        "--memory", mem_limit,
        "--cpus", cpus,
        "--pids-limit", pids_limit,
        # Security: drop capabilities, rely on default seccomp, no privilege,
        # no privileged mode, run as the image's non-root user.
        "--cap-drop", "ALL",
        "--security-opt", "no-new-privileges",
        # Mount only the temporary workspace, read/write.
        "--mount",
        f"type=bind,src={workspace},dst={policies.WORKSPACE_DIR}",
        "--workdir", policies.WORKSPACE_DIR,
        image,
        *command,
    ]

    start = time.monotonic()

    try:
        completed = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=host_timeout,
        )
    except subprocess.TimeoutExpired:
        _remove_container(docker_binary, container_name)
        return _error_result(
            language,
            f"Execution exceeded the timeout of {policy.timeout_seconds}s "
            f"and was terminated.",
            timed_out=True,
            duration_ms=int((time.monotonic() - start) * 1000),
        )
    except FileNotFoundError:
        return _error_result(
            language,
            f"Docker executable '{docker_binary}' could not be launched.",
        )

    duration_ms = int((time.monotonic() - start) * 1000)

    stdout = _cap_output(completed.stdout)
    stderr = _cap_output(completed.stderr)

    # Docker CLI failure codes (125 daemon error, 126 cannot execute,
    # 127 command not found) indicate a sandbox infrastructure problem,
    # not a user-code result. Surface a clear sandbox error instead of a
    # misleading exit code.
    if completed.returncode in (125, 126, 127):
        detail = (stderr or stdout).strip().splitlines()
        detail = detail[-1] if detail else ""
        return _error_result(
            language,
            f"Sandbox could not start the container (docker exit "
            f"{completed.returncode}). {detail}",
            duration_ms=duration_ms,
        )

    return {
        "success": completed.returncode == 0,
        "exit_code": completed.returncode,
        "stdout": stdout,
        "stderr": stderr,
        "timed_out": False,
        "duration_ms": duration_ms,
        "language": language,
    }


def _remove_container(docker_binary: str, container_name: str) -> None:
    subprocess.run(
        [docker_binary, "rm", "-f", container_name],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _cap_output(text: str, limit: int | None = None) -> str:
    limit = limit or policies.DEFAULT_MAX_OUTPUT_BYTES
    if len(text) <= limit:
        return text
    return text[:limit] + "\n... [output truncated]"


def _error_result(
    language: str,
    message: str,
    timed_out: bool = False,
    duration_ms: int = 0,
) -> dict:
    return {
        "success": False,
        "exit_code": -1,
        "stdout": "",
        "stderr": message,
        "timed_out": timed_out,
        "duration_ms": duration_ms,
        "language": language,
        "error": message,
    }


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "build":
        print(json.dumps(build_images(), indent=2))
        sys.exit(0)

    print("Penthos sandbox runner. Use 'build' to build images.")
