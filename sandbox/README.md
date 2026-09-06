# Penthos Sandbox

A secure, disposable Docker-based code execution sandbox for running
generated code and tests without giving untrusted code access to the host
Mac or its secrets.

Penthos agents must be able to execute code and verify tests, but they must
never do so on the host. The sandbox runs every payload inside a fresh,
throwaway container: no network, no host environment, no host files, strict
resource limits, and automatic cleanup.

## Architecture

```
model
  │  run_tests(language, files, command)          ← agent/sandbox/tool.py
  ▼
sandbox/tool.py      Model-facing adapter. Accepts only language, files,
                     command. Docker controls are fixed and never exposed.
  ▼
sandbox/runner.py    Core engine. Validates payload, applies policy,
                     builds/removes containers, caps output, kills on timeout.
  ▼
sandbox/policies.py  Centralized limits + command allowlists.
  ▼
docker (CLI)         Disposable container with --network none, no host env,
                     --cap-drop ALL, no-new-privileges, resource limits.
```

Files:

| File | Purpose |
| --- | --- |
| `runner.py` | Execution engine (`execute`, `build_images`). |
| `policies.py` | ExecutionPolicy, per-language command allowlists, limits. |
| `tool.py` | Model-facing `run_tests` adapter registered with the agent. |
| `Dockerfile` | Meta/base placeholder for the sandbox directory. |
| `images/python.Dockerfile` | Python 3.12 image with pytest. |
| `images/node.Dockerfile` | Node 20 image. |
| `images/typescript.Dockerfile` | Node 20 image with typescript + tsx/tsc. |

The agent tool registry exposes a single sandbox tool, `run_tests`
(`agent/core.py`), and the bounded `AutonomousCodingEngine` routes test
verification through it (`agent/autonomous.py`). This enables the future
loop: inspect repository → modify code → run tests in the sandbox →
inspect failure → modify → run again → stop when verified or the iteration
limit is reached.

## Security model

Every execution:

- Runs in a **disposable container** (`docker run --rm`), removed after the
  run succeeds, fails, or times out. `docker ps -a` never accumulates
  sandbox containers.
- Has **no network**: `--network none`.
- Does **not** inherit the host environment. Only two variables are set:
  `PYTHONUNBUFFERED=1` and `LANG=C.UTF-8`. No `--env-file`, no `os.environ`.
- Mounts **only** the temporary workspace directory under `/workspace`
  (read/write). No `~/.ssh`, `~/.aws`, `~/.config`, `~/.cache`, no Docker
  socket, no arbitrary host directories, never the home directory.
- Enforces resource limits: memory (512 MB), CPUs (1), PIDs (128), and a
  wall-clock timeout (20 s).
- Drops all Linux capabilities (`--cap-drop ALL`), stays non-privileged
  (`no-new-privileges`), relies on Docker's default seccomp profile, and
  runs as a non-root user (`sandbox`, uid 1000/1001) with `/workspace` as
  the working directory.
- Captures stdout/stderr and caps output at 64 KB so a noisy program
  cannot fill memory with logs.
- Never uses `shell=True`; the command is passed to Docker strictly as an
  argv list. Docker environment, mounts, and flags are fixed by Penthos and
  never come from the model.
- Never falls back to host execution. If Docker is missing, the image is
  absent, or setup fails, the runner returns a clear structured `error`.

The command is validated against a per-language allowlist in `policies.py`.
Only `python` / `python3` / `pytest` (Python), `node` / `npm` / `npx`
(Node), and `node` / `npm` / `npx` / `tsx` / `tsc` (TypeScript) may be used
as the entrypoint. Argument tokens are checked for safe characters; shell
operators, absolute paths, and path traversal are rejected. There is no
generic shell executor behind the sandbox API.

## Supported languages

| Language | Binaries | Notes |
| --- | --- | --- |
| `python` | `python`, `python3`, `pytest` | pytest 8.3 preinstalled |
| `node` | `node`, `npm`, `npx` | Node 20, npm included |
| `typescript` | `node`, `npm`, `npx`, `tsx`, `tsc` | typescript 5.6 + tsx 4.19 global |

Dependency installation is *not* enabled through the sandbox. Images are
frozen at build time and execution has no network, so `pip install` and
`npm install` cannot run against the internet. A controlled dependency-
preparation stage can be added later without broadening the execution
surface.

## Limits (defaults)

Configured centrally in `sandbox/policies.py`. Tuning these is a Penthos
operation; the model cannot override them.

| Limit | Default |
| --- | --- |
| Memory | 512 MB |
| CPUs | 1 |
| Processes (PIDs) | 128 |
| Timeout | 20 s (per-execution payload timeout capped at 120 s) |
| Captured output | 64 KB |

These fit comfortably within a 16 GB Mac with an ~8 GB Docker engine so
multiple jobs can coexist.

## Example usage

Build the images (Penthos-side operation):

```bash
cd /Users/nithin/Penthos
python3 -m sandbox.runner build
```

Run a Python test:

```python
from sandbox import runner

result = runner.execute({
    "language": "python",
    "files": {
        "main.py": "def add(a, b):\n    return a + b\n",
        "test_main.py": "from main import add\n\ndef test_add():\n    assert add(1, 2) == 3\n",
    },
    "command": ["python", "-m", "pytest", "-q"],
})
```

Result:

```json
{
  "success": true,
  "exit_code": 0,
  "stdout": "...1 passed...",
  "stderr": "",
  "timed_out": false,
  "duration_ms": 340,
  "language": "python"
}
```

Use it through the agent:

```python
from agent.core import PenthosAgent

agent = PenthosAgent(".")
agent.execute_tool("run_tests", language="python",
                   files={"test_main.py": "..."},
                   command=["python", "-m", "pytest", "-q"])
```

Run the tests:

```bash
cd /Users/nithin/Penthos
.venv/bin/python -m pytest tests/test_sandbox.py -v
```

## Known limitations

This sandbox is not a perfect security boundary. Realistic limitations:

- A model that can write arbitrary file contents can already run arbitrary
  code *inside* the container (the sandbox limits the container, not the
  code's logic).
- The command allowlist and argument validation reduce the surface but are
  not a formal policy engine; they are defense in depth.
- The workspace binds the host's temporary directory read/write. A hostile
  program can fill its workspace disk (the container has no dedicated disk
  quota).
- Resource limits rely on the Docker engine being available and behaving;
  they do not protect against kernel bugs or Docker/containerd escapes.
- No network means no dependency installation; projects needing third-party
  libraries require a separate, controlled preparation stage that is not
  implemented yet.
- The sandbox does not verify that generated code is *functionally correct*;
  it only runs what it is told and reports the outcome.
- Containers are cleaned up by `--rm` plus an explicit `rm -f` on timeout.
  A hard crash of the orchestrator could in principle leave a container
  behind.