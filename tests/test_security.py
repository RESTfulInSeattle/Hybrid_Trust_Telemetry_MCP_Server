"""Tests for security sanitization and path traversal defenses."""

from pathlib import Path

import pytest

from telemetry_mcp_server.security import (
    TRAVERSAL_ERROR_MESSAGE,
    safe_resolve_log_path,
    validate_safe_path,
)


@pytest.mark.parametrize(
    "adversarial_input",
    [
        "../",
        "../../etc/passwd",
        "/etc/passwd",
        "auth\0.log",
        "..%2F..%2F",
        "..%2f..%2fetc%2fpasswd",
        "nested/../../etc/shadow",
        "auth.log/../../passwd",
        "auth;cat /etc/passwd",
        "auth|rm -rf /",
        "auth`whoami`",
        "auth$(id)",
        "auth name with spaces",
        "",
        ".",
        "..",
    ],
)
def test_path_traversal_rejections(adversarial_input: str, mock_log_dir: Path) -> None:
    """Verify that all adversarial traversal payloads are strictly rejected."""
    result = safe_resolve_log_path(adversarial_input, base_dir=mock_log_dir)
    assert not result.is_valid
    assert result.error_message == TRAVERSAL_ERROR_MESSAGE
    assert result.path is None


@pytest.mark.parametrize(
    "adversarial_input",
    [
        "../",
        "../../etc/passwd",
        "/etc/passwd",
        "auth\0.log",
        "..%2F..%2F",
    ],
)
def test_validate_safe_path_raises_exception(
    adversarial_input: str, mock_log_dir: Path
) -> None:
    """Verify that validate_safe_path raises PermissionError or ValueError for malicious inputs."""
    with pytest.raises((PermissionError, ValueError)):
        validate_safe_path(adversarial_input, base_dir=mock_log_dir)


@pytest.mark.parametrize(
    "valid_service",
    [
        "auth",
        "payment",
        "database",
        "inference-vllm",
        "gateway_litellm",
        "Service123",
    ],
)
def test_valid_service_names_allowed(valid_service: str, mock_log_dir: Path) -> None:
    """Verify that valid alphanumeric service identifiers resolve inside base directory."""
    result = safe_resolve_log_path(valid_service, base_dir=mock_log_dir)
    assert result.is_valid
    assert result.error_message is None
    assert result.path is not None
    assert result.path == (mock_log_dir / f"{valid_service}.log").resolve()
