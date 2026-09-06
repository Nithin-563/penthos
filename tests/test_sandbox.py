"""Tests for the Penthos Docker sandbox.

These are integration tests and require a running Docker daemon plus the
sandbox images:

    docker build -f sandbox/images/python.Dockerfile        -t penthos-sandbox:python sandbox
    docker build -f sandbox/images/node.Dockerfile          -t penthos-sandbox:node sandbox
    docker build -f sandbox/images/typescript.Dockerfile    -t penthos-sandbox:typescript sandbox

Run from the repository root:

    python -m pytest tests/test_sandbox.py -v

All execution happens inside disposable containers. Nothing in this suite
ever executes user code directly on the host.
"""

import subprocess
import sys
import time
from pathlib import Path

import pytest

from sandbox import policies, runner
from sandbox.tool import run_tests

REPO_ROOT = Path(__file__).resolve().parent.parent

sys.path.insert(0, str(REPO_ROOT))

DOCKER = "docker"

PASS_FILES = {
    "main.py": "def add(a, b):\n    return a + b\n",
    "test_main.py": (
        "from main import add\n"
        "\n"
        "def test_add():\n"
        "    assert add(1, 2) == 3\n"
    ),
}

FAIL_FILES = {
    "test_fail.py": (
        "def test_failure():\n"
        "    assert 1 == 2, 'deliberate failure'\n"
    ),
}

BIG_FILES = {
    "main.py": (
        "for i in range(2000):\n"
        "    print('x' * 100)\n"
    ),
}

NOISE_FILES = {
    "noise.py": "print('hello from the sandbox')\n",
}


