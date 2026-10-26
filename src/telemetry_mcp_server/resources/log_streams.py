"""MCP Resources implementation for Telemetry MCP Server.

Exposes telemetry data streams over standard MCP URIs (telemetry://health,
telemetry://services, telemetry://logs/{service}).
"""

import json

from mcp.server import MCPServer

from telemetry_mcp_server.tools.health import get_system_health
from telemetry_mcp_server.tools.logs import list_available_services, read_recent_errors


def register_resources(mcp_server: MCPServer) -> None:
    """Register MCP resources on the provided MCPServer instance.

    Args:
        mcp_server: Target MCPServer instance.
    """

    @mcp_server.resource("telemetry://health")
    def get_health_resource() -> str:
        """Resource exposing system health and telemetry metrics."""
        return get_system_health()

    @mcp_server.resource("telemetry://services")
    def get_services_resource() -> str:
        """Resource exposing the list of monitored services."""
        return json.dumps(list_available_services(), indent=2)

    @mcp_server.resource("telemetry://logs/{service}")
    def get_service_logs_resource(service: str) -> str:
        """Resource exposing recent log entries for a given service."""
        return read_recent_errors(service_name=service, lines=50)
