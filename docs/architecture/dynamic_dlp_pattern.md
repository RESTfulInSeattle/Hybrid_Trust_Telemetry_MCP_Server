# Architecture Pattern: Dynamic Data Loss Prevention (DLP) at the MCP Layer

## Overview
This pattern embeds context-aware redaction directly into the Telemetry MCP server. It extends the "Governed Pattern" by evaluating the identity or network origin of the requesting client and altering the payload accordingly.

## Mechanism
1. **Client Identification:** When a client application connects to the MCP server via stdio or SSE, the server evaluates the client's execution context (e.g., network origin, authenticated user profile, or API key).
2. **Dynamic Filtering:**
   - **External/Cloud Origin:** If the request originates from a cloud-based agent harness, the MCP server passes the outgoing JSON-RPC payload through a local regex or lightweight NLP filter. This redacts PII, internal IP addresses, API keys, and proprietary logic blocks.
   - **Internal/Local Origin:** If the request originates from a trusted local UI (e.g., a VS Code extension running on the secure home network `192.168.1.x`), the server bypasses the filter.
3. **Payload Delivery:** The LLM receives the modified payload. The AI model only "sees" what the MCP server explicitly allows based on the trust level of the connection.

## Benefits
* **Server-Side Enforcement:** Security is enforced at the data source (the MCP server) rather than relying on the client IDE to behave securely.
* **Seamless Experience:** The frontier model still receives enough context to diagnose issues (e.g., seeing `Error in [REDACTED_ALGO_NAME]`) without exposing the actual proprietary implementation.

---

## Related Use Cases & Patterns
* 🏢 [**Hybrid-Trust Architecture & Use Cases**](./hybrid_trust_use_cases.md) — Comprehensive guide on enterprise hybrid-trust workflows.
* 🔀 [**Gateway Router Pattern**](./gateway_router_pattern.md) — Tool-triggered model routing at the gateway level.
* 📖 [**Architecture Directory Index**](./README.md)
