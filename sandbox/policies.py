"""Centralized security limits and command allowlists for the sandbox.

Everything the runner needs to stay conservative is defined here so the
values can be tuned by Penthos itself without ever being controlled by
model-generated tool arguments.
"""

from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Conservative execution defaults.
#
# Penthos runs on a developer Mac with 16 GB unified memory; the local
# Docker engine is configured with roughly 8 GB of RAM. Each sandboxed
# execution is deliberately given a small slice so many jobs can coexist
# without starving the host.
# ---------------------------------------------------------------------------

# Maximum memory a single container may consume.
DEFAULT_MEMORY_MB = 512

# Number of host CPUs a single container may use.
DEFAULT_CPUS = 1

# Maximum number of processes a single container may spawn.
DEFAULT_PIDS = 128

# Wall-clock budget (seconds) before a container is killed.
DEFAULT_TIMEOUT_SECONDS = 20

# Maximum bytes of combined captured output returned to the caller.
DEFAULT_MAX_OUTPUT_BYTES = 64 * 1024  # 64 KB

# Runtime bleed guards for the host-side process.
MAX_HOST_TIMEOUT_SECONDS = 120

# Supported execution languages.
SUPPORTED_LANGUAGES = ("python", "node", "typescript")

# Docker images built from sandbox/images/*.Dockerfile.
IMAGE_NAMES = {
    "python": "penthos-sandbox:python",
    "node": "penthos-sandbox:node",
    "typescript": "penthos-sandbox:typescript",
}

# Working directory used inside every image.
WORKSPACE_DIR = "/workspace"

# Non-root user created inside every image.
IMAGE_USER = "sandbox"

# Container-relative location of the mounted workspace.
CONTAINER_WORKSPACE = WORKSPACE_DIR


@dataclass(frozen=True)
class ExecutionPolicy:
    """Immutable limits applied to a single sandboxed execution."""

    memory_mb: int = DEFAULT_MEMORY_MB
    cpus: float = DEFAULT_CPUS
    pids: int = DEFAULT_PIDS
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS
    max_output_bytes: int = DEFAULT_MAX_OUTPUT_BYTES

    def __post_init__(self):
        if self.memory_mb < 64:
            raise ValueError("memory_mb must be at least 64")
        if self.cpus < 0.1:
            raise ValueError("cpus must be at least 0.1")
        if self.pids < 16:
            raise ValueError("pids must be at least 16")
        if self.timeout_seconds < 1:
            raise ValueError("timeout_seconds must be positive")
        if self.max_output_bytes < 1024:
            raise ValueError("max_output_bytes must be at least 1024")


# ---------------------------------------------------------------------------
# Command allowlists.
#
# The command argument the model supplies may only select an entrypoint from
# these lists. No generic shell is ever exposed. Validation is two-stage:
# token zero must be a permitted executable for the language and every other
# token must be a simple argument (safe characters only, no shell operators,
# no path traversal, no redirects/pipes/glob expansion).
# ---------------------------------------------------------------------------

# Allowed entrypoint executables per language.
_ALLOWED_EXECUTABLES = {
    "python": {"python", "python3", "pytest"},
    "node": {"node", "npm", "npx"},
    "typescript": {"node", "npm", "npx", "tsx", "tsc"},
}

# Charsets for argument tokens. Hyphens are allowed everywhere because they
# appear in long flags (--tb=short) and in file names (my-app.test.ts).
# Flags additionally allow "=" and ":" (e.g. --key=value).
_SAFE_TOKEN_CHARSET = set(
    "abcdefghijklmnopqrstuvwxyz"
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    "0123456789"
    "_.@-"
)
_FLAG_EXTRA_CHARSET = _SAFE_TOKEN_CHARSET | set("=:")

# Characters that must never appear in an argument because they are shell
# operators, quoting, or glob/brace constructs. They would be inert without
# a shell but are rejected anyway to keep the surface conservative.
_FORBIDDEN_CHARS = set(';|&><$`\'"*?~[](){}!#\\')


def allowed_languages():
    return tuple(SUPPORTED_LANGUAGES)


def is_supported_language(language: str) -> bool:
    return language in SUPPORTED_LANGUAGES


def image_for(language: str) -> str:
    if language not in IMAGE_NAMES:
        raise ValueError(f"Unsupported language: {language}")
    return IMAGE_NAMES[language]


def allowed_executables(language: str) -> set[str]:
    if language not in _ALLOWED_EXECUTABLES:
        raise ValueError(f"Unsupported language: {language}")
    return _ALLOWED_EXECUTABLES[language]


def validate_command(language: str, command: list[str]) -> None:
    """Raise ValueError if the command is not allowed for the language.

    The command must be a non-empty list of strings whose first token is a
    permitted executable for the language and whose remaining tokens are all
    simple arguments: safe characters only, no shell operators, no embedded
    whitespace, no absolute paths, and no `..` path segments.
    """

    if not isinstance(command, list) or not command:
        raise ValueError("Command must be a non-empty list of arguments")

    if not all(isinstance(token, str) and token.strip() for token in command):
        raise ValueError("Command arguments must be non-empty strings")

    executable = command[0]

    if executable not in allowed_executables(language):
        raise ValueError(
            f"Command '{executable}' is not allowed for language "
            f"'{language}'. Allowed: {sorted(allowed_executables(language))}"
        )

    for token in command[1:]:
        _validate_argument_token(language, token)


def _validate_argument_token(language: str, token: str) -> None:
    if token.startswith("/"):
        raise ValueError(
            "Command argument must not be an absolute path "
            f"(got {token!r})"
        )
    if ".." in token:
        raise ValueError(
            "Command argument must not contain path traversal "
            f"(got {token!r})"
        )
    if any(c in _FORBIDDEN_CHARS for c in token):
        raise ValueError(
            f"Command argument contains forbidden characters: {token!r}"
        )

    charset = _FLAG_EXTRA_CHARSET if token.startswith("-") else _SAFE_TOKEN_CHARSET

    if any(c not in charset for c in token):
        raise ValueError(
            f"Command argument is not a plain safe token for "
            f"language '{language}': {token!r}"
        )
