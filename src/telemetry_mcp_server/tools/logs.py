"""Log inspection, filtering, and search tools for Telemetry MCP Server.

Provides bounded tailing, regex pattern searching, structured JSON log parsing,
and severity/time-window filtering with strict path traversal safeguards and
governed DLP sanitization.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from telemetry_mcp_server.config import settings
from telemetry_mcp_server.dlp import sanitize_payload
from telemetry_mcp_server.security import ALLOWED_SERVICE_REGEX, safe_resolve_log_path

# Standard log severity mappings
LOG_LEVEL_SEVERITY: dict[str, int] = {
    "TRACE": 5,
    "DEBUG": 10,
    "INFO": 20,
    "NOTICE": 25,
    "WARN": 30,
    "WARNING": 30,
    "ERROR": 40,
    "ERR": 40,
    "CRITICAL": 50,
    "FATAL": 50,
}

_TEXT_LOG_REGEX = re.compile(
    r"^(?:\[(?P<ts1>[^\]]+)\]\s*)?(?:\[(?P<lvl1>[A-Za-z]+)\]|\b(?P<lvl2>DEBUG|INFO|WARN(?:ING)?|ERROR|ERR|CRITICAL|FATAL)\b)(?:\s*\[(?P<ts2>[^\]]+)\])?\s*(?P<msg>.*)$",
    re.IGNORECASE,
)


@dataclass
class ParsedLogEntry:
    """Represents a structured or semi-structured log entry."""

    raw_line: str
    timestamp: datetime | None = None
    level: str | None = None
    severity: int = 0
    trace_id: str | None = None
    caller: str | None = None
    service: str | None = None
    message: str = ""
    extra: dict[str, Any] = field(default_factory=dict)
    is_json: bool = False


def parse_timestamp(value: str | datetime | None) -> datetime | None:
    """Parse string or datetime into a normalized timezone-naive UTC datetime.

    Args:
        value: Input timestamp string or datetime object.

    Returns:
        Normalized datetime object or None if unparseable.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            return value.astimezone(UTC).replace(tzinfo=None)
        return value

    val = str(value).strip()
    if not val:
        return None

    # Strip trailing Z if present for ISO parsing
    if val.endswith(("Z", "z")):
        val = val[:-1] + "+00:00"

    try:
        dt = datetime.fromisoformat(val)
        if dt.tzinfo is not None:
            return dt.astimezone(UTC).replace(tzinfo=None)
        return dt
    except ValueError:
        pass

    # Fallback common formats
    for fmt in (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y/%m/%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d",
    ):
        try:
            return datetime.strptime(val, fmt)
        except ValueError:
            continue

    return None


def parse_log_line(line: str) -> ParsedLogEntry:
    """Parse a single log line into a ParsedLogEntry supporting both JSON and text formats.

    Args:
        line: Raw log line string.

    Returns:
        ParsedLogEntry with extracted metadata.
    """
    stripped = line.strip()
    if not stripped:
        return ParsedLogEntry(raw_line=line)

    # Fast-path: Structured JSON line
    if stripped.startswith("{") and stripped.endswith("}"):
        try:
            data = json.loads(stripped)
            if isinstance(data, dict):
                # Extract level
                raw_level = (
                    data.get("level")
                    or data.get("severity")
                    or data.get("log_level")
                    or data.get("status")
                )
                level_str = str(raw_level).upper() if raw_level else None
                severity = LOG_LEVEL_SEVERITY.get(level_str or "", 0)

                # Extract timestamp
                raw_ts = (
                    data.get("timestamp")
                    or data.get("time")
                    or data.get("@timestamp")
                    or data.get("datetime")
                )
                ts = parse_timestamp(raw_ts)

                # Extract trace ID & caller
                trace_id = (
                    data.get("trace_id")
                    or data.get("traceId")
                    or data.get("request_id")
                    or data.get("requestId")
                    or data.get("tx_id")
                )
                caller = (
                    data.get("caller")
                    or data.get("logger")
                    or data.get("component")
                    or data.get("module")
                )
                service = data.get("service") or data.get("service_name")
                message = str(
                    data.get("message") or data.get("msg") or data.get("event") or ""
                )

                extra = {
                    k: v
                    for k, v in data.items()
                    if k
                    not in (
                        "level",
                        "severity",
                        "log_level",
                        "status",
                        "timestamp",
                        "time",
                        "@timestamp",
                        "datetime",
                        "trace_id",
                        "traceId",
                        "request_id",
                        "requestId",
                        "tx_id",
                        "caller",
                        "logger",
                        "component",
                        "module",
                        "service",
                        "service_name",
                        "message",
                        "msg",
                        "event",
                    )
                }

                return ParsedLogEntry(
                    raw_line=line,
                    timestamp=ts,
                    level=level_str,
                    severity=severity,
                    trace_id=str(trace_id) if trace_id else None,
                    caller=str(caller) if caller else None,
                    service=str(service) if service else None,
                    message=message,
                    extra=extra,
                    is_json=True,
                )
        except json.JSONDecodeError:
            pass

    # Standard Text / Bracket Format
    m = _TEXT_LOG_REGEX.match(stripped)
    if m:
        raw_ts = m.group("ts1") or m.group("ts2")
        raw_lvl = m.group("lvl1") or m.group("lvl2")
        msg = m.group("msg") or ""

        ts = parse_timestamp(raw_ts) if raw_ts else None
        lvl = raw_lvl.upper() if raw_lvl else None
        sev = LOG_LEVEL_SEVERITY.get(lvl or "", 0)

        # Attempt to extract trace_id from message (e.g. trace_id=tr-123 or tx_id=tx_456)
        trace_match = re.search(r"\b(?:trace_id|request_id|tx_id|tx)=([^\s,;]+)", msg)
        trace_id_val = trace_match.group(1) if trace_match else None

        return ParsedLogEntry(
            raw_line=line,
            timestamp=ts,
            level=lvl,
            severity=sev,
            trace_id=trace_id_val,
            caller=None,
            service=None,
            message=msg,
            extra={},
            is_json=False,
        )

    return ParsedLogEntry(raw_line=line)


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

        raw_output = "".join(processed)
        return sanitize_payload(raw_output)
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
        raw_output = "".join(matches[-bounded_matches:])
        return sanitize_payload(raw_output)
    except OSError as e:
        return f"Failed to search logs for service '{service_name}': {e!s}"


