# Architecture & Hybrid-Trust Design Patterns

This directory contains architectural specifications and design patterns for running the **Telemetry MCP Server** within enterprise and **hybrid-trust** environments.

---

## 📚 Architectural Documents & Patterns

| Document | Category | Focus Area |
| :--- | :--- | :--- |
| [**`hybrid_trust_use_cases.md`**](./hybrid_trust_use_cases.md) | **Master Use Case Guide** | End-to-end enterprise use cases (HFT trading algorithms, HIPAA/PCI compliance, air-gapped defense, cost optimization), threat modeling, and reference configurations. |
| [**`dynamic_dlp_pattern.md`**](./dynamic_dlp_pattern.md) | **MCP Server Pattern** | Context-aware payload filtering and PII/secret scrubbing directly inside the MCP server pipeline based on client identity and network origin. |
| [**`sub_agent_delegation_pattern.md`**](./sub_agent_delegation_pattern.md) | **Agent Orchestration Pattern** | Two-tier agent hierarchy where a cloud manager delegates raw telemetry inspection to a local on-premise sub-agent and receives sanitized summaries. |
| [**`strict_ide_profile_binding.md`**](./strict_ide_profile_binding.md) | **Client / IDE Pattern** | UI-level configuration air-gapping in Continue.dev or VS Code, binding sensitive MCP servers strictly to local inference profiles. |
| [**`gateway_router_pattern.md`**](./gateway_router_pattern.md) | **Network Proxy Pattern** | AI Gateway (e.g., LiteLLM) that inspects outgoing JSON-RPC tool calls and dynamically swaps models (local vs. cloud) based on tool sensitivity. |

---

## 🧭 System Context

- For the baseline MCP 2.x protocol implementation, stdio transport, and security boundary design, see [**`../architecture.md`**](../architecture.md).
- For the phased implementation plan and skill progression for each pattern, see [**`../roadmap.md`**](../roadmap.md).
- For the high-level documentation map and recommended reading paths, see [**`../README.md`**](../README.md).
