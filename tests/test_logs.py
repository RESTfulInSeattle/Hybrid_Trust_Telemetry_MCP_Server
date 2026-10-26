"""Tests for log inspection and search tools."""

from pathlib import Path

from telemetry_mcp_server.security import TRAVERSAL_ERROR_MESSAGE
from telemetry_mcp_server.tools.logs import (
    list_available_services,
    read_recent_errors,
    search_logs_by_pattern,
)


def test_list_available_services(mock_log_dir: Path) -> None:
    """Verify that all monitored services are detected and returned sorted."""
    services = list_available_services(base_dir=mock_log_dir)
    assert services == ["auth", "database", "payment"]


def test_read_recent_errors_happy_path(mock_log_dir: Path) -> None:
    """Verify reading recent lines from an existing log."""
    content = read_recent_errors(service_name="auth", lines=2, base_dir=mock_log_dir)
    lines = content.strip().split("\n")
    assert len(lines) == 2
    assert "Redis cache" in content
    assert "Token validation failed" in content


def test_read_recent_errors_nonexistent_service(mock_log_dir: Path) -> None:
    """Verify graceful error reporting when service log does not exist."""
    result = read_recent_errors(service_name="billing", base_dir=mock_log_dir)
    assert "Error: Service 'billing' not found." in result
    assert "auth" in result
    assert "database" in result
    assert "payment" in result


def test_read_recent_errors_adversarial_traversal(mock_log_dir: Path) -> None:
    """Verify that traversal attempts return strict security denial messages."""
    result = read_recent_errors(
        service_name="../../../../etc/passwd", base_dir=mock_log_dir
    )
    assert f"Error: {TRAVERSAL_ERROR_MESSAGE}" in result


def test_search_logs_by_pattern_found(mock_log_dir: Path) -> None:
    """Verify matching pattern search in log lines."""
    result = search_logs_by_pattern(
        service_name="auth",
        pattern="Redis",
        max_matches=10,
        base_dir=mock_log_dir,
    )
    assert "Connection timeout to Redis cache" in result


def test_search_logs_by_pattern_not_found(mock_log_dir: Path) -> None:
    """Verify message when pattern does not match any lines."""
    result = search_logs_by_pattern(
        service_name="auth",
        pattern="OutOfMemoryError",
        max_matches=10,
        base_dir=mock_log_dir,
    )
    assert "No lines matching pattern 'OutOfMemoryError' found" in result


def test_search_logs_by_pattern_regex(mock_log_dir: Path) -> None:
    """Verify regex pattern matching works properly."""
    result = search_logs_by_pattern(
        service_name="payment",
        pattern=r"5\d\d",
        max_matches=5,
        base_dir=mock_log_dir,
    )
    assert "504" in result


def test_search_logs_by_pattern_traversal(mock_log_dir: Path) -> None:
    """Verify search tool rejects directory traversal."""
    result = search_logs_by_pattern(
        service_name="../../etc/passwd",
        pattern="root",
        base_dir=mock_log_dir,
    )
    assert f"Error: {TRAVERSAL_ERROR_MESSAGE}" in result