def filter_logs(
    service_name: str,
    level: str | None = None,
    start_time: str | None = None,
    end_time: str | None = None,
    max_lines: int = 50,
    base_dir: Path | str | None = None,
) -> str:
    """Filter logs for a specific service by severity level and timestamp window.

    Use this tool when investigating incidents where you need only high-severity
    events (e.g., ERROR or CRITICAL) or events within a specific operational window.
    Supports both structured JSON log entries and standard bracketed syslog formats.

    Args:
        service_name: Name of target service (e.g., 'auth', 'payment', 'database', 'inference').
        level: Minimum log level to return ('DEBUG', 'INFO', 'WARN', 'ERROR', 'CRITICAL').
        start_time: ISO-8601 or standard timestamp string (e.g., '2026-10-25T18:30:00').
        end_time: Optional ISO-8601 or standard timestamp string upper bound.
        max_lines: Maximum number of log lines to return (1-200, default 50).
        base_dir: Optional base directory override for tests or custom environments.

    Returns:
        Newline-delimited matching log lines, or an informational message if no entries match.
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

    # Validate level threshold if provided
    min_severity: int = 0
    if level is not None:
        normalized_level = level.strip().upper()
        if normalized_level not in LOG_LEVEL_SEVERITY:
            valid_levels = sorted({"DEBUG", "INFO", "WARN", "ERROR", "CRITICAL"})
            return f"Error: Invalid log level '{level}'. Valid levels: {valid_levels}"
        min_severity = LOG_LEVEL_SEVERITY[normalized_level]

    # Validate timestamp bounds if provided
    start_dt: datetime | None = None
    if start_time is not None:
        start_dt = parse_timestamp(start_time)
        if start_dt is None:
            return (
                f"Error: Invalid start_time format '{start_time}'. "
                "Expected ISO-8601 string (e.g., '2026-10-25T18:30:00' or '2026-10-25 18:30:00')."
            )

    end_dt: datetime | None = None
    if end_time is not None:
        end_dt = parse_timestamp(end_time)
        if end_dt is None:
            return (
                f"Error: Invalid end_time format '{end_time}'. "
                "Expected ISO-8601 string (e.g., '2026-10-25T19:00:00' or '2026-10-25 19:00:00')."
            )

    bounded_lines = max(1, min(max_lines, settings.max_lines))
    matching_lines: list[str] = []

    try:
        with open(log_path, encoding="utf-8", errors="replace") as f:
            for line in f:
                if not line.strip():
                    continue

                entry = parse_log_line(line)

                # Severity filtering
                if min_severity > 0 and entry.severity < min_severity:
                    continue

                # Timestamp window filtering
                if start_dt is not None and (
                    entry.timestamp is None or entry.timestamp < start_dt
                ):
                    continue

                if end_dt is not None and (
                    entry.timestamp is None or entry.timestamp > end_dt
                ):
                    continue

                # Format and line-length ceiling
                out_line = line if line.endswith("\n") else line + "\n"
                if len(out_line) > settings.max_line_length:
                    out_line = (
                        out_line[: settings.max_line_length] + " ... [truncated]\n"
                    )

                matching_lines.append(out_line)

        if not matching_lines:
            criteria_desc = []
            if level:
                criteria_desc.append(f"level>={level.upper()}")
            if start_time:
                criteria_desc.append(f"start_time>={start_time}")
            if end_time:
                criteria_desc.append(f"end_time<={end_time}")
            desc_str = (
                f" matching criteria [{', '.join(criteria_desc)}]"
                if criteria_desc
                else ""
            )
            return f"No log entries{desc_str} found in service '{service_name}'."

        raw_output = "".join(matching_lines[-bounded_lines:])
        return sanitize_payload(raw_output)

    except OSError as e:
        return f"Failed to filter logs for service '{service_name}': {e!s}"
