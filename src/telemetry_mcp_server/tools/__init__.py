"""Modular MCP tools for Telemetry MCP Server."""

from telemetry_mcp_server.tools.health import get_system_health
from telemetry_mcp_server.tools.logs import (
    list_available_services,
    read_recent_errors,
    search_logs_by_pattern,
)

__all__ = [
    "get_system_health",
    "list_available_services",
    "read_recent_errors",
    "search_logs_by_pattern",
]
