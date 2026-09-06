# Penthos Agent Core

The Penthos Agent Core separates the model from the environment in
which it operates.

Current capabilities:

- tool registry
- persistent memory
- repository indexing
- project context
- filesystem operations
- code search
- Git inspection
- web search
- web fetching
- command execution
- verification helpers
- permission checks
- bounded autonomous coding loop
- isolated Docker sandbox for test execution

The intended coding-agent cycle is:

1. Understand
2. Inspect
3. Plan
4. Implement
5. Verify (in the sandbox)
6. Diagnose
7. Repair
8. Verify again
9. Report

The model is not given unrestricted machine access.

The `run_tests` tool executes generated code and tests inside a disposable,
network-isolated Docker container that never sees the host filesystem,
Docker socket, or host environment variables. Host-side command execution
via `shell_exec` remains permission-gated, but for generated untrusted code
the sandbox is the only supported execution path.
