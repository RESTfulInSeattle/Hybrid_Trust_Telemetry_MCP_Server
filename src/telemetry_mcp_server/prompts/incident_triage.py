"""MCP Prompts implementation for Telemetry MCP Server.

Provides predefined diagnostic workflow templates guiding LLMs through structured
incident triage and root cause analysis.
"""

from typing import Any

from mcp.server import MCPServer


def register_prompts(mcp_server: MCPServer) -> None:
    """Register MCP prompts on the provided MCPServer instance.

    Args:
        mcp_server: Target MCPServer instance.
    """

    @mcp_server.prompt()
    def incident_triage(
        service_name: str,
        issue_description: str = "Investigate unexpected latency or error spikes.",
    ) -> list[dict[str, Any]]:
        """Standard diagnostic prompt template for triaging service incidents.

        Guides the AI model through a four-stage investigation:
        1. Query system health and foundational latency metrics.
        2. Tail error logs for the target service.
        3. Search for specific exception patterns or trace IDs.
        4. Synthesize root cause analysis and remediation steps.

        Args:
            service_name: The affected service (e.g., 'auth', 'payment', 'database', 'inference').
            issue_description: Optional description of the alert or symptom observed.
        """
        guidance = f"""You are triaging an incident affecting the '{service_name}' service.
Reported symptom: {issue_description}

Please execute this structured investigation workflow:
1. Call `get_system_health()` to determine platform-wide blast radius, active alerts, and database latency.
2. Call `read_recent_errors(service_name='{service_name}', lines=30)` to inspect recent error logs.
3. If error signatures (e.g. timeouts, 500 errors, connection pools) appear, call `search_logs_by_pattern(service_name='{service_name}', pattern='...')` to find related events.
4. Synthesize your findings:
   - What is the root cause?
   - What services or components are affected?
   - What immediate mitigation or permanent fix do you recommend?
"""
        return [
            {
                "role": "user",
                "content": guidance,
            }
        ]
