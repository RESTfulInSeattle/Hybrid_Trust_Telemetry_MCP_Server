"""Log inspection and search tools for Telemetry MCP Server.

Provides bounded tailing, regex pattern searching, and service discovery
with strict path traversal safeguards.
"""

import re
from pathlib import Path

from telemetry_mcp_server.config import settings
from telemetry_mcp_server.security import ALLOWED_SERVICE_REGEX, safe_resolve_log_path


def list_available_services(base_dir: Path | str | None = None) -> list[str]:
    """Scan the log directory and return a sorted list of monitored services.

    Args:
        base_dir: Directory containing log files. Defaults to configured log_dir.

    Returns:
        Sorted list of service identifiers available for inspection.
    """
    target_dir = Path(base_dir or settings.log_dir).resolve()
    if not target_dir.exists() or not target_dir.is_dir():
        return []

    services: list[str] = []
    for item in target_dir.glob("*.log"):
        if item.is_file() and ALLOWED_SERVICE_REGEX.match(item.stem):
            services.append(item.stem)

    return sorted(services)


def read_recent_errors(
    service_name: str,
    lines: int = 50,
    base_dir: Path | str | None = None,
) -> str:
    """Retrieve the most recent log entries for a specific service.

    Use this tool when investigating errors, checking service state, or reviewing
    recent trace events across backend services or local AI inference components.

    Args:
        service_name: Name of the service (e.g., 'auth', 'payment', 'database', 'inference').
        lines: Number of lines to tail from the log file (1-200, default 50).
        base_dir: Optional base directory override for tests or custom environments.

    Returns:
        Newline-delimited recent log lines, or an actionable error message if
        the service does not exist or access is denied.
    """
    validation = safe_resolve_log_path(service_name, base_dir=base_dir)
    if not validation.is_valid or validation.path is None:
        return f"Error: {validation.error_message}"

    log_path = validation.path
    if not log_path.exists() or not log_path.is_file():
        available = list_available_services(base_dir=base_dir)
        return (
            f"Error: Service '{service_name}' not found. "
            f"Available services: {available}"
        )

    # Enforce context window bounds (1 to max_lines)
    bounded_lines = max(1, min(lines, settings.max_lines))

    try:
        with open(log_path, encoding="utf-8", errors="replace") as f:
            all_lines = f.readlines()

        if not all_lines:
            return f"No log entries found in service '{service_name}'."

        recent_lines = all_lines[-bounded_lines:]

        # Enforce line length ceiling to prevent prompt explosion
        processed: list[str] = []
        for line in recent_lines:
            if len(line) > settings.max_line_length:
                line = line[: settings.max_line_length] + " ... [truncated]\n"
            processed.append(line)

        return "".join(processed)
    except OSError as e:
        return f"Failed to read logs for service '{service_name}': {e!s}"


def search_logs_by_pattern(
    service_name: str,
    pattern: str,
    max_matches: int = 20,
    base_dir: Path | str | None = None,
) -> str:
    """Search recent logs for a specific service matching a regex or substring.

    Use this tool when investigating errors or looking for specific trace IDs,
    HTTP status codes, or exception names across service logs.

    Args:
        service_name: Name of target service (e.g., 'auth', 'payment', 'database', 'inference').
        pattern: Regex or substring pattern to match (e.g., '500 Internal', 'NullPointer', 'timeout').
        max_matches: Maximum number of matching lines to return (1-100, default 20).
        base_dir: Optional base directory override for tests or custom environments.

    Returns:
        Newline-delimited matching log lines, or an informational message if no matches.
    """
    validation = safe_resolve_log_path(service_name, base_dir=base_dir)
    if not validation.is_valid or validation.path is None:
        return f"Error: {validation.error_message}"

    log_path = validation.path
    if not log_path.exists() or not log_path.is_file():
        available = list_available_services(base_dir=base_dir)
        return (
            f"Error: Service '{service_name}' not found. "
            f"Available services: {available}"
        )

    bounded_matches = max(1, min(max_matches, 100))

    try:
        compiled_regex: re.Pattern[str] | None = re.compile(pattern, re.IGNORECASE)
    except re.error:
        compiled_regex = None

    matches: list[str] = []
    pattern_lower = pattern.lower()

    try:
        with open(log_path, encoding="utf-8", errors="replace") as f:
            for line in f:
                matched = (
                    compiled_regex.search(line) is not None
                    if compiled_regex
                    else (pattern_lower in line.lower())
                )
                if matched:
                    if len(line) > settings.max_line_length:
                        line = line[: settings.max_line_length] + " ... [truncated]\n"
                    matches.append(line)

        if not matches:
            return f"No lines matching pattern '{pattern}' found in service '{service_name}'."

        # Return the most recent matches up to bounded_matches
        return "".join(matches[-bounded_matches:])
    except OSError as e:
        return f"Failed to search logs for service '{service_name}': {e!s}"
