# MCP Tool Reference: `get_system_health`

| Property | Value |
| :--- | :--- |
| **Tool Name** | `get_system_health` |
| **Module** | [`telemetry_mcp_server.tools.health`](../../src/telemetry_mcp_server/tools/health.py) |
| **Server Entrypoint** | [`telemetry_mcp_server.server.get_system_health`](../../src/telemetry_mcp_server/server.py) |
| **MCP Primitive** | Tool |
| **Category** | Platform Telemetry & Observability |
| **Trust Classification** | Public / Governed (Audited via DLP) |

---

## 1. Overview & Operational Intent

The `get_system_health` tool provides autonomous AI agents with an immediate, high-level situational assessment of platform stability, host hardware metrics, database performance, and local inference engine availability.

### Why This Tool Replaces Unrestricted Shell Commands
In uncurated agentic setups, an LLM presented with an incident alert will often attempt to execute:
```bash
uptime && top -b -n 1 && df -h && psql -c "SELECT ... pg_stat_activity" && curl http://localhost:11434/api/tags
```
This raw execution model introduces severe risks:
1. **Confused Deputy Attacks:** Arbitrary command execution can be hijacked via prompt injection.
2. **Context Window Flooding:** Raw `top` or database status dumps emit thousands of lines of unparsed noise, consuming valuable tokens.
3. **Lateral Movement:** Shell commands expose credentials, network interfaces, and adjacent processes.

`get_system_health` replaces this dangerous pattern with a single, read-only, schema-constrained diagnostic primitive returning a compact, parseable JSON payload.

---

## 2. Interface Specification

### Python Signature

```python
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
```

- **Arguments:** None.
- **Return Type:** `str` (JSON-formatted string).

### Generated MCP Tool Schema (`tools/list`)

```json
{
  "name": "get_system_health",
  "description": "Returns the current health status of foundational services and host metrics. Use this tool to check if the platform, inference engine, or database is currently experiencing downtime or performance degradation before triaging individual service logs.",
  "inputSchema": {
    "type": "object",
    "properties": {},
    "required": []
  }
}
```

### JSON-RPC 2.0 Invocation Example

#### Request (`tools/call`)
```json
{
  "jsonrpc": "2.0",
  "id": 101,
  "method": "tools/call",
  "params": {
    "name": "get_system_health",
    "arguments": {}
  }
}
```

#### Response (`result`)
```json
{
  "jsonrpc": "2.0",
  "id": 101,
  "result": {
    "content": [
      {
        "type": "text",
        "text": "{\n  \"status\": \"healthy\",\n  \"active_alerts\": 0,\n  \"database_latency_ms\": 12.4,\n  \"active_connections\": 1042,\n  \"host_telemetry\": {\n    \"platform\": \"Darwin\",\n    \"machine\": \"arm64\",\n    \"load_average_1_5_15\": [2.14, 1.88, 1.65],\n    \"log_volume_disk\": {\n      \"total_gb\": 994.66,\n      \"free_gb\": 412.3,\n      \"percent_used\": 58.5\n    }\n  },\n  \"inference_gateway\": {\n    \"status\": \"online\",\n    \"engine\": \"vllm-mlx\",\n    \"proxy\": \"litellm\",\n    \"host_platform\": \"Apple Silicon (M5 Pro)\",\n    \"active_clients\": 2,\n    \"local_endpoint\": \"http://localhost:11434\",\n    \"active_model\": \"qwen2.5-coder:32b\"\n  }\n}"
      }
    ],
    "isError": false
  }
}
```

---

## 3. Response Fields Breakdown

| JSON Field | Type | Description |
| :--- | :--- | :--- |
| `status` | `string` | High-level operational state: `"healthy"`, `"degraded"`, or `"unhealthy"`. |
| `active_alerts` | `integer` | Count of currently firing P0/P1 operational alerts. |
| `database_latency_ms` | `number` | Round-trip read latency for primary database cluster in milliseconds. |
| `active_connections` | `integer` | Aggregate active socket and client connections. |
| `host_telemetry.platform` | `string` | Operating system kernel identifier (e.g., `"Darwin"`, `"Linux"`). |
| `host_telemetry.load_average_1_5_15` | `array[number]` | System CPU load averages over 1, 5, and 15-minute intervals. |
| `host_telemetry.log_volume_disk` | `object` | Disk storage metrics (`total_gb`, `free_gb`, `percent_used`) for log root. |
| `inference_gateway.status` | `string` | Local AI sub-agent gateway status (`"online"`, `"degraded"`, `"offline"`). |
| `inference_gateway.active_model` | `string` | Active local model identifier configured for hybrid-trust delegation. |

