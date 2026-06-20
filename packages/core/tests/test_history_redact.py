"""
Tests for mintmory.core.history.redact.

Verifies:
- Each secret pattern is redacted correctly.
- redact() is idempotent (running twice == running once).
- scan() counts matches without mutating.
- Real mk_agent / JWT / sk- samples are fully scrubbed.
- [REDACTED:...] placeholders are not double-redacted.
"""

from __future__ import annotations

from mintmory.core.history.redact import redact, scan

# Shared JWT constants (too long for inline literals per ruff E501)
_JWT_SAMPLE = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
    ".eyJzdWIiOiIxMjM0NTY3ODkwIn0"
    ".SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
)
_JWT_ED = "eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJhZ2VudCJ9.abc123def456ghi789jkl"


# ---------------------------------------------------------------------------
# Pattern coverage
# ---------------------------------------------------------------------------


class TestOpenAIStyleKeys:
    def test_sk_key_redacted(self) -> None:
        text = "key = sk-abcdefghijklmnopqrstuvwxyz123456"
        result = redact(text)
        assert "sk-" not in result
        assert "[REDACTED:openai_sk]" in result

    def test_pk_key_redacted(self) -> None:
        text = "pk-abcdefghijklmnopqrstuvwxyz123456"
        result = redact(text)
        assert "pk-" not in result
        assert "[REDACTED:openai_pk]" in result

    def test_rk_key_redacted(self) -> None:
        text = "rk-abcdefghijklmnopqrstuvwxyz123456"
        result = redact(text)
        assert "rk-" not in result
        assert "[REDACTED:openai_rk]" in result

    def test_short_sk_not_redacted(self) -> None:
        # Less than 20 chars after prefix — should NOT match
        text = "sk-tooshort"
        result = redact(text)
        assert result == text


class TestMkAgentKey:
    def test_mk_agent_redacted(self) -> None:
        text = "Bearer mk_agent_ABCDEFGHIJKLMNOPQRSTUVWXYZ1234567890"
        result = redact(text)
        assert "mk_agent_" not in result
        assert "[REDACTED:mk_agent]" in result

    def test_mk_agent_exact_20_chars(self) -> None:
        text = "mk_agent_12345678901234567890"
        result = redact(text)
        assert "[REDACTED:mk_agent]" in result

    def test_short_mk_agent_not_redacted(self) -> None:
        # 19 alphanum after prefix — should NOT match (needs {20,})
        text = "mk_agent_1234567890123456789"
        result = redact(text)
        assert "mk_agent_" in result  # not redacted


class TestJWT:
    def test_jwt_redacted(self) -> None:
        text = f"Token: {_JWT_SAMPLE}"
        result = redact(text)
        assert "eyJ" not in result
        assert "[REDACTED:jwt]" in result

    def test_jwt_in_bearer_header(self) -> None:
        text = f"Authorization: Bearer {_JWT_SAMPLE}"
        result = redact(text)
        assert "eyJ" not in result


class TestAWSKey:
    def test_aws_key_redacted(self) -> None:
        text = "AKIAIOSFODNN7EXAMPLE"
        result = redact(text)
        assert "AKIA" not in result
        assert "[REDACTED:aws_key]" in result

    def test_aws_key_wrong_length_not_redacted(self) -> None:
        # AKIA + 15 chars (needs exactly 16)
        text = "AKIA123456789012345"
        result = redact(text)
        # 15 chars instead of 16 — should NOT match
        assert "AKIA" in result


class TestGitHubTokens:
    def test_ghp_redacted(self) -> None:
        text = "ghp_abcdefghijklmnopqrstuvwxyz123456"
        result = redact(text)
        assert "ghp_" not in result
        assert "[REDACTED:github_token]" in result

    def test_gho_redacted(self) -> None:
        text = "gho_abcdefghijklmnopqrstuvwxyz123456"
        result = redact(text)
        assert "[REDACTED:github_token]" in result

    def test_ghu_redacted(self) -> None:
        text = "ghu_abcdefghijklmnopqrstuvwxyz123456"
        result = redact(text)
        assert "[REDACTED:github_token]" in result

    def test_ghs_redacted(self) -> None:
        text = "ghs_abcdefghijklmnopqrstuvwxyz123456"
        result = redact(text)
        assert "[REDACTED:github_token]" in result

    def test_ghr_redacted(self) -> None:
        text = "ghr_abcdefghijklmnopqrstuvwxyz123456"
        result = redact(text)
        assert "[REDACTED:github_token]" in result


class TestPEMKey:
    def test_pem_private_key_redacted(self) -> None:
        pem = (
            "-----BEGIN RSA PRIVATE KEY-----\n"
            "MIIEowIBAAKCAQEA2a2rwplBQLF29amygykEMmYz0+Kcj3bKBp29B4pHMz3YLFCz\n"
            "-----END RSA PRIVATE KEY-----"
        )
        result = redact(pem)
        assert "BEGIN RSA PRIVATE KEY" not in result
        assert "[REDACTED:pem_private_key]" in result

    def test_ec_private_key_redacted(self) -> None:
        pem = (
            "-----BEGIN EC PRIVATE KEY-----\n"
            "some_base64_encoded_key_data\n"
            "-----END EC PRIVATE KEY-----"
        )
        result = redact(pem)
        assert "EC PRIVATE KEY" not in result
        assert "[REDACTED:pem_private_key]" in result


