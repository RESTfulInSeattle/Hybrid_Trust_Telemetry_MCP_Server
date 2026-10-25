# Architecture Pattern: Sub-Agent Delegation Model

## Overview
In this architecture, the frontier cloud model acts as an overarching project manager but remains physically and network-isolated from the sensitive MCP server. Instead of direct access, it delegates sensitive tasks to a specialized, locally-hosted sub-agent.

## Mechanism
1. **Primary Orchestration:** The user interacts with a frontier model (e.g., Claude 3.5) for general project planning and code generation.
2. **Delegation Prompting:** When the frontier model identifies a need to analyze proprietary logic or internal telemetry, it is restricted from calling the internal MCP server. Instead, it is given a tool to prompt a *local sub-agent*.
3. **Local Execution:** The local agent (powered by the M5 Pro `llama.cpp` endpoint) receives the prompt, authenticates with the restricted MCP server, and processes the raw trade secrets.
4. **Sanitized Return:** The local agent synthesizes the findings, strips out raw proprietary code, and returns a sanitized summary back to the frontier model to continue the overarching task.

## Benefits
* **Air-Gapped IP:** The frontier model never ingests actual proprietary data into its context window, virtually eliminating the risk of cloud exfiltration or third-party training ingestion.
* **Specialization:** The local agent can be heavily prompted (or fine-tuned) specifically for parsing the company's unique telemetry formats, while the frontier model handles broad architectural reasoning.

---

## Related Use Cases & Patterns
* 🏢 [**Hybrid-Trust Architecture & Use Cases**](./hybrid_trust_use_cases.md) — Comprehensive guide on enterprise hybrid-trust workflows.
* ⚙️ [**Strict IDE Profile Binding**](./strict_ide_profile_binding.md) — Isolating profiles within Continue.dev or VS Code.
* 📖 [**Architecture Directory Index**](./README.md)
