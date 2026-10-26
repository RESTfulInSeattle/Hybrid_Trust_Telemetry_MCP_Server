# Building a Telemetry MCP Server (Python)

The Model Context Protocol (MCP) is an open standard that allows AI models to securely interact with local or remote data sources and tools.

This demonstrates **"governed tool integration."** Instead of giving an AI raw shell access, you are providing a strictly defined, observable API (the MCP server) that the AI can call.

We will build a simple MCP server in Python that allows an LLM to read local telemetry or application logs.

---

## Step 1: Project Initialization

Using `uv` to manage the project and virtual environment:

```bash
# Create and navigate to the project directory
mkdir Telemetry_MCP_Server
cd Telemetry_MCP_Server

# Initialize a new Python project using uv
uv init

# Add the official MCP SDK and CLI tools
uv add "mcp[cli]"
```

> [!NOTE]
> **MCP SDK 2.x Notice:** The official Python MCP SDK (`mcp>=2.0`) uses `MCPServer` from `mcp.server`. In older 1.x releases, this class was called `FastMCP`. The code below uses the modern 2.x syntax.

---

## Step 2: The MCP Server Code

Create your server file at `src/telemetry_mcp_server/server.py`:

```python
import os
import json
from mcp.server import MCPServer

# Initialize the MCP server
# This name will appear in Claude/Continue when the tool is loaded
mcp = MCPServer("TelemetryInspector")

# Mock log directory for this example
LOG_DIR = "./logs"


@mcp.tool()
def get_system_health() -> str:
    """
    Returns the current health status of the foundational services.
    Use this tool to check if the platform is currently experiencing downtime.
    """
    # In a real app, this might ping a Datadog API or check Azure Monitor
    return json.dumps(
        {
            "status": "healthy",
            "active_alerts": 0,
            "database_latency_ms": 12.4,
            "active_connections": 1042,
        }
    )


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
        with open(log_path, "r") as f:
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
```

---

## Step 3: Local Testing

### Option A: The Interactive Web Inspector (`mcp dev`)
The MCP SDK includes a built-in browser inspector so you can test your server without needing an LLM host immediately:

```bash
uv run mcp dev src/telemetry_mcp_server/server.py
```

> [!IMPORTANT]
> **Prerequisite for `mcp dev`:** The web inspector uses `@modelcontextprotocol/inspector` under the hood, which requires Node.js / `npx`. If `npx` is not found, install it on macOS via:
> ```bash
> brew install node
> ```

### Option B: Quick Pure-Python Verification (No Node.js needed)
You can verify the tools execute directly in Python without installing Node.js:
```bash
uv run python -c "from telemetry_mcp_server.server import get_system_health; print(get_system_health())"
```

---

## Step 4: Hooking it up to your IDE (Continue.dev)

Since your goal is to use this in a local LLM setup (like a local Qwen 30B model or Claude), you can attach this MCP server directly to the **Continue** extension in VS Code.

1. Open your Continue configuration file (`~/.continue/config.json`).
2. Add your new MCP server to the `mcpServers` array:

```json
{
  "mcpServers": [
    {
      "name": "TelemetryInspector",
      "command": "uv",
      "args": [
        "run",
        "--directory",
        "/Users/YOUR_MAC_USERNAME/Development/Telemetry_MCP_Server",
        "python",
        "src/telemetry_mcp_server/server.py"
      ]
    }
  ]
}
```

*(Be sure to replace `/Users/YOUR_MAC_USERNAME/...` with your actual absolute path).*

---

## Step 5: The Agentic Workflow

Now, open VS Code, open the Continue chat (powered by your local LLM or Claude), and prompt it:

> *"Are there any recent errors in the auth service?"*

**What happens next:**

1. The LLM sees that it has access to the `TelemetryInspector` MCP server.
2. It decides to call the `read_recent_errors` tool, passing `"auth"` as the `service_name`.
3. Your Python MCP server executes the code securely on your machine, reads the log file, and returns the text.
4. The LLM reads the result and answers you: *"Yes, there is a connection timeout to the Redis cache in the auth service."*

---

## The Interview Talking Point

When you talk to the Microsoft Foundry team or engineering leaders, you can frame this perfectly:

*"To better understand the agent deployment lifecycle, I built a custom MCP server in Python. Instead of giving my local LLMs raw terminal execution privileges, I created governed, observable tool boundaries. For example, I implemented a telemetry inspector that strictly limits the AI to reading specific application logs, ensuring secure integration while allowing the agent to autonomously diagnose system errors."*