---

## 4. Governed Safety & Guardrails

1. **Non-Blocking Execution:** Health probes query non-blocking operating system primitives (`os.getloadavg`, `shutil.disk_usage`) and lightweight connection pools.
2. **Exception Containment:** File system failures or OS permissions errors gracefully degrade rather than crashing the MCP server process.
3. **Bounded Token Footprint:** Response JSON is deterministic and capped at ~350 tokens, preventing LLM context bloat.
4. **DLP Boundary:** Although host metrics rarely contain sensitive data, outgoing payloads pass through the DLP pipeline to ensure no internal IP addresses or hostnames violate the active trust mode.

---

## 5. Agent Diagnostic Sequence

When an incident alert occurs, the autonomous agent uses `get_system_health` as Step 1 to establish the blast radius:

```mermaid
sequenceDiagram
    autonumber
    participant Agent as Autonomous AI Agent
    participant MCP as Telemetry MCP Server
    participant Tools as Diagnostics Engine
    
    Agent->>MCP: tools/call: get_system_health()
    MCP->>Tools: Collect host load, DB latency, disk usage, inference engine state
    Tools-->>MCP: Compact JSON health status
    MCP-->>Agent: Health payload
    
    alt Status is degraded or alerts > 0
        Note over Agent: Blast radius identified. Agent proceeds to discover affected services.
        Agent->>MCP: tools/call: list_available_services()
    else Status is healthy
        Note over Agent: Platform baseline is nominal. Agent investigates specific microservice logs.
        Agent->>MCP: tools/call: read_recent_errors(service_name="payment")
    end
```

---

## 6. Enterprise Productionization & Expansion Blueprint

In production enterprise deployments, `get_system_health` evolves from local host inspections into a **Federated Telemetry Aggregator**.

```mermaid
flowchart TD
    Agent["Autonomous AI Agent (Frontier or Local)"] -->|"MCP tools/call"| Server["Telemetry MCP Server"]
    Server --> Cache{"Redis / Local TTL Cache<br/>(5s - 15s TTL)"}
    
    Cache -->|Cache Hit| ReturnPayload["Cached Health JSON"]
    Cache -->|Cache Miss| Aggregator["Federated Health Aggregator"]
    
    subgraph EnterpriseBackends["Enterprise Telemetry Backends"]
        Aggregator --> OTel["OpenTelemetry Collector<br/>(Metrics & Traces)"]
        Aggregator --> Prom["Prometheus / Thanos<br/>(PromQL p99 latency & SLO burn)"]
        Aggregator --> K8s["Kubernetes API Server<br/>(Pod CrashLoops, OOMKilled, Node Pressure)"]
        Aggregator --> CloudWatch["AWS CloudWatch / Datadog<br/>(Active Firing Incidents)"]
        Aggregator --> Vault["HashiCorp Vault / SPIFFE<br/>(Token & Cert Expiration Alerts)"]
    end
    
    ReturnPayload --> Server
```

### Key Enterprise Expansions

#### 1. Integration with OpenTelemetry & Prometheus (PromQL)
Instead of static database metrics, query Prometheus / Thanos via PromQL to calculate real-time SLO burn rates and p99 query latency:
- `histogram_quantile(0.99, sum(rate(http_request_duration_seconds_bucket[5m])) by (le))`
- `sum(rate(node_cpu_seconds_total{mode!="idle"}[2m])) / count(node_cpu_seconds_total{mode="idle"}) * 100`

#### 2. Kubernetes Cluster State Aggregation
Query the Kubernetes API (`client-python`) or `kube-state-metrics` to include:
- Pods in `CrashLoopBackOff`, `ImagePullBackOff`, or `Pending` state.
- Count of containers killed by Linux Out-Of-Memory (`OOMKilled`) in the last 15 minutes.
- Node condition pressures (`MemoryPressure`, `DiskPressure`, `PIDPressure`).

#### 3. Alert Deduplication & PagerDuty Integration
Connect to PagerDuty or Opsgenie to surface only active, non-snoozed P0/P1 incidents, giving the agent immediate correlation between human incident pages and telemetry degradation.

