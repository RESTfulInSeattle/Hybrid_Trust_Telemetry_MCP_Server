"""Telemetry MCP Server package.

Provides governed, secure application telemetry, system health probes,
and log diagnostics to AI models via the Model Context Protocol.
"""

import os
import sys

from telemetry_mcp_server.server import (
    get_system_health,
    list_available_services,
    mcp,
    parse_args,
    read_recent_errors,
    run_server,
    search_logs_by_pattern,
)


def main() -> None:
    """CLI script entrypoint for telemetry-mcp-server."""
    parsed = parse_args(sys.argv[1:])
    if parsed.log_dir:
        os.environ["TELEMETRY_LOG_DIR"] = str(parsed.log_dir.resolve())
    run_server(
        transport=parsed.transport,
        host=parsed.host,
        port=parsed.port,
        log_dir=parsed.log_dir,
    )


__all__ = [
    "get_system_health",
    "list_available_services",
    "main",
    "mcp",
    "read_recent_errors",
    "run_server",
    "search_logs_by_pattern",
]
