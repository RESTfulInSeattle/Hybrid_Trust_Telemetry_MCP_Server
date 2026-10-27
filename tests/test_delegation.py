"""Tests for sub-agent delegation tool in Hybrid-Trust architecture."""

from pathlib import Path

from telemetry_mcp_server.security import TRAVERSAL_ERROR_MESSAGE
from telemetry_mcp_server.tools.delegation import delegate_telemetry_investigation


def test_delegation_happy_path(mock_structured_log_dir: Path) -> None:
    """Verify sub-agent delegation synthesizes root cause without leaking proprietary symbols."""
    brief = delegate_telemetry_investigation(
        service_name="matching_engine",
        issue_description="Investigate order matching sequence desync",
        max_summary_tokens=300,
        base_dir=mock_structured_log_dir,
    )

    # Must contain sub-agent diagnostic structure
    assert "Local Sub-Agent Telemetry Briefing" in brief or "Sub-Agent" in brief
    assert "Root Cause" in brief

    # Must contain abstracted computer science concept
    assert (
        "lock-free" in brief.lower()
        or "synchronization" in brief.lower()
        or "concurrency" in brief.lower()
    )

    # Must NOT leak raw formula weights into cloud briefing
    assert "[0.1, 0.4, 0.5]" not in brief


def test_delegation_redis_timeout_synthesis(mock_structured_log_dir: Path) -> None:
    """Verify sub-agent delegation correctly diagnoses Redis cache timeout cascade."""
    brief = delegate_telemetry_investigation(
        service_name="auth",
        issue_description="Login service failing with 500 status codes",
        base_dir=mock_structured_log_dir,
    )
    assert "cache" in brief.lower() or "redis" in brief.lower()
    assert "Recommended Next Steps" in brief


def test_delegation_nonexistent_service(mock_structured_log_dir: Path) -> None:
    """Verify delegation returns actionable service discovery error for nonexistent service."""
    result = delegate_telemetry_investigation(
        service_name="unknown_worker",
        issue_description="Latency alert",
        base_dir=mock_structured_log_dir,
    )
    assert "Error: Service 'unknown_worker' not found." in result
    assert "auth" in result


def test_delegation_adversarial_traversal(mock_structured_log_dir: Path) -> None:
    """Verify delegation strictly rejects path traversal attempts."""
    result = delegate_telemetry_investigation(
        service_name="../../etc/passwd",
        issue_description="Exfiltrate shadow",
        base_dir=mock_structured_log_dir,
    )
    assert f"Error: {TRAVERSAL_ERROR_MESSAGE}" in result
