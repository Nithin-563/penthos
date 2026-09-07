"""Penthos guardrails: input filter and output sanitizer.

Two focused layers, intentionally simple and auditable:

  - Guard.check_input(text)  -> True/False + a reason. Blocks obvious
    jailbreak/prompt-injection patterns and anything that asks the model to
    act outside its identity, reveal hidden instructions, or exfiltrate the
    system prompt. It is a heuristic layer, not a guarantee: it detects
    common phrasing, not every possible paraphrase.
  - Guard.sanitize_output(text) -> scrubs recognizable secret material from
    model output so a key/credential can never be echoed back to the user.

Deployment note: the model is open-weight. Anyone hosting the weights can
remove these layers, so treat them as a baseline (not a vault) and enforce
identity/auth at the serving layer (see docs/hosting.md and the benchmark
report).
"""

import re

# ---------------------------------------------------------------------------
# Input attack patterns
# ---------------------------------------------------------------------------

_ATTACK_PATTERNS = (
    # Direct system-prompt theft / hidden-instruction override.
    (r"ignore\s+(all\s+)?previous\s+instructions", "overrides previous instructions"),
    (r"(repeat|reveal|print|show|paste)\s+(your\s+)?(system|developer|hidden)\s+prompt", "tries to extract the system prompt"),
    (r"output\s+the\s+instructions\s+above", "tries to roll back hidden instructions"),
    (r"(act|pretend|behave)\s+as\s+an?\s+unrestricted", "asks for a removed-limits persona"),
    (r"(dan\b|developer\s+mode|jailbreak|prompt\s+injection)", "invokes jailbreak framing"),
    (r"forget\s+(everything|all)\s+(above|the|instructions)", "asks to override the system prompt"),
    (r"ignore\s+your\s+(identity|rules|guardrails)", "asks to drop its guardrails"),
    # Secret exfiltration.
    (r"(print|show|display|reveal)\s+(me\s+)?(the\s+)?(secret|key|credential|password|token)", "asks to reveal secrets"),
    (r"(disclose|leak)\s+.*(api|secret|credential)", "asks to disclose secrets"),
)

# ---------------------------------------------------------------------------
# Output scrub patterns: recognizable secrets should never reach the terminal.
# ---------------------------------------------------------------------------

_SECRET_SCRUB_PATTERNS = (
    r"\b(sk|pk|ghp|gho|ghu|AKIA|xox[tbsap]|eyJhbGciOi)[A-Za-z0-9_\-\.]{12,}\b",
    r"AKIA[0-9A-Z]{16}",
    r"(-----BEGIN\s+(RSA\s+|OPENSSH\s+|EC\s+)?PRIVATE KEY-----.*?-----END\s+(RSA\s+|OPENSSH\s+|EC\s+)?PRIVATE KEY-----)",
    r"Bearer\s+[A-Za-z0-9\-\._~\+\/]{16,}=?",
)

_SCRUB_TEMPLATE = "[REDACTED: %s]"


class Guard:
    def check_input(self, text: str) -> tuple[bool, str | None]:
        """Return (blocked, reason). blocked=True when the request is an attack."""
        lowered = (text or "").lower()
        for pattern, reason in _ATTACK_PATTERNS:
            if re.search(pattern, lowered):
                return True, reason
        return False, None

    def sanitize_output(self, text: str) -> str:
        """Scrub recognizable secrets from model output."""
        return re.sub(
            "|".join(_SECRET_SCRUB_PATTERNS),
            lambda match: _SCRUB_TEMPLATE % match.group(0)[:12],
            (text or ""),
        )

    def refusal(self, reason: str) -> str:
        return (
            "I can't help with that. "
            f"Reason: the request {reason}, which crosses Penthos's safety "
            "boundaries (Deoid security policy)."
        )