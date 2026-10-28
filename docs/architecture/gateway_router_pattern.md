# Architecture Pattern: The AI Gateway Router (Tool-Triggered Dynamic Model Swapping)

[![Model Context Protocol](https://img.shields.io/badge/Protocol-MCP%202.x-blue.svg)](https://modelcontextprotocol.io/)
[![Pattern Category](https://img.shields.io/badge/Pattern-Network%20Proxy%20Governance-purple.svg)](#)
[![Gateway](https://img.shields.io/badge/AI%20Gateway-LiteLLM%20%7C%20Envoy%20Proxy-blue.svg)](#)

## 1. Executive Summary & Problem Statement

In enterprise organizations with hundreds of software engineers, relying on developers to manually switch IDE profiles (the [Strict IDE Profile Binding](./strict_ide_profile_binding.md) pattern) introduces operational risk:
- **Human Error:** Engineers under incident stress may forget to toggle profiles, inadvertently asking cloud models to inspect raw internal telemetry.
- **Client Fragmentation:** Different teams use different editors (VS Code, Cursor, JetBrains, Continue.dev, Claude Desktop), making client-level enforcement difficult to audit centrally.
- **Lack of Unified Audit Trails:** Security and compliance teams cannot verify whether sensitive stack traces were transmitted to external cloud APIs without centralized network inspection.

**The Solution:** The **AI Gateway Router Pattern**. 
This pattern places an intelligent AI Gateway (such as **LiteLLM**, **Cloudflare AI Gateway**, or an enterprise Envoy/Kong proxy) between developer IDEs and inference providers. The gateway inspects outgoing JSON-RPC tool requests in real time. When a prompt triggers a sensitive telemetry tool, the gateway **dynamically hot-swaps the underlying model**, routing the conversation to an on-premise local inference engine without requiring any developer intervention.

---

## 2. Architectural Blueprint & Sequence Flow

```mermaid
sequenceDiagram
    autonumber
    actor Dev as Developer / SRE
    participant IDE as Developer IDE (Continue / Cursor)
    participant Gateway as AI Gateway Router (LiteLLM)
    participant Frontier as Frontier Cloud Model (Claude 3.5 Sonnet)
    participant LocalLLM as Local Cluster (Qwen 2.5 32B via vLLM)
    participant MCP as Telemetry MCP Server

    Dev->>IDE: "Why did the order-matching service crash during market close?"
    IDE->>Gateway: POST /v1/chat/completions (Initial planning prompt)
    Note over Gateway: Initial request contains no sensitive tools.<br/>Route to Frontier Model for reasoning.
    Gateway->>Frontier: Forward planning prompt
    Frontier-->>Gateway: Tool Call: read_recent_errors(service_name="matching-engine")
    
    rect rgb(255, 248, 240)
        Note over Gateway: 🚨 TOOL-TRIGGER DETECTED: 'read_recent_errors'<br/>Rule matched: Sensitive Telemetry Tool -> SWAP MODEL
        Gateway->>IDE: Execute tool call on Telemetry MCP Server
        IDE->>MCP: read_recent_errors("matching-engine")
        MCP-->>IDE: Raw internal telemetry & proprietary ring buffer traces
        IDE->>Gateway: POST /v1/chat/completions (Tool Result + Context)
        Note over Gateway: Gateway redirects context to LOCAL on-premise cluster
        Gateway->>LocalLLM: Forward tool results to Local Model (Zero Cloud Egress)
        LocalLLM-->>Gateway: Sanitized root-cause synthesis (< 400 tokens)
    end

    rect rgb(240, 248, 255)
        Note over Gateway: Sanitize context window before returning to Cloud
        Gateway->>Frontier: Forward sanitized diagnosis (Raw logs pruned from context)
    end

    Frontier-->>Gateway: Final C++20 patch & architectural fix
    Gateway-->>IDE: Stream response to developer
    IDE-->>Dev: Display resolution
```

---

## 3. Reference Implementation: LiteLLM Gateway Configuration

The following production configuration (`litellm_config.yaml`) illustrates how to implement tool-based routing and automated model swapping:

```yaml
model_list:
  # 1. Frontier Tier (Cloud Egress - High-level reasoning)
  - model_name: general-reasoning
    litellm_params:
      model: anthropic/claude-3-5-sonnet-20241022
      api_key: os.environ/ANTHROPIC_API_KEY
      rpm: 100

  # 2. Local Trust Tier (Zero Egress - Sensitive Telemetry & Trade Secrets)
  - model_name: local-telemetry-secure
    litellm_params:
      model: openai/qwen2.5-coder-32b
      api_base: http://vllm-cluster.internal.lan:8000/v1
      api_key: "none"
      tpm: 500000

router_settings:
  routing_strategy: "tool-name-inspection"
  rules:
    # Route sensitive diagnostic tools strictly to the local on-premise cluster
    - match_tool_names:
        - "read_recent_errors"
        - "search_logs_by_pattern"
        - "filter_logs"
        - "delegate_telemetry_investigation"
      route_to: "local-telemetry-secure"
      strip_raw_tool_results_before_cloud_handoff: true

    # Default all benign coding and planning tasks to the frontier model
    - default: "general-reasoning"

general_settings:
  master_key: os.environ/LITELLM_MASTER_KEY
  alerting: ["slack"]
  alerting_threshold: 500 # Alert on unexpected routing anomalies
```

---

## 4. Context Lifecycle & State Pruning

A major technical hurdle in tool-triggered model swapping is **context hygiene**:
If the local model processes 2,000 lines of raw proprietary logs to produce a diagnosis, that raw log output must **not** remain in the conversation history when control returns to the cloud model on the next turn.

The Gateway Router solves this via **State Pruning**:

```mermaid
flowchart LR
    Turn1["Turn 1:<br/>Dev Prompt + Cloud Plan"] --> ToolCall["Turn 2:<br/>Tool Execution (Raw Logs)"]
    ToolCall --> LocalSynth["Turn 3:<br/>Local Model Synthesizes Brief"]
    
    subgraph Pruning["🛡️ Gateway State Pruning Chokepoint"]
        LocalSynth --> Purge["Replace 2,000 raw log lines with<br/>[LOCAL_MODEL_SYNTHESIZED_BRIEF]"]
    end
    
    Purge --> CloudTurn["Turn 4:<br/>Frontier Model receives clean context"]
```

1. **Before Cloud Resumption:** The Gateway replaces the multi-megabyte raw tool output in the message history with the local model's concise summary.
2. **Context Window Protection:** Prevents context window blowout and eliminates "Lost in the Middle" degradation.
3. **Guaranteed Zero-Egress:** Even if the conversation continues for 20 more turns with Claude 3.5, the raw proprietary logs are never transmitted upstream.

---

## 5. Enterprise Deployment Topologies

Organizations can deploy the Gateway Router in two primary architectures depending on infrastructure maturity:

### Topology A: Workstation-Local Proxy (Individual Developers)
- **Deployment:** A single Docker container running LiteLLM or an Envoy sidecar on `localhost:4000`.
- **Target:** Independent developers or small teams using an Apple Silicon Mac Studio running Ollama alongside cloud APIs.
- **Benefits:** Quick setup, zero cloud infrastructure cost.

### Topology B: Centralized Enterprise Kubernetes Cluster
- **Deployment:** A redundant LiteLLM ingress fleet deployed in a private Kubernetes cluster (EKS/GKE/on-premise).
- **Backend:** Routes local inference requests to a high-throughput **vLLM** or **Triton Inference Server** cluster equipped with private NVIDIA A100/H100 or L40S GPUs.
- **Benefits:** Unified enterprise audit logging, hardware cost amortization across 1,000+ developers, centralized DLP rule management.

---

## 6. Pattern Comparison & Selection Guide

| Architectural Dimension | [Dynamic DLP](./dynamic_dlp_pattern.md) | [Sub-Agent Delegation](./sub_agent_delegation_pattern.md) | [Strict IDE Binding](./strict_ide_profile_binding.md) | **Gateway Router Pattern** |
| :--- | :--- | :--- | :--- | :--- |
| **Trust Boundary** | MCP Server Payload | Agent Prompt Layer | IDE User Interface | **Network Proxy Layer** |
| **Enforcement Point** | Server-side (`dlp.py`) | Orchestrating Agent | Client Config (`config.json`) | Centralized Proxy (`litellm` / `gateway_proxy.py`) |
| **Developer Friction** | **Zero** | Low | Low-Medium (Profile Switch) | **Zero** (Completely Transparent) |
| **Implementation Effort** | Low-Medium | Medium | Minimal (Config only) | Medium-High (Proxy & Routing Middleware) |
| **Best Suited For** | Scrubbing PII, tokens, IPs | Proprietary algorithms & quants | Air-gapped / ITAR defense | **Enterprise-wide developer fleets** |

---

## 7. Concrete Implementation & Verification in this Repository

The Gateway Router pattern is fully implemented and tested within this repository:

1. **LiteLLM Production Configuration ([`config/litellm_config.yaml`](../../config/litellm_config.yaml)):**
   - Configures `frontier-reasoning` (Claude 3.5 Sonnet / GPT-4o) and `local-secure` (Qwen 2.5 32B via Ollama / vLLM on `http://localhost:11434/v1`).
   - Declares tool-name matching rules for all sensitive telemetry tools (`read_recent_errors`, `get_system_health`, `search_logs_by_pattern`, `filter_logs`, `delegate_telemetry_investigation`, `get_security_posture`, `sanitize_telemetry_payload`).
   - Enforces `strip_raw_tool_results_before_cloud_handoff: true` and `fail_closed: true`.

2. **Standalone Gateway Proxy Prototype ([`scripts/gateway_proxy.py`](../../scripts/gateway_proxy.py)):**
   - Starlette ASGI application implementing OpenAI `/v1/chat/completions`, `/health`, `/metrics`, and `/audit` endpoints.
   - Evaluates incoming request JSON for tool schemas, assistant tool calls, and tool responses.
   - **Fail-Closed Enforcement:** If the local secure endpoint is unreachable or offline, restricted tool calls abort with HTTP 503 (`fail_closed_security_violation`), strictly preventing any fallback to cloud providers.
   - **State Pruning:** Implements context hygiene by abstracting raw error traces before control is handed back to cloud models.
   - **Centralized Metrics:** Records request counts, tool diversions, token savings, and structured audit logs.

3. **Automated Test Suite ([`tests/test_gateway_router.py`](../../tests/test_gateway_router.py)):**
   - 11 comprehensive tests validating:
     - YAML configuration loading and parsing.
     - Benign prompt routing to `frontier-reasoning`.
     - Tool schema, tool call, and tool result routing to `local-secure`.
     - Embedded telemetry trace signature interception.
     - Fail-closed security guarantee under simulated upstream failure.
     - Context state pruning and raw trace abstraction.
     - Metrics tracking and audit log recording.

```bash
# Launch the Gateway Router proxy
python scripts/gateway_proxy.py --port 4000 --config config/litellm_config.yaml

# Execute test suite
uv run pytest -v tests/test_gateway_router.py
```

---

## 8. Related Documentation & Next Steps

- 🏢 [**Hybrid-Trust Architecture & Enterprise Use Cases**](./hybrid_trust_use_cases.md) — Comprehensive guide on quantitative trading, HIPAA, and air-gapped defense.
- 🛡️ [**Dynamic DLP Pattern**](./dynamic_dlp_pattern.md) — In-server payload sanitization and credential scrubbing.
- 🤝 [**Sub-Agent Delegation Pattern**](./sub_agent_delegation_pattern.md) — Two-tier agent orchestration with local sub-agents.
- ⚙️ [**Strict IDE Profile Binding**](./strict_ide_profile_binding.md) — UI air-gapping within Continue.dev.
- 🎬 [**Showcase Runbook & Live Demo**](../runbooks/showcase_runbook.md) — 5-minute interactive demonstration script.
