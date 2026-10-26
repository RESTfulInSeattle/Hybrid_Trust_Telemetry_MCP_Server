# Architecture Pattern: The Gateway Router (Tool-Triggered Model Swapping)

## Overview
This pattern introduces an AI Gateway (such as LiteLLM) as a proxy between the client application and the LLM providers. It acts as an intelligent router that inspects outgoing JSON-RPC tool calls and routes the context window to different models based on the sensitivity of the requested tool.

## Mechanism
1. **Interception:** The AI Gateway intercepts all JSON-RPC payload requests originating from the IDE or agent harness.
2. **Evaluation:** The gateway inspects the `name` of the requested MCP tool.
3. **Routing:**
   - **Restricted Tools:** If the tool matches a restricted list (e.g., `read_core_algo()`, `get_unredacted_telemetry()`), the gateway halts external transmission and routes the prompt and context window strictly to the local inference engine (e.g., Qwen 30B via `llama.cpp`).
   - **Benign Tools:** If the tool is standard or public (e.g., `search_public_docs()`), the gateway routes the request to a frontier model (e.g., Claude 3.5 Sonnet or GPT-4).

## Benefits
* **Automated Siloing:** Developers do not need to manually toggle between local and cloud models; the infrastructure enforces data boundaries automatically.
* **Cost Efficiency:** Utilizes expensive frontier models only for general reasoning, while relying on zero-cost local models for processing proprietary data.
* **Auditability:** The gateway provides a centralized choke point to log and audit all tool invocation attempts.

---

## Related Use Cases & Patterns
* 🏢 [**Hybrid-Trust Architecture & Use Cases**](./hybrid_trust_use_cases.md) — Comprehensive guide on enterprise hybrid-trust workflows.
* 🛡️ [**Dynamic DLP Pattern**](./dynamic_dlp_pattern.md) — Redaction embedded at the MCP server level.
* 📖 [**Architecture Directory Index**](./README.md)
