# Telemetry MCP Server Documentation Hub

Welcome to the documentation repository for the **Telemetry MCP Server**. This directory contains detailed architectural specifications, operational runbooks, hands-on tutorials, and project roadmaps.

---

## 🧭 Documentation Map

Our documentation follows structured documentation principles (inspired by the [Diátaxis framework](https://diataxis.fr/)), separating tutorials, how-to guides, reference material, and strategic roadmaps.

| Category | Document | Audience & Purpose |
| :--- | :--- | :--- |
| **Architecture & Reference** | [**`architecture.md`**](./architecture.md) | **Systems Engineers & Architects:** MCP 2.x protocol specification, stdio transport, JSON-RPC 2.0 message flows, security isolation, and data flow diagrams. |
| **Hybrid-Trust Architecture** | [**`architecture/hybrid_trust_use_cases.md`**](./architecture/hybrid_trust_use_cases.md) | **Enterprise Architects & Security Teams:** Protecting trade secrets and sensitive telemetry using local models alongside cloud frontier models. |
| **Architectural Patterns** | [**`architecture/README.md`**](./architecture/README.md) | **Designers & Implementers:** Modular patterns (Dynamic DLP, Sub-Agent Delegation, Strict IDE Profiles, Gateway Router). |
| **Roadmap & Strategy** | [**`roadmap.md`**](./roadmap.md) | **Engineers & Hiring Leads:** 10-phase skill development curriculum and feature progression from MVP to Enterprise Hybrid-Trust Architectures. |
| **Operational Runbooks** | [**`runbooks/showcase_runbook.md`**](./runbooks/showcase_runbook.md) | **Presenters & Interview Candidates:** 5-minute live demo script, step-by-step walkthrough, and technical interview talking points. |
| **Tutorials & Guides** | [**`tutorials/building_your_first_mcp_server.md`**](./tutorials/building_your_first_mcp_server.md) | **Developers & Learners:** Step-by-step guide to building a telemetry MCP server from scratch using Python and `uv`. |
| **Agent Contract** | [**`AGENTS.md`**](../AGENTS.md) | **AI Coding Agents & Collaborators:** Machine-readable engineering contract, least-privilege boundaries, and quality gates. |

---

## 📂 Directory Layout

```text
docs/
├── README.md                              # This documentation hub & index
├── architecture.md                        # MCP 2.x architecture, protocol mechanics & security
├── architecture/                          # Hybrid-Trust architecture patterns & use cases
│   ├── README.md                          # Architecture directory navigation
│   ├── hybrid_trust_use_cases.md          # Enterprise use cases for trade-secret protection
│   ├── dynamic_dlp_pattern.md             # In-server payload redaction based on origin
│   ├── gateway_router_pattern.md          # Tool-triggered model routing at the gateway
│   ├── strict_ide_profile_binding.md      # Client/IDE profile air-gapping
│   └── sub_agent_delegation_pattern.md    # Two-tier local sub-agent delegation
├── roadmap.md                             # Phased skill development & feature progression
├── runbooks/                              # Operational runbooks and presentation guides
│   └── showcase_runbook.md                # 5-minute live demo script & interview Q&A
└── tutorials/                             # Step-by-step tutorials and hands-on walkthroughs
    └── building_your_first_mcp_server.md  # Foundation walkthrough using uv and MCP SDK 2.x
```

---

## 📖 Recommended Reading Paths

### 1. 💼 Technical Interviewer / Portfolio Reviewer
1. Start at the root [**`README.md`**](../README.md) for the project overview and core value proposition.
2. Review [**`runbooks/showcase_runbook.md`**](./runbooks/showcase_runbook.md) for the 30-second elevator pitch and demo flow.
3. Inspect [**`architecture.md`**](./architecture.md) for sequence diagrams and security boundary design.
4. Read [**`AGENTS.md`**](../AGENTS.md) to evaluate our AI-first engineering methodology.

### 2. 🛠️ Developer / Contributor
1. Follow [**`tutorials/building_your_first_mcp_server.md`**](./tutorials/building_your_first_mcp_server.md) to understand how the baseline server is constructed.
2. Review [**`architecture.md`**](./architecture.md) for tool schema generation and JSON-RPC lifecycle.
3. Check [**`roadmap.md`**](./roadmap.md) to pick up the next milestone task.
4. Adhere to [**`AGENTS.md`**](../AGENTS.md) for tool implementation protocols and verification gates.

---

## ✍️ Documentation Guidelines

When contributing new documentation to this directory:
- **Place in the appropriate subfolder:**
  - `runbooks/` for operational procedures, demo guides, and triage checklists.
  - `tutorials/` for beginner-friendly, step-by-step learning materials.
  - Root of `docs/` for cross-cutting specifications (e.g., architecture, roadmap).
- **Keep docstrings and docs synchronized:** Ensure tool signatures and parameters in documentation match code implementations in `src/telemetry_mcp_server/`.
- **Maintain relative links:** Always test relative markdown links (`../`, `./`) so navigation works seamlessly both locally in IDEs and on GitHub.
- **Update this index:** When adding a new document, add an entry to the Documentation Map table above and root [**`README.md`**](../README.md).
