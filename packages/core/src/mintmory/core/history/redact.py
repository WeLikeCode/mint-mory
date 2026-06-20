"""
history/redact.py — secret redaction HARD GATE.

redact() is called on EVERY string before it is persisted or sent to an LLM.
scan() audits stored summaries for residual secrets (history scrub command).

Design: over-redact by intent — false positives are safe; false negatives are not.
Idempotent: running redact() twice produces the same output as running it once
because [REDACTED:...] placeholders do NOT match any pattern.
"""

from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Patterns — ordered: longest/most-specific first to avoid partial matches
# ---------------------------------------------------------------------------

# Each entry: (placeholder_label, compiled_pattern)
_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    # PEM private key blocks (multi-line, greedy enough to span the full block)
    (
        "pem_private_key",
        re.compile(
            r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----",
            re.MULTILINE,
        ),
    ),
    # Authorization header values — keep the header name, redact entire line value.
    # Capture group 1 = "Authorization: " prefix so redact() can keep it. The
    # (?!\[REDACTED:) lookahead keeps redact() idempotent AND stops scan() from
    # re-flagging an already-redacted "Authorization: [REDACTED:auth_header]" line.
    (
        "auth_header",
        re.compile(
            r"((?i:Authorization)\s*:\s*)(?!\[REDACTED:)\S[^\r\n]*",
        ),
    ),
    # JWTs: eyJ<header>.<payload>.<signature>  (base64url segments)
    (
        "jwt",
        re.compile(
            r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+",
        ),
    ),
    # Mintkey agent keys: mk_agent_<20+ alphanum>
    (
        "mk_agent",
        re.compile(
            r"mk_agent_[A-Za-z0-9]{20,}",
        ),
    ),
    # AWS access key IDs: AKIA<16 uppercase+digits>
    (
        "aws_key",
        re.compile(
            r"AKIA[0-9A-Z]{16}",
        ),
    ),
    # GitHub tokens: gh[pousr]_<20+ alphanum>
    (
        "github_token",
        re.compile(
            r"gh[pousr]_[A-Za-z0-9]{20,}",
        ),
    ),
    # OpenAI-style secret keys: sk-<20+ alphanum/dash/underscore>
    (
        "openai_sk",
        re.compile(
            r"sk-[A-Za-z0-9_-]{20,}",
        ),
    ),
    # OpenAI-style publishable keys: pk-<20+ alphanum/dash/underscore>
    (
        "openai_pk",
        re.compile(
            r"pk-[A-Za-z0-9_-]{20,}",
        ),
    ),
    # OpenAI-style restricted keys: rk-<20+ alphanum/dash/underscore>
    (
        "openai_rk",
        re.compile(
            r"rk-[A-Za-z0-9_-]{20,}",
        ),
    ),
]

# Auth header pattern index for special-case handling in redact()
_AUTH_HEADER_PAT: re.Pattern[str] = next(pat for label, pat in _PATTERNS if label == "auth_header")


def redact(text: str) -> str:
    """
    Replace every secret match with '[REDACTED:<label>]'.
    Over-redact by design. Idempotent: running twice produces the same result.
    """
    for label, pat in _PATTERNS:
        placeholder = f"[REDACTED:{label}]"
        if pat is _AUTH_HEADER_PAT:
            # Keep "Authorization: " prefix (group 1), replace rest with placeholder
            def _auth_repl(m: re.Match[str], ph: str = placeholder) -> str:
                return m.group(1) + ph

            text = pat.sub(_auth_repl, text)
        else:
            text = pat.sub(placeholder, text)
    return text


def scan(text: str) -> dict[str, int]:
    """
    Return {label: count} of secret patterns found (for the 'scrub' audit).
    No mutation — read-only over the text.
    """
    counts: dict[str, int] = {}
    for label, pat in _PATTERNS:
        matches = pat.findall(text)
        if matches:
            counts[label] = len(matches)
    return counts