def _containers() -> list[str]:
    """Return currently present penthos-sandbox container names."""

    result = subprocess.run(
        [DOCKER, "ps", "-a", "--filter", "name=penthos-sandbox", "--format", "{{.Names}}"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


@pytest.fixture(autouse=True)
def _no_leftover_containers():
    yield
    leftovers = _containers()
    assert leftovers == [], f"Sandbox containers leaked: {leftovers}"


def test_supported_languages():
    assert policies.allowed_languages() == ("python", "node", "typescript")


def test_python_success():
    """1. Valid Python execution succeeds."""

    result = run_tests("python", PASS_FILES, ["python", "-m", "pytest", "-q"])
    assert result["language"] == "python"
    assert result["exit_code"] == 0
    assert result["success"] is True
    assert "1 passed" in result["stdout"]
    assert result["timed_out"] is False
    assert result["duration_ms"] >= 0


def test_python_failing_test():
    """2. Failing test returns a non-zero exit code."""

    result = run_tests("python", FAIL_FILES, ["python", "-m", "pytest", "-q"])
    assert result["exit_code"] != 0
    assert result["success"] is False
    assert "deliberate failure" in result["stdout"] + result["stderr"]


def test_timeout_terminates():
    """3. Timeout terminates execution."""

    payload = {
        "language": "python",
        "files": {"sleep.py": "import time\nwhile True:\n    time.sleep(1)\n"},
        "command": ["python", "sleep.py"],
        "timeout_seconds": 2,
    }
    start = time.monotonic()
    result = runner.execute(payload)
    elapsed = time.monotonic() - start

    assert result["timed_out"] is True
    assert result["success"] is False
    # Allow generous slack for container startup/teardown.
    assert elapsed < 30


def test_output_is_capped():
    """4. Output is capped."""

    result = run_tests("python", BIG_FILES, ["python", "main.py"])

    combined = result["stdout"]
    assert "truncated" in combined
    assert len(combined) <= policies.DEFAULT_MAX_OUTPUT_BYTES + 64


def test_unsupported_language_rejected():
    """5. Unsupported language is rejected."""

    result = run_tests("rust", PASS_FILES, ["cargo", "test"])
    assert result["success"] is False
    assert result["exit_code"] == -1
    assert "Unsupported language" in result["stderr"]


def test_unsupported_command_rejected():
    """6. Unsupported command is rejected for the language."""

    result = run_tests("python", PASS_FILES, ["bash", "-c", "rm -rf /"])
    assert result["success"] is False
    assert result["exit_code"] == -1
    assert "not allowed" in result["stderr"]


def test_network_is_unavailable():
    """7. Network access is unavailable."""

    files = {
        "net.py": (
            "import urllib.request\n"
            "try:\n"
            "    urllib.request.urlopen('http://10.255.255.1', timeout=2)\n"
            "    print('NETWORK_OK')\n"
            "except Exception:\n"
            "    print('NETWORK_BLOCKED')\n"
        ),
    }
    result = run_tests("python", files, ["python", "net.py"])
    assert result["exit_code"] == 0
    assert "NETWORK_BLOCKED" in result["stdout"]


def test_host_env_not_exposed():
    """8. Host environment variables are not exposed."""

    import os

    os.environ["PENTHOS_SECRET_TOKEN"] = "supersecret-e2e-value"
    files = {
        "env.py": (
            "import os\n"
            "print(os.environ.get('PENTHOS_SECRET_TOKEN', 'NOT_PRESENT'))\n"
        ),
    }
    result = run_tests("python", files, ["python", "env.py"])
    assert "NOT_PRESENT" in result["stdout"]
    assert "supersecret" not in result["stdout"]
    assert "supersecret" not in result["stderr"]


def test_container_removed_after_execution():
    """9. Container is removed after execution."""

    before = set(_containers())
    run_tests("python", NOISE_FILES, ["python", "noise.py"])

    # The fixture also asserts no leftovers, but assert here too for clarity.
    after = set(_containers())
    assert before == after
    assert "hello from the sandbox" in run_tests(
        "python", NOISE_FILES, ["python", "noise.py"]
    )["stdout"]
    assert _containers() == []


def test_no_host_execution():
    """10. Sandbox does not execute anything on the host.

    Runs a payload that creates a distinctive file inside the container; if
    it appeared anywhere on the host, the sandbox leaked out. Because the
    container is ephemeral, the marker should only ever exist inside the
    container, not on the host.
    """

    files = {
        "marker.py": (
            "from pathlib import Path\n"
            "Path('/workspace/sandbox-marker.txt').write_text('sandbox-internal')\n"
            "print('MARKER_WRITTEN')\n"
            # Host Mac directories must not exist inside the container.
            "print('HOST_MAC_VISIBLE', Path('/Users').exists())\n"
            "print('SSH_VISIBLE', Path('/home/sandbox/.ssh').exists())\n"
        ),
    }
    result = run_tests("python", files, ["python", "marker.py"])
    assert result["exit_code"] == 0
    assert "MARKER_WRITTEN" in result["stdout"]
    assert "HOST_MAC_VISIBLE False" in result["stdout"]
    assert "SSH_VISIBLE False" in result["stdout"]

    host_home = Path.home()
    # The marker must never appear in the host home directory or repo root.
    assert not (host_home / "sandbox-marker.txt").exists(), (
        "File written inside the container leaked to the host home directory!"
    )
    assert not (REPO_ROOT / "sandbox-marker.txt").exists(), (
        "File written inside the container leaked to the repository!"
    )


def test_agent_tool_never_exposes_docker_controls():
    """The model-facing tool accepts onlylanguage/files/command and rejects Docker knobs."""

    from agent.core import PenthosAgent

    agent = PenthosAgent(".")
    tol = agent.tools.get("run_tests")
    assert tol is not None

    import inspect

    # The tool adapter must not accept docker-specific parameters.
    params = inspect.signature(tol.function).parameters
    for forbidden in (
        "mounts",
        "network",
        "env",
        "privileged",
        "capabilities",
        "dockerfile",
        "timeout_seconds",
        "memory",
        "cpus",
        "pids",
    ):
        assert forbidden not in params


def test_no_host_fallback_when_docker_missing():
    """Missing Docker must yield a clear sandbox error, never host execution."""

    result = runner.execute(
        {
            "language": "python",
            "files": {"hello.py": "open('/Users', 'w')  # if run on host this would fail loudly\nprint('HOST_RAN')\n"},
            "command": ["python", "hello.py"],
        },
        docker_binary="penthos-fake-docker-command-xyz",
    )
    assert result["success"] is False
    assert result["exit_code"] == -1
    assert "Docker is required" in result["stderr"]
    assert "HOST_RAN" not in result["stdout"]


def test_run_tests_registered_in_agent():
    """The sandbox tool is registered on the Penthos agent."""

    from agent.core import PenthosAgent

    agent = PenthosAgent(".")
    names = {tool["name"] for tool in agent.tool_descriptions()}
    assert "run_tests" in names

    tool = agent.tools.get("run_tests")
    assert tool is not None
    assert tool.function is not None


if __name__ == "__main__":
    sys.exit(pytest.main(["-v", __file__]))