"""Tests for security posture and trust observability tools."""

import json

from telemetry_mcp_server.dlp import audit_metrics, sanitize_payload
from telemetry_mcp_server.tools.security_posture import get_security_posture


def test_get_security_posture_structure() -> None:
    """Verify get_security_posture returns valid JSON with all required hybrid-trust governance keys."""
    raw = get_security_posture()
    data = json.loads(raw)

    assert isinstance(data, dict)
    assert "hybrid_trust_posture" in data
    assert "active_security_mode" in data["hybrid_trust_posture"]
    assert "dlp_enabled" in data["hybrid_trust_posture"]

    assert "dlp_scrubbers" in data
    assert "pci_dss" in data["dlp_scrubbers"]
    assert "hipaa_pii" in data["dlp_scrubbers"]
    assert "secrets_credentials" in data["dlp_scrubbers"]

    assert "redaction_metrics" in data
    assert "total_redactions" in data["redaction_metrics"]

    assert "governed_boundaries" in data
    assert "context_window_caps" in data["governed_boundaries"]
    assert "local_inference_gateway" in data


def test_security_posture_reflects_redactions() -> None:
    """Verify that redaction metrics increment dynamically when sensitive data is processed."""
    audit_metrics.reset()

    # Trigger a redaction
    sanitize_payload("Secret key leaked: AKIAIOSFODNN7EXAMPLE", mode="REDACTED_CLOUD")

    raw = get_security_posture()
    data = json.loads(raw)

    metrics = data["redaction_metrics"]
    assert metrics["credentials"] >= 1
    assert metrics["total_redactions"] >= 1
