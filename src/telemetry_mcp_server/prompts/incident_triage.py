"""MCP Prompts implementation for Telemetry MCP Server.

Provides predefined diagnostic workflow templates guiding LLMs through structured
incident triage, root cause analysis, and hybrid-trust multi-tier investigations.
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
        2. Tail error logs or filter by severity for the target service.
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
2. Call `filter_logs(service_name='{service_name}', level='ERROR', max_lines=30)` to inspect recent high-severity errors.
3. If error signatures (e.g. timeouts, 500 errors, connection pools) appear, call `search_logs_by_pattern(service_name='{service_name}', pattern='...')` to correlate related events.
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

    @mcp_server.prompt()
    def hybrid_trust_triage(
        service_name: str,
        issue_description: str = "Investigate incident in proprietary or regulated service.",
    ) -> list[dict[str, Any]]:
        """Governed diagnostic prompt template for Hybrid-Trust enterprise environments.

        Instructs cloud frontier models to observe trust boundaries, leverage
        sub-agent delegation for proprietary services, and avoid leaking trade secrets.

        Args:
            service_name: Target service (e.g., 'matching_engine', 'payment', 'inference').
            issue_description: Observed anomaly or alert.
        """
        guidance = f"""You are triaging an incident in a Hybrid-Trust governed enterprise environment.
Target Service: {service_name}
Reported Issue: {issue_description}

SECURITY DIRECTIVE:
If '{service_name}' contains trade secrets, proprietary algorithms, or regulated data (e.g. cardholder PANs, patient identifiers), you MUST NOT ingest raw logs into cloud context.

Recommended Hybrid-Trust Workflow:
1. Call `get_security_posture()` to verify active security mode and DLP scrubbers.
2. Call `delegate_telemetry_investigation(service_name='{service_name}', issue_description='{issue_description}')`
   This delegates raw log inspection to an on-premise local sub-agent, returning an abstract, trade-secret-free root cause summary.
3. Use the sanitized briefing to recommend code modifications or architectural remediation without exposing proprietary IP.
"""
        return [
            {
                "role": "user",
                "content": guidance,
            }
        ]
