"""Telemetry MCP Server main application and entrypoint.

Initializes the MCPServer instance, registers diagnostic tools, telemetry resources,
and triage prompts, and configures CLI / runtime transports (stdio, SSE, streamable-http)
with first-class Hybrid-Trust security governance.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from mcp.server import MCPServer

from telemetry_mcp_server.config import settings
from telemetry_mcp_server.dlp import sanitize_payload
from telemetry_mcp_server.prompts.incident_triage import register_prompts
from telemetry_mcp_server.resources.log_streams import register_resources
from telemetry_mcp_server.tools.delegation import (
    delegate_telemetry_investigation as _delegate_telemetry_investigation,
)
from telemetry_mcp_server.tools.health import get_system_health as _get_system_health
from telemetry_mcp_server.tools.logs import (
    filter_logs as _filter_logs,
)
from telemetry_mcp_server.tools.logs import (
    list_available_services as _list_available_services,
)
from telemetry_mcp_server.tools.logs import (
    read_recent_errors as _read_recent_errors,
)
from telemetry_mcp_server.tools.logs import (
    search_logs_by_pattern as _search_logs_by_pattern,
)
from telemetry_mcp_server.tools.security_posture import (
    get_security_posture as _get_security_posture,
)

# Initialize the Model Context Protocol (MCP 2.x) server
mcp = MCPServer(
    name="TelemetryInspector",
    instructions="Governed observability and telemetry server providing system health, log inspection, and hybrid-trust security boundaries.",
)


@mcp.tool()
def get_system_health() -> str:
    """Returns the current health status of foundational services and host metrics.

    Use this tool to check if the platform, inference engine, or database
    is currently experiencing downtime or performance degradation before triaging
    individual service logs.

    Returns:
        JSON string containing status ('healthy', 'degraded', 'unhealthy'),
        active alert counts, database latency in milliseconds, active connection counts,
        host resource metrics, and local inference gateway telemetry.
    """
    return _get_system_health()


@mcp.tool()
def read_recent_errors(service_name: str, lines: int = 50) -> str:
    """Retrieve the most recent log entries for a specific service.

    Use this tool when investigating errors, checking service state, or reviewing
    recent trace events across backend services or local AI inference components.
    Output is automatically governed by active hybrid-trust DLP policies.

    Args:
        service_name: Name of the service (e.g., 'auth', 'payment', 'database', 'inference', 'matching_engine').
        lines: Number of lines to tail from the log file (1-200, default 50).

    Returns:
        Newline-delimited recent log lines, or an actionable error message if
        the service does not exist or access is denied.
    """
    return _read_recent_errors(service_name=service_name, lines=lines)


@mcp.tool()
def search_logs_by_pattern(
    service_name: str, pattern: str, max_matches: int = 20
) -> str:
    """Search recent logs for a specific service matching a regex or substring.

    Use this tool when investigating errors or looking for specific trace IDs,
    HTTP status codes, or exception names across service logs.
    Output is automatically governed by active hybrid-trust DLP policies.

    Args:
        service_name: Name of target service (e.g., 'auth', 'payment', 'database', 'inference', 'matching_engine').
        pattern: Regex or substring pattern to match (e.g., '500 Internal', 'NullPointer', 'timeout').
        max_matches: Maximum number of matching lines to return (1-100, default 20).

    Returns:
        Newline-delimited matching log lines, or an informational message if no matches.
    """
    return _search_logs_by_pattern(
        service_name=service_name,
        pattern=pattern,
        max_matches=max_matches,
    )


@mcp.tool()
def filter_logs(
    service_name: str,
    level: str | None = None,
    start_time: str | None = None,
    end_time: str | None = None,
    max_lines: int = 50,
) -> str:
    """Filter logs for a specific service by severity level and timestamp window.

    Use this tool when investigating incidents where you need only high-severity
    events (e.g., ERROR or CRITICAL) or events within a specific operational window.
    Supports both structured JSON log entries and standard bracketed syslog formats.

    Args:
        service_name: Name of target service (e.g., 'auth', 'payment', 'database', 'inference', 'matching_engine').
        level: Minimum log level to return ('DEBUG', 'INFO', 'WARN', 'ERROR', 'CRITICAL').
        start_time: Optional ISO-8601 or standard timestamp string lower bound (e.g., '2026-10-25T18:30:00').
        end_time: Optional ISO-8601 or standard timestamp string upper bound.
        max_lines: Maximum number of log lines to return (1-200, default 50).

    Returns:
        Newline-delimited matching log lines, or an informational message if no entries match.
    """
    return _filter_logs(
        service_name=service_name,
        level=level,
        start_time=start_time,
        end_time=end_time,
        max_lines=max_lines,
    )


@mcp.tool()
def delegate_telemetry_investigation(
    service_name: str,
    issue_description: str,
    max_summary_tokens: int = 400,
) -> str:
    """Delegate raw telemetry analysis and proprietary log inspection to an on-premise local sub-agent.

    Use this tool when triaging incidents that may involve proprietary business logic,
    trade secrets, internal algorithm details, or sensitive system telemetry. Instead of
    requesting raw error logs into frontier cloud model context, this hands off diagnostic
    inspection to an on-premise local model (or governed local analyzer) which synthesizes
    the findings and returns an abstract, trade-secret-free root cause summary.

    Args:
        service_name: Name of target service (e.g., 'auth', 'payment', 'database', 'inference', 'matching_engine').
        issue_description: Description of the observed symptom, alert, or diagnostic goal.
        max_summary_tokens: Maximum tokens in the returned sanitized brief (100-800, default 400).

    Returns:
        Sanitized, abstract incident brief containing root-cause analysis, affected
        components, and remediation recommendations without proprietary IP or sensitive data.
    """
    return _delegate_telemetry_investigation(
        service_name=service_name,
        issue_description=issue_description,
        max_summary_tokens=max_summary_tokens,
    )


@mcp.tool()
def get_security_posture() -> str:
    """Returns the current hybrid-trust security posture and governance telemetry.

    Use this tool to verify active trust zones (STRICT_LOCAL vs REDACTED_CLOUD),
    inspect real-time DLP redaction counts, verify path containment, and confirm
    least-privilege boundaries before performing sensitive operations.

    Returns:
        JSON string containing trust mode, active DLP rules, cumulative redaction metrics,
        monitored services, and local inference gateway connectivity.
    """
    return _get_security_posture()


@mcp.tool()
def sanitize_telemetry_payload(
    payload: str,
    trust_mode: str | None = None,
) -> str:
    """Sanitize a text or JSON telemetry payload through the server DLP engine.

    Use this tool to preview how the MCP server redacts credentials, PII/PANs,
    internal IPs, and proprietary symbols under different trust modes.

    Args:
        payload: Input text containing potential telemetry or error logs.
        trust_mode: Optional security mode ('STRICT_LOCAL', 'REDACTED_CLOUD', 'AUDIT_ONLY').
            Defaults to the server's active security_mode.

    Returns:
        Sanitized text payload.
    """
    return sanitize_payload(payload=payload, mode=trust_mode)


@mcp.tool()
def list_available_services() -> list[str]:
    """List all service identifiers available for telemetry and log inspection.

    Use this tool to discover what services (e.g., 'auth', 'payment', 'database', 'inference', 'matching_engine')
    currently have active log streams in the system.

    Returns:
        Sorted list of monitored service names.
    """
    return _list_available_services()


# Register Resources and Prompts
register_resources(mcp)
register_prompts(mcp)


def populate_sample_logs(log_dir: Path) -> None:
    """Populate initial realistic sample logs if directory is empty."""
    log_dir.mkdir(parents=True, exist_ok=True)

    auth_log = log_dir / "auth.log"
    if not auth_log.exists():
        auth_log.write_text(
            "[2026-10-25 18:30:11] [INFO] Auth service started worker-pool=4\n"
            "[2026-10-25 18:45:22] [INFO] JWT key rotation completed successfully\n"
            "[2026-10-25 18:58:04] [WARN] High latency detected on login endpoint latency_ms=452\n"
            "[2026-10-25 18:59:15] [ERROR] Connection timeout to Redis cache at 10.0.4.12:6379 after 5000ms\n"
            "[2026-10-25 18:59:18] [ERROR] Fallback session lookup failed: Redis connection unavailable\n"
            "[2026-10-25 19:01:02] [ERROR] Connection timeout to Redis cache at 10.0.4.12:6379 after 5000ms\n",
            encoding="utf-8",
        )

    payment_log = log_dir / "payment.log"
    if not payment_log.exists():
        payment_log.write_text(
            "[2026-10-25 18:31:00] [INFO] Payment gateway provider stripe-us-east connected\n"
            "[2026-10-25 18:42:10] [INFO] Processed checkout tx_id=tx_994821 amount=49.99 status=success\n"
            "[2026-10-25 18:55:33] [WARN] Gateway response time degraded gateway=stripe latency_ms=890\n"
            "[2026-10-25 19:00:12] [ERROR] Payment capture failed tx_id=tx_994825: 504 Gateway Timeout\n",
            encoding="utf-8",
        )

    database_log = log_dir / "database.log"
    if not database_log.exists():
        database_log.write_text(
            "[2026-10-25 18:30:00] [INFO] PostgreSQL connection pool initialized max_connections=50\n"
            "[2026-10-25 18:40:15] [INFO] Checkpoint starting: time\n"
            "[2026-10-25 18:40:45] [INFO] Checkpoint complete: 42 buffers written\n"
            "[2026-10-25 18:52:19] [WARN] Slow query detected duration_ms=1240 query=\"SELECT * FROM orders WHERE status = 'pending'\"\n"
            "[2026-10-25 19:02:40] [INFO] Connection pool healthy active_connections=18 idle=32\n",
            encoding="utf-8",
        )

    inference_log = log_dir / "inference.log"
    if not inference_log.exists():
        inference_log.write_text(
            "[2026-10-25 18:30:00] [INFO] vllm-mlx continuous batching engine initialized on Apple M5 Pro Metal GPU\n"
            "[2026-10-25 18:30:05] [INFO] Model mlx-community/Qwen2.5-Coder-7B-Instruct-4bit loaded into 48GB unified memory\n"
            "[2026-10-25 18:30:10] [INFO] Prefix caching enabled. KV-cache capacity: 32768 tokens\n"
            "[2026-10-25 18:35:20] [INFO] Request batch processed tokens_per_sec=74.2 clients=2\n"
            "[2026-10-25 19:05:12] [INFO] LiteLLM gateway proxy health check: 200 OK from 0.0.0.0:11434\n",
            encoding="utf-8",
        )

    # Hybrid-Trust HFT Quant scenario log
    matching_log = log_dir / "matching_engine.log"
    if not matching_log.exists():
        matching_log.write_text(
            "[2026-10-25 18:30:00] [INFO] Matching engine initialized book_depth=500 symbol=AAPL\n"
            "[2026-10-25 18:35:10] [INFO] Order book sequence initialized sequence_head=100492\n"
            "[2026-10-25 18:50:12] [WARN] Concurrency barrier latency spiked to 420ns in order_book_ring_buffer\n"
            "[2026-10-25 18:58:30] [ERROR] Lock_free_sequence_barrier hazard detected: Thread 4 missed release barrier at sequence 108422\n"
            "[2026-10-25 18:58:31] [ERROR] Desync in proprietary_pricing_model: formula_weights: [0.42, 0.18, 0.35, 0.05] buffer corrupted\n",
            encoding="utf-8",
        )


def run_server(
    transport: str = "stdio",
    host: str = "0.0.0.0",
    port: int = 8080,
    log_dir: Path | None = None,
) -> None:
    """Execute the MCP server with the specified transport protocol.

    Args:
        transport: Transport protocol ('stdio', 'sse', or 'streamable-http').
        host: Host IP to bind for network transports (SSE/HTTP).
        port: Port number for network transports.
        log_dir: Target directory containing log files.
    """
    target_log_dir = log_dir or settings.log_dir
    populate_sample_logs(target_log_dir)

    if transport == "stdio":
        mcp.run(transport="stdio")
    elif transport == "sse":
        mcp.run(transport="sse", host=host, port=port)
    elif transport == "streamable-http":
        mcp.run(transport="streamable-http", host=host, port=port)
    else:
        raise ValueError(f"Unsupported transport protocol: {transport}")


def parse_args(args: list[str] | None = None) -> argparse.Namespace:
    """Parse command line arguments for the server entrypoint."""
    parser = argparse.ArgumentParser(
        description="Telemetry MCP Server: Governed Observability & Hybrid-Trust for AI Agents",
    )
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse", "streamable-http"],
        default=settings.default_transport,
        help="Transport protocol to run (default: stdio)",
    )
    parser.add_argument(
        "--host",
        default=settings.default_host,
        help="Host IP to bind to when running network transports (default: 0.0.0.0)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=settings.default_port,
        help="Port to bind to when running network transports (default: 8080)",
    )
    parser.add_argument(
        "--log-dir",
        type=Path,
        default=settings.log_dir,
        help="Directory path containing service log files",
    )
    parser.add_argument(
        "--security-mode",
        choices=["STRICT_LOCAL", "REDACTED_CLOUD", "AUDIT_ONLY"],
        default=None,
        help="Override security mode for hybrid-trust enforcement",
    )
    return parser.parse_args(args)


if __name__ == "__main__":
    parsed = parse_args(sys.argv[1:])
    if parsed.log_dir:
        os.environ["TELEMETRY_LOG_DIR"] = str(parsed.log_dir.resolve())
    if parsed.security_mode:
        os.environ["SECURITY_MODE"] = parsed.security_mode
    run_server(
        transport=parsed.transport,
        host=parsed.host,
        port=parsed.port,
        log_dir=parsed.log_dir,
    )
