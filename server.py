import os
import json
from mcp.server.fastmcp import FastMCP

# Initialize the FastMCP server
# This name will appear in Claude/Continue when the tool is loaded
mcp = FastMCP("TelemetryInspector")

# Mock log directory for this example
LOG_DIR = "./logs"

@mcp.tool()
def get_system_health() -> str:
    """
    Returns the current health status of the foundational services.
    Use this tool to check if the platform is currently experiencing downtime.
    """
    # In a real app, this might ping a Datadog API or check Azure Monitor
    return json.dumps({
        "status": "healthy",
        "active_alerts": 0,
        "database_latency_ms": 12.4,
        "active_connections": 1042
    })

@mcp.tool()
def read_recent_errors(service_name: str, lines: int = 50) -> str:
    """
    Retrieves the most recent error logs for a specific service.
    
    Args:
        service_name: The name of the service (e.g., 'auth', 'payment', 'database')
        lines: The number of lines to tail from the log file (default 50)
    """
    log_path = os.path.join(LOG_DIR, f"{service_name}.log")
    
    if not os.path.exists(log_path):
        return f"Error: No logs found for service '{service_name}'."
    
    try:
        with open(log_path, 'r') as f:
            # Simple tail implementation
            all_lines = f.readlines()
            recent_lines = all_lines[-lines:]
            return "".join(recent_lines)
    except Exception as e:
        return f"Failed to read logs: {str(e)}"

if __name__ == "__main__":
    # Ensure our mock log directory exists
    os.makedirs(LOG_DIR, exist_ok=True)
    
    # Create a dummy log file to test with
    with open(os.path.join(LOG_DIR, "auth.log"), "w") as f:
        f.write("[INFO] Auth service started\n")
        f.write("[WARN] High latency detected on login endpoint\n")
        f.write("[ERROR] Connection timeout to Redis cache\n")
    
    # Start the MCP server using standard input/output (stdio)
    # This is how the AI client communicates with the server
    mcp.run()