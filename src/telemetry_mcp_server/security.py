"""Security and path sanitization module for Telemetry MCP Server.

Enforces defense-in-depth against directory traversal, null-byte injection,
and arbitrary filesystem access.
"""

import os
import re
import urllib.parse
from dataclasses import dataclass
from pathlib import Path

from telemetry_mcp_server.config import settings

ALLOWED_SERVICE_REGEX = re.compile(r"^[a-zA-Z0-9_-]+$")
TRAVERSAL_ERROR_MESSAGE = (
    "Invalid service name or path traversal violation. Access denied."
)


@dataclass(frozen=True)
class ValidationResult:
    """Result of path validation and sanitization checks."""

    is_valid: bool
    path: Path | None = None
    error_message: str | None = None


def safe_resolve_log_path(
    service_name: str,
    base_dir: Path | str | None = None,
) -> ValidationResult:
    """Sanitize service identifier and resolve path strictly inside base directory.

    Args:
        service_name: Target service identifier (e.g., 'auth', 'database').
        base_dir: Optional base directory to enforce containment against.
            Defaults to configured settings.log_dir.

    Returns:
        ValidationResult with resolved Path if valid, or error_message if denied.
    """
    if not service_name or not isinstance(service_name, str):
        return ValidationResult(
            is_valid=False,
            error_message=TRAVERSAL_ERROR_MESSAGE,
        )

    # Layer 1: Check for null-byte injection
    if "\0" in service_name:
        return ValidationResult(
            is_valid=False,
            error_message=TRAVERSAL_ERROR_MESSAGE,
        )

    # Layer 2: Check for URL-encoded traversal characters (%2e, %2f, etc.)
    decoded = urllib.parse.unquote(service_name)
    if ".." in decoded or "/" in decoded or "\\" in decoded or "\0" in decoded:
        return ValidationResult(
            is_valid=False,
            error_message=TRAVERSAL_ERROR_MESSAGE,
        )

    # Layer 3: Whitelist alphanumeric + hyphen + underscore characters only
    if not ALLOWED_SERVICE_REGEX.match(service_name):
        return ValidationResult(
            is_valid=False,
            error_message=TRAVERSAL_ERROR_MESSAGE,
        )

    # Layer 4: Canonical absolute path resolution and containment check
    resolved_base = Path(base_dir or settings.log_dir).resolve()
    candidate_path = (resolved_base / f"{service_name}.log").resolve()

    try:
        # Verify commonpath strictly matches canonical base
        if os.path.commonpath([str(resolved_base), str(candidate_path)]) != str(
            resolved_base
        ):
            return ValidationResult(
                is_valid=False,
                error_message=TRAVERSAL_ERROR_MESSAGE,
            )
    except (ValueError, OSError):
        return ValidationResult(
            is_valid=False,
            error_message=TRAVERSAL_ERROR_MESSAGE,
        )

    # Ensure candidate path is not the root or directory itself
    if candidate_path == resolved_base:
        return ValidationResult(
            is_valid=False,
            error_message=TRAVERSAL_ERROR_MESSAGE,
        )

    return ValidationResult(is_valid=True, path=candidate_path)


def validate_safe_path(
    service_name: str,
    base_dir: Path | str | None = None,
) -> Path:
    """Validate path and raise exception if invalid.

    Args:
        service_name: Target service identifier.
        base_dir: Base directory to contain files within.

    Returns:
        Resolved safe Path object.

    Raises:
        ValueError: If service name format is invalid.
        PermissionError: If path traversal violation is detected.
    """
    result = safe_resolve_log_path(service_name, base_dir=base_dir)
    if not result.is_valid:
        if (
            ".." in service_name
            or "/" in service_name
            or "\\" in service_name
            or "\0" in service_name
        ):
            raise PermissionError(result.error_message)
        raise ValueError(result.error_message)
    assert result.path is not None
    return result.path