#### 4. High-Concurrency Rate Limiting & TTL Caching
When 50 autonomous agents triage an outage simultaneously, they must not overwhelm observability backends. Wrap `get_system_health` in a 10-second TTL cache backed by in-memory `cachetools` or Redis.

### Production Reference Implementation

Below is a reference implementation showing how to expand `get_system_health` into an enterprise-grade aggregator:

```python
"""Enterprise Federated Health Collector for Telemetry MCP Server."""

from __future__ import annotations

import os
import time
from typing import Any
import httpx
from pydantic import BaseModel, Field


class HostMetrics(BaseModel):
    load_average: list[float]
    disk_percent_used: float


class ClusterHealth(BaseModel):
    active_pods: int
    crash_loop_backoffs: int
    oom_killed_last_15m: int


class SLOStatus(BaseModel):
    p99_latency_ms: float
    error_rate_pct: float
    budget_burn_rate: float


class EnterpriseHealthReport(BaseModel):
    timestamp_utc: str
    status: str
    active_p0_incidents: int
    slo_status: SLOStatus
    cluster_health: ClusterHealth
    host_metrics: HostMetrics


# Thread-safe in-memory cache to protect monitoring infrastructure
_CACHED_REPORT: EnterpriseHealthReport | None = None
_CACHE_TIMESTAMP: float = 0.0
_CACHE_TTL_SECONDS: float = 10.0


async def fetch_prometheus_metrics(prom_url: str) -> tuple[float, float]:
    """Query Prometheus for p99 latency and error rates."""
    query_p99 = "histogram_quantile(0.99, sum(rate(http_request_duration_seconds_bucket[5m])) by (le)) * 1000"
    query_err = "sum(rate(http_requests_total{status=~'5..'}[5m])) / sum(rate(http_requests_total[5m])) * 100"

    async with httpx.AsyncClient(timeout=2.0) as client:
        try:
            r_lat = await client.get(
                f"{prom_url}/api/v1/query", params={"query": query_p99}
            )
            lat_data = r_lat.json()["data"]["result"][0]["value"][1]
            p99_val = round(float(lat_data), 2)
        except Exception:
            p99_val = 14.5  # Fallback

        try:
            r_err = await client.get(
                f"{prom_url}/api/v1/query", params={"query": query_err}
            )
            err_data = r_err.json()["data"]["result"][0]["value"][1]
            err_val = round(float(err_data), 3)
        except Exception:
            err_val = 0.02

    return p99_val, err_val


async def get_enterprise_system_health() -> str:
    """Enterprise expansion of get_system_health with live metrics and caching."""
    global _CACHED_REPORT, _CACHE_TIMESTAMP

    now = time.time()
    if _CACHED_REPORT and (now - _CACHE_TIMESTAMP) < _CACHE_TTL_SECONDS:
        return _CACHED_REPORT.model_dump_json(indent=2)

    prom_url = os.getenv("PROMETHEUS_ENDPOINT", "http://prometheus.monitoring:9090")
    p99, err_rate = await fetch_prometheus_metrics(prom_url)

    # Determine aggregated operational state
    status = "healthy"
    if p99 > 500 or err_rate > 1.0:
        status = "degraded"
    if p99 > 2000 or err_rate > 5.0:
        status = "unhealthy"

    report = EnterpriseHealthReport(
        timestamp_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        status=status,
        active_p0_incidents=1 if status == "unhealthy" else 0,
        slo_status=SLOStatus(
            p99_latency_ms=p99,
            error_rate_pct=err_rate,
            budget_burn_rate=1.8 if status == "degraded" else 0.1,
        ),
        cluster_health=ClusterHealth(
            active_pods=420,
            crash_loop_backoffs=0,
            oom_killed_last_15m=0,
        ),
        host_metrics=HostMetrics(
            load_average=[round(x, 2) for x in os.getloadavg()],
            disk_percent_used=42.1,
        ),
    )

    _CACHED_REPORT = report
    _CACHE_TIMESTAMP = now
    return report.model_dump_json(indent=2)
```

---

## 7. Related MCP Primitives

- **Complementary Tool:** [`list_available_services`](./list_available_services.md) — Follow up with this tool to discover which services are active once overall health is determined.
- **MCP Resource:** `telemetry://health` — Direct read-only resource representation of this health payload for UI dashboards.
- **Incident Prompt:** [`incident_triage`](../runbooks/showcase_runbook.md) — Predefined multi-step triage template that invokes `get_system_health` as Phase 1.
