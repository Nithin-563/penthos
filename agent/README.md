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

The intended coding-agent cycle is:

1. Understand
2. Inspect
3. Plan
4. Implement
5. Verify
6. Diagnose
7. Repair
8. Verify again
9. Report

The model is not given unrestricted machine access.

Before public deployment, command execution must run inside a
proper isolated sandbox with resource limits and secret protection.
