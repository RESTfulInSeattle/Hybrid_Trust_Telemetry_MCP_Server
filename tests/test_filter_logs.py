"""Tests for structured JSON log support and filter_logs tool."""

from pathlib import Path

from telemetry_mcp_server.security import TRAVERSAL_ERROR_MESSAGE
from telemetry_mcp_server.tools.logs import filter_logs, parse_log_line, parse_timestamp


def test_parse_timestamp_formats() -> None:
    """Verify parse_timestamp handles ISO-8601, space-delimited, and UTC offsets."""
    ts1 = parse_timestamp("2026-10-25T18:30:00Z")
    assert ts1 is not None
    assert ts1.year == 2026
    assert ts1.hour == 18
    assert ts1.minute == 30

    ts2 = parse_timestamp("2026-10-25 18:30:00")
    assert ts2 is not None
    assert ts2.year == 2026
    assert ts2.minute == 30

    assert parse_timestamp("invalid-date") is None
    assert parse_timestamp("") is None
    assert parse_timestamp(None) is None


def test_parse_log_line_structured_json() -> None:
    """Verify parsing a structured JSON log line."""
    json_line = (
        '{"timestamp": "2026-10-25T18:30:00Z", "level": "ERROR", '
        '"service": "auth", "trace_id": "tr-9988", "caller": "auth.server:112", '
        '"message": "Redis timeout", "extra_field": "val1"}'
    )
    entry = parse_log_line(json_line)
    assert entry.is_json is True
    assert entry.level == "ERROR"
    assert entry.severity == 40
    assert entry.trace_id == "tr-9988"
    assert entry.caller == "auth.server:112"
    assert entry.service == "auth"
    assert entry.message == "Redis timeout"
    assert entry.extra == {"extra_field": "val1"}
    assert entry.timestamp is not None
    assert entry.timestamp.hour == 18


def test_parse_log_line_text_bracket() -> None:
    """Verify parsing standard bracketed text log lines."""
    text_line = "[2026-10-25 18:40:00] [WARN] Gateway latency degraded to 920ms\n"
    entry = parse_log_line(text_line)
    assert entry.is_json is False
    assert entry.level == "WARN"
    assert entry.severity == 30
    assert "Gateway latency degraded" in entry.message
    assert entry.timestamp is not None


def test_filter_logs_by_level_json(mock_structured_log_dir: Path) -> None:
    """Verify filtering structured JSON logs by minimum severity level."""
    result = filter_logs(
        service_name="auth",
        level="ERROR",
        base_dir=mock_structured_log_dir,
    )
    assert "Redis connection timeout" in result
    assert "Session store completely unavailable" in result
    assert "Auth service initialized" not in result
    assert "High latency on token endpoint" not in result


def test_filter_logs_by_level_critical_only(mock_structured_log_dir: Path) -> None:
    """Verify filtering for CRITICAL only matches CRITICAL events."""
    result = filter_logs(
        service_name="auth",
        level="CRITICAL",
        base_dir=mock_structured_log_dir,
    )
    assert "Session store completely unavailable" in result
    assert "Redis connection timeout" not in result


def test_filter_logs_by_level_text(mock_structured_log_dir: Path) -> None:
    """Verify filtering standard bracketed text logs by level."""
    result = filter_logs(
        service_name="payment",
        level="ERROR",
        base_dir=mock_structured_log_dir,
    )
    assert "Payment capture failed: 504" in result
    assert "Payment processor worker-1 started" not in result
    assert "Gateway latency degraded" not in result


def test_filter_logs_by_timestamp_window(mock_structured_log_dir: Path) -> None:
    """Verify filtering logs within a start_time and end_time range."""
    result = filter_logs(
        service_name="auth",
        start_time="2026-10-25T18:10:00",
        end_time="2026-10-25T18:35:00",
        base_dir=mock_structured_log_dir,
    )
    assert "High latency on token endpoint" in result
    assert "Redis connection timeout" in result
    assert "Auth service initialized" not in result
    assert "Session store completely unavailable" not in result


def test_filter_logs_invalid_level(mock_structured_log_dir: Path) -> None:
    """Verify actionable error message when an invalid level is provided."""
    result = filter_logs(
        service_name="auth",
        level="SUPER_FATAL",
        base_dir=mock_structured_log_dir,
    )
    assert "Error: Invalid log level 'SUPER_FATAL'." in result
    assert "DEBUG" in result


def test_filter_logs_invalid_timestamp(mock_structured_log_dir: Path) -> None:
    """Verify actionable error message when invalid timestamp format is provided."""
    result = filter_logs(
        service_name="auth",
        start_time="yesterday-at-noon",
        base_dir=mock_structured_log_dir,
    )
    assert "Error: Invalid start_time format 'yesterday-at-noon'." in result


def test_filter_logs_adversarial_traversal(mock_structured_log_dir: Path) -> None:
    """Verify filter_logs strictly rejects path traversal attempts."""
    result = filter_logs(
        service_name="../../etc/shadow",
        level="ERROR",
        base_dir=mock_structured_log_dir,
    )
    assert f"Error: {TRAVERSAL_ERROR_MESSAGE}" in result


def test_filter_logs_nonexistent_service(mock_structured_log_dir: Path) -> None:
    """Verify filter_logs handles nonexistent service with available service discovery."""
    result = filter_logs(
        service_name="unknown_service",
        level="ERROR",
        base_dir=mock_structured_log_dir,
    )
    assert "Error: Service 'unknown_service' not found." in result
    assert "auth" in result


def test_filter_logs_no_matching_criteria(mock_structured_log_dir: Path) -> None:
    """Verify informational message when no log entries match the criteria."""
    result = filter_logs(
        service_name="payment",
        level="CRITICAL",
        base_dir=mock_structured_log_dir,
    )
    assert "No log entries" in result
    assert "payment" in result