class TestAuthorizationHeader:
    def test_auth_header_value_redacted(self) -> None:
        text = "Authorization: Bearer some_secret_token_12345"
        result = redact(text)
        assert "some_secret_token_12345" not in result
        # Header name should still be present
        assert "Authorization" in result

    def test_auth_header_case_insensitive(self) -> None:
        text = "authorization: token abc123def456ghi789"
        result = redact(text)
        assert "abc123def456ghi789" not in result


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------


class TestIdempotency:
    def test_redact_twice_equals_once_sk(self) -> None:
        text = "sk-abcdefghijklmnopqrstuvwxyz123456"
        once = redact(text)
        twice = redact(once)
        assert once == twice

    def test_redact_twice_equals_once_jwt(self) -> None:
        once = redact(_JWT_SAMPLE)
        twice = redact(once)
        assert once == twice

    def test_redact_twice_equals_once_mk_agent(self) -> None:
        text = "mk_agent_ABCDEFGHIJKLMNOPQRSTUVWXYZ1234567890"
        once = redact(text)
        twice = redact(once)
        assert once == twice

    def test_redact_twice_equals_once_pem(self) -> None:
        pem = (
            "-----BEGIN RSA PRIVATE KEY-----\n"
            "MIIEowIBAAKCAQEA2a2rwplBQL\n"
            "-----END RSA PRIVATE KEY-----"
        )
        once = redact(pem)
        twice = redact(once)
        assert once == twice

    def test_placeholder_not_re_redacted(self) -> None:
        # Confirm that a placeholder string does NOT get further mangled
        placeholder = "[REDACTED:openai_sk]"
        result = redact(placeholder)
        assert result == placeholder

    def test_clean_text_unchanged(self) -> None:
        text = "This is a normal sentence without any secrets."
        assert redact(text) == text


# ---------------------------------------------------------------------------
# scan()
# ---------------------------------------------------------------------------


class TestScan:
    def test_scan_counts_patterns(self) -> None:
        text = (
            "sk-abcdefghijklmnopqrstuvwxyz123456 and "
            "AKIAIOSFODNN7EXAMPLE and "
            "mk_agent_ABCDEFGHIJKLMNOPQRSTUVWXYZ1234567890"
        )
        counts = scan(text)
        assert counts.get("openai_sk", 0) == 1
        assert counts.get("aws_key", 0) == 1
        assert counts.get("mk_agent", 0) == 1

    def test_scan_no_mutation(self) -> None:
        text = "sk-abcdefghijklmnopqrstuvwxyz123456"
        _ = scan(text)
        assert "sk-" in text  # original unchanged

    def test_scan_empty_returns_empty(self) -> None:
        assert scan("") == {}

    def test_scan_clean_returns_empty(self) -> None:
        assert scan("no secrets here") == {}


# ---------------------------------------------------------------------------
# Real-world samples fully scrubbed
# ---------------------------------------------------------------------------


class TestRealWorldSamples:
    def test_mk_agent_sample_fully_scrubbed(self) -> None:
        sample = "use key mk_agent_ABC123DEF456GHI789JKL012MNO345PQR678 to auth"
        result = redact(sample)
        assert "mk_agent_" not in result
        assert "[REDACTED:mk_agent]" in result

    def test_jwt_sample_fully_scrubbed(self) -> None:
        result = redact(_JWT_ED)
        assert "eyJ" not in result
        assert "[REDACTED:jwt]" in result

    def test_sk_sample_fully_scrubbed(self) -> None:
        sample = "OPENAI_API_KEY=sk-proj-abcdefghijklmnopqrstuvwxyz12345678901234"
        result = redact(sample)
        assert "sk-proj-" not in result
        assert "[REDACTED:openai_sk]" in result

    def test_combined_sample_fully_scrubbed(self) -> None:
        """A transcript with multiple secret types is fully cleaned."""
        sample = (
            "Session started. API key: sk-abcdefghijklmnopqrstuvwxyz123456\n"
            "Agent token: mk_agent_ABCDEFGHIJKLMNOPQRSTUVWXYZ1234567890\n"
            f"Authorization: Bearer {_JWT_SAMPLE}\n"
            "AWS: AKIAIOSFODNN7EXAMPLE\n"
            "GH: ghp_abcdefghijklmnopqrstuvwxyz123456"
        )
        result = redact(sample)
        assert "sk-abcdefghij" not in result
        assert "mk_agent_ABCDEFGHIJ" not in result
        assert "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9" not in result
        assert "AKIAIOSFODNN7EXAMPLE" not in result
        assert "ghp_abcdefghij" not in result


def test_authorization_redaction_scans_clean() -> None:
    """A redacted Authorization line must NOT be re-flagged by scan() (scrub bug)."""
    raw = "Authorization: Bearer eyJabc.def.ghi and key sk-AAAAAAAAAAAAAAAAAAAAAA"
    red = redact(raw)
    assert "Bearer eyJabc" not in red
    assert scan(red) == {}  # scrub audit passes clean on already-redacted text
    assert redact(red) == red  # idempotent


def test_authorization_value_redacted_header_kept() -> None:
    red = redact("Authorization: Bearer supersecretvalue123456")
    assert red.startswith("Authorization: ")
    assert "supersecretvalue123456" not in red
    assert "[REDACTED:auth_header]" in red
