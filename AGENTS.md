# AGENTS.md — Agent Operating Contract & Development Guidelines

Welcome to the **Telemetry MCP Server** repository. This document serves as the governing specification and operating contract for autonomous AI coding agents (and human engineers collaborating with AI) working within this codebase.

---

## 1. Project Identity & Purpose

- **Project Name:** Telemetry MCP Server (`telemetry-mcp-server`)
- **Protocol:** [Model Context Protocol (MCP)](https://modelcontextprotocol.io/)
- **Primary Framework:** Python `MCPServer` (via official `mcp[cli]>=2.0`, previously known as `FastMCP` in v1)
- **Core Purpose:** Provide a secure, governed Model Context Protocol server that allows AI agents and LLM clients (Continue.dev, Claude Desktop, Cursor, local LLMs like Qwen) to inspect system health, read application logs, and diagnose incidents **without granting unrestricted shell or filesystem access**.
- **Target Showcase:** AI Engineering, Agentic Tool Governance, Enterprise Observability, and technical interviews (e.g., Microsoft Foundry, AI Platform teams).

---

## 2. AI-First Engineering Principles

When generating, modifying, or refactoring code in this repository, all AI agents **MUST** uphold these core principles:

### Principle 1: Governed Tool Boundaries (Least Privilege)
Never create tools that expose raw shell execution, arbitrary file writes, or unrestricted directory traversal. The value of this project is demonstrating **fine-grained, governed tool access** over dangerous general-purpose command execution.

### Principle 2: Docstrings are LLM User Interfaces
In MCP, tool docstrings and parameter descriptions are directly ingested by the client LLM to determine *when* and *how* to call tools.
- Docstrings must be unambiguous, concise, and explicit.
- Always document edge cases, default parameters, and valid parameter ranges.
- Describe both what the tool does **and** when it should be used versus alternatives.

### Principle 3: Defensive Path & Input Sanitization
Any tool accepting filenames or service identifiers must strictly sanitize input to prevent directory traversal attacks (e.g., `../../etc/shadow`). Always validate that resolved paths reside inside the designated root log directory.

### Principle 4: Deterministic & Actionable Returns
- Never let unhandled exceptions crash the MCP server process.
- Return structured, parseable messages (or JSON strings) that tell the calling agent precisely what failed and how to remediate it (e.g., `"Error: Service 'billing' not found. Available services: ['auth', 'database', 'payment']"`).

### Principle 5: Context Window Awareness
Logs can be massive. Never return unbounded log streams that risk blowing up the LLM's context window. Always enforce sensible defaults (e.g., `lines: int = 50`, `max_lines: int = 200`) and provide filtering options (e.g., log level, timestamp window, regex).

---

## 3. Technology Stack & Tooling Standards

| Category | Standard / Tool | Version / Rule |
| :--- | :--- | :--- |
| **Language** | Python | `>= 3.12` |
| **Package Management** | `uv` | Always use `uv add`, `uv run`, `uv sync` |
| **MCP Implementation** | `MCPServer` from `mcp[cli]>=2.0` | Official Anthropic/MCP Python SDK v2.x |
| **Data Validation** | Pydantic v2 | Used for structured tool parameters & responses |
| **Code Formatting & Linting** | `ruff` | `uv run ruff check .` & `uv run ruff format .` |
| **Type Checking** | `mypy` | Strict typing on all tool signatures |
| **Testing** | `pytest`, `pytest-asyncio` | Unit tests for all tools & security boundaries |
| **Inspector Tooling** | Node.js / `npx` | Required only for the `mcp dev` web inspector UI |

> [!IMPORTANT]
> **No Legacy Package Managers:** Do not invoke `pip install` or create raw virtual environments with `python -m venv`. Always use `uv`.

---

## 4. Repository Structure & Layout

Agents must adhere to the following directory layout:

```text
Telemetry_MCP_Server/
├── AGENTS.md                          # This agent operating specification & development contract
├── README.md                          # Public showcase, quickstart & documentation index
├── pyproject.toml                     # Project metadata and dependencies (managed by uv)
├── docs/                              # Project documentation & guides
│   ├── README.md                      # Documentation index & navigation map
│   ├── architecture.md                # Deep-dive system design, security & MCP mechanics
│   ├── architecture/                  # Hybrid-Trust architecture patterns & use cases
│   │   ├── README.md                  # Architecture index
│   │   ├── hybrid_trust_use_cases.md  # Trade secret defense & enterprise use cases
│   │   └── ...                        # Dynamic DLP, Sub-Agent, IDE profile, Gateway router
│   ├── roadmap.md                     # Phased skill development & feature progression
│   ├── runbooks/                      # Operational runbooks & interview guides
│   │   └── showcase_runbook.md        # 5-minute live demo script & interview talking points
│   └── tutorials/                     # Step-by-step guides & tutorials
│       └── building_your_first_mcp_server.md # Foundation walkthrough
├── src/
│   └── telemetry_mcp_server/
│       ├── __init__.py                # Package exports
│       ├── server.py                  # MCPServer instance and entrypoint
│       ├── config.py                  # Environment config (log dirs, line limits, auth)
│       ├── security.py                # Path traversal sanitizers and input validators
│       ├── tools/                     # Modular MCP tools
│       │   ├── __init__.py
│       │   ├── health.py              # System health & metrics probes
│       │   └── logs.py                # Log tailing, regex search, level filtering
│       ├── resources/                 # MCP Resources (telemetry:// URIs)
│       │   ├── __init__.py
│       │   └── log_streams.py
│       └── prompts/                   # MCP Prompts (predefined triage templates)
│           ├── __init__.py
│           └── incident_triage.py
├── tests/
│   ├── conftest.py                    # Pytest fixtures and mock log generators
│   ├── test_security.py               # Security & path traversal tests
│   ├── test_health.py                 # Health probe tests
│   └── test_logs.py                   # Log retrieval and filtering tests
└── logs/                              # Mock / test log files (gitignored except sample templates)
    ├── auth.log
    ├── payment.log
    └── database.log
```

---

## 5. Standard Agent Workflows & Runbooks

### Workflow 1: Adding a New MCP Tool

When asked to implement a new tool (e.g., `search_logs_by_pattern`), follow this exact protocol:

1. **Define the Interface First:**
   Specify explicit types for all parameters and return types. Use Python type hints (`str`, `int`, `Optional[str]`, Pydantic models).
2. **Draft the Docstring:**
   Format docstrings following the Google Python style guide with explicit `Args:` and `Returns:` sections. Ensure the explanation makes the tool's intent obvious to an LLM planner.
3. **Apply Defensive Guards:**
   Call `security.validate_safe_path()` or equivalent before performing any I/O.
4. **Implement Graceful Error Handling:**
   Catch expected filesystem/parsing errors and return structured failure responses rather than raising uncaught exceptions.
5. **Write Unit Tests:**
   Add a test case in `tests/` covering:
   - Happy path with mock log data.
   - Missing file / service not found.
   - Adversarial input (e.g., `service_name="../../../etc"`).
6. **Verify with Tests or MCP Inspector:**
   Run tests via `uv run pytest` or launch the inspector via `uv run mcp dev src/telemetry_mcp_server/server.py`.

```python
# Example: Canonical Tool Pattern (MCP 2.x)
from mcp.server import MCPServer
from telemetry_mcp_server.security import safe_resolve_log_path

mcp = MCPServer("TelemetryInspector")


@mcp.tool()
def search_logs_by_pattern(
    service_name: str, pattern: str, max_matches: int = 20
) -> str:
    """Search recent logs for a specific service matching a regex or substring.

    Use this tool when investigating errors or looking for specific trace IDs,
    HTTP status codes, or exception names across service logs.

    Args:
        service_name: Name of target service (e.g., 'auth', 'payment', 'database').
        pattern: Regex or string pattern to match (e.g., '500 Internal', 'NullPointer').
        max_matches: Maximum number of matching lines to return (1-100, default 20).

    Returns:
        Newline-delimited matching log lines or an informational message if no matches.
    """
    # 1. Sanitize input
    path_result = safe_resolve_log_path(service_name)
    if not path_result.is_valid:
        return f"Error: {path_result.error_message}"

    # 2. Execute bounded search
    # ... logic here ...
```

---

### Workflow 2: Implementing MCP Resources

MCP Resources expose data streams that clients can read or subscribe to (via URIs like `telemetry://services/health` or `telemetry://logs/{service}`):

1. Use `@mcp.resource("telemetry://{path}")`.
2. Ensure resource outputs are formatted as clean JSON, Markdown, or plain text.
3. Keep resource reads non-blocking.

---

### Workflow 3: Implementing MCP Prompts

MCP Prompts are server-defined prompt templates that guide an LLM through a multi-step investigation:

1. Use `@mcp.prompt()`.
2. Structure the prompt to orchestrate sequential tool calls (e.g., check health first, inspect failing service logs second, synthesize root cause third).

---

## 6. Testing, Quality & Verification Gates

Before completing any task or opening a PR, the agent must run and verify:

```bash
# 1. Format and lint check
uv run ruff check .
uv run ruff format --check .

# 2. Strict type check
uv run mypy src/

# 3. Test suite execution
uv run pytest -v

# 4. Direct Python smoke test
uv run python -c "from telemetry_mcp_server.server import get_system_health; print(get_system_health())"

# 5. MCP inspector test (requires node/npx)
uv run mcp dev src/telemetry_mcp_server/server.py
```

### Path Traversal Defense Verification Matrix
Every tool that touches logs must pass these negative test inputs:
- `../` (relative traversal)
- `../../etc/passwd` (deep traversal)
- `/etc/passwd` (absolute path escape)
- `auth\0.log` (null byte injection)
- `..%2F..%2F` (URL encoded traversal)

---

## 7. Portfolio & Interview Framing (For Human + AI Collaboration)

When discussing or demonstrating this codebase in portfolio reviews or technical interviews:
- **Core Narrative:** *"Modern AI applications require governed capability boundaries. Unrestricted shell access is a massive security hazard. This project demonstrates how the Model Context Protocol (MCP) provides a typed, observable, and defense-in-depth API boundary for LLMs performing automated SRE and telemetry diagnostics."*
- **Architecture Highlight:** `MCPServer` high-level abstraction layer (MCP 2.x), strict path containment, bounded response sizes for context window management, and native JSON-RPC stdio transport.
- **Protocol Currency:** Fluent with the evolution from v1 FastMCP to v2 MCPServer in the official Python SDK.
- **AI-First Pedigree:** Built using `AGENTS.md` as an executable agent contract, demonstrating fluency with modern agentic workflows, prompt-driven tool design, and automated regression testing.
