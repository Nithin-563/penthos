# Penthos Memory

Penthos uses separate memory scopes:

- `conversation/` — current conversations
- `project/` — repository/project-specific knowledge
- `long_term/` — durable knowledge and preferences

Memory is external to the model weights so it can grow without
making the model itself larger.
