"""Tests for Dynamic Data Loss Prevention (DLP) and payload sanitization."""

from telemetry_mcp_server.dlp import (
    DLPScrubber,
    audit_metrics,
    is_luhn_valid,
    sanitize_payload,
)


def test_is_luhn_valid() -> None:
    """Verify Luhn checksum accurately distinguishes valid and invalid card numbers."""
    # Standard test card numbers (valid)
    assert is_luhn_valid("4111111111111111") is True
    assert is_luhn_valid("4111-1111-1111-1111") is True
    assert is_luhn_valid("378282246310005") is True  # Amex

    # Arbitrary sequence of 16 digits (invalid Luhn)
    assert is_luhn_valid("1234567890123456") is False
    assert is_luhn_valid("9999999999999999") is False
    assert is_luhn_valid("123") is False


def test_pci_dss_pan_redaction() -> None:
    """Verify Luhn-valid card numbers and CVVs are masked under REDACTED_CLOUD."""
    raw = (
        "Customer charged on card 4111-1111-1111-1111 with cvv: 482. "
        "Reference order ID is 1234567890123456 (not a card)."
    )
    scrubber = DLPScrubber()
    result = scrubber.scrub(raw, mode="REDACTED_CLOUD")

    # Card must be redacted with last 4 digits
    assert "[CARD_REDACTED_*1111]" in result.text
    assert "4111-1111-1111-1111" not in result.text
    # CVV must be redacted
    assert "cvv: [CVV_REDACTED]" in result.text
    # Non-Luhn candidate must NOT be redacted (prevent false positive)
    assert "1234567890123456" in result.text
    assert result.categories["pci_dss"] >= 2


def test_hipaa_pii_redaction() -> None:
    """Verify SSNs, patient IDs, emails, and phone numbers are scrubbed."""
    raw = (
        "Patient record: patient_id: PT-90218, mrn: MRN-8849. "
        "SSN is 000-12-3456, email: alice.smith@hospital.org, phone: 555-839-2041."
    )
    scrubbed = sanitize_payload(raw, mode="REDACTED_CLOUD")

    assert "[PATIENT_ID_REDACTED]" in scrubbed
    assert "PT-90218" not in scrubbed
    assert "[SSN_REDACTED]" in scrubbed
    assert "000-12-3456" not in scrubbed
    assert "[EMAIL_REDACTED]" in scrubbed
    assert "alice.smith@hospital.org" not in scrubbed
    assert "[PHONE_REDACTED]" in scrubbed
    assert "555-839-2041" not in scrubbed


def test_secrets_and_credentials_redaction() -> None:
    """Verify Bearer tokens, JWTs, AWS keys, private keys, and database URLs are scrubbed."""
    private_key = (
        "-----BEGIN RSA PRIVATE KEY-----\n"
        "MIIEowIBAAKCAQEA0Y1+MockPrivateKeyForTestingPurposesOnly==\n"
        "-----END RSA PRIVATE KEY-----"
    )
    jwt_token = (
        "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
        "eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIn0."
        "G5b0x8Z42w9v8x7MockSignatureValueHere"
    )
    raw = (
        f"Authorization: Bearer mySecretTokenLongStringWithMoreThanTwentyChars\n"
        f"Auth token: {jwt_token}\n"
        f"AWS key: AKIAIOSFODNN7EXAMPLE\n"
        f"Database connection: postgres://dbuser:superSecretPass@db.internal:5432/telemetry\n"
        f"{private_key}\n"
    )

    scrubbed = sanitize_payload(raw, mode="REDACTED_CLOUD")

    assert "Bearer [TOKEN_SCRUBBED]" in scrubbed
    assert "mySecretTokenLongStringWithMoreThanTwentyChars" not in scrubbed
    assert "[JWT_REDACTED]" in scrubbed
    assert "[AWS_KEY_REDACTED]" in scrubbed
    assert "AKIAIOSFODNN7EXAMPLE" not in scrubbed
    assert "[DATABASE_URL_REDACTED]" in scrubbed
    assert "superSecretPass" not in scrubbed
    assert "[PRIVATE_KEY_REDACTED]" in scrubbed


def test_network_topology_redaction() -> None:
    """Verify RFC 1918 private IPv4 addresses are masked."""
    raw = "Redis nodes at 10.0.4.12:6379, 172.16.8.4:6379, and 192.168.1.136:6379."
    scrubbed = sanitize_payload(raw, mode="REDACTED_CLOUD")

    assert "10.0.4.12" not in scrubbed
    assert "172.16.8.4" not in scrubbed
    assert "192.168.1.136" not in scrubbed
    assert "[INTERNAL_IP_REDACTED]" in scrubbed


def test_trade_secrets_redaction() -> None:
    """Verify proprietary HFT symbols and formula weight vectors are scrubbed."""
    raw = (
        "Hazard in order_book_ring_buffer and lock_free_sequence_barrier. "
        "formula_weights: [0.45, 0.25, 0.20, 0.10]"
    )
    scrubbed = sanitize_payload(raw, mode="REDACTED_CLOUD")

    assert "[PROPRIETARY_ALGO_REDACTED]" in scrubbed
    assert "order_book_ring_buffer" not in scrubbed
    assert "formula_weights: [PROPRIETARY_WEIGHTS_REDACTED]" in scrubbed
    assert "0.45, 0.25" not in scrubbed


def test_trust_mode_strict_local() -> None:
    """Verify STRICT_LOCAL mode permits raw telemetry over trusted boundary while recording metrics."""
    raw = "Error connecting to Redis at 10.0.4.12:6379 with ssn=000-11-2222"
    result = DLPScrubber().scrub(raw, mode="STRICT_LOCAL")

    # Raw text preserved
    assert result.text == raw
    assert "10.0.4.12" in result.text
    assert "000-11-2222" in result.text
    # Audit metrics still recorded
    assert result.redacted_count >= 2


def test_trust_mode_audit_only() -> None:
    """Verify AUDIT_ONLY mode leaves payload untouched while populating audit metrics."""
    raw = "AWS access key: AKIAIOSFODNN7EXAMPLE used"
    result = DLPScrubber().scrub(raw, mode="AUDIT_ONLY")

    assert result.text == raw
    assert "AKIAIOSFODNN7EXAMPLE" in result.text
    assert result.redacted_count == 1
    metrics = audit_metrics.to_dict()
    assert metrics["credentials"] >= 1
