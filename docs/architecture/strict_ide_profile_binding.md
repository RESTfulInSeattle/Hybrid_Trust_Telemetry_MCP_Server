# Architecture Pattern: Strict IDE Profile Binding

## Overview
This pattern enforces security at the user-interface and configuration level by using strict operational profiles within the IDE's agent extension (such as Continue.dev or the native VS Code BYOK settings). 

## Mechanism
1. **Profile Segregation:** The developer configures distinct, isolated profiles within their IDE settings.
2. **The "Cloud / Boilerplate" Profile:** 
   - Bound to Anthropic, OpenAI, or LiteLLM.
   - Attachments: Only public or generalized MCP servers (e.g., GitHub search, public docs).
   - *Crucially: The internal Trade Secret MCP server is entirely absent from this configuration.*
3. **The "Secure Internal" Profile:** 
   - Bound exclusively to the local inference engine (e.g., `http://192.168.1.136:11434`).
   - Attachments: The proprietary Telemetry and Trade Secret MCP servers are loaded only into this profile.

## Benefits
* **UI-Level Air-Gapping:** Guarantees that the MCP server serving trade secrets is never accidentally exposed to a session communicating with an external API.
* **Simplicity:** Requires zero custom middleware or complex gateway code; relies entirely on standard IDE configuration files (like `config.json` or `settings.json`).
* **Developer Intent:** Forces the developer to make a conscious, intentional switch to the "Secure" profile when working on sensitive components, reinforcing good security hygiene.

---

## Related Use Cases & Patterns
* 🏢 [**Hybrid-Trust Architecture & Use Cases**](./hybrid_trust_use_cases.md) — Comprehensive guide on enterprise hybrid-trust workflows.
* 🤝 [**Sub-Agent Delegation Pattern**](./sub_agent_delegation_pattern.md) — Two-tier agent hierarchy for local sanitization.
* 📖 [**Architecture Directory Index**](./README.md)
