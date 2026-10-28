# Architecture Pattern: Dynamic Data Loss Prevention (DLP) at the MCP Protocol Boundary

[![Model Context Protocol](https://img.shields.io/badge/Protocol-MCP%202.x-blue.svg)](https://modelcontextprotocol.io/)
[![Pattern Category](https://img.shields.io/badge/Pattern-MCP%20Server%20Middleware-purple.svg)](#)
[![Compliance](https://img.shields.io/badge/Compliance-PCI--DSS%20%7C%20HIPAA-green.svg)](#)

## 1. Executive Summary & Problem Statement

When AI coding agents and diagnostic copilots inspect production systems, log streams are their primary diagnostic source. However, real-world application logs are fraught with high-liability data:
- **Payment Card Data (PCI-DSS):** Primary Account Numbers (PANs), CVVs, expiration dates.
- **Protected Health Information & PII (HIPAA):** Social Security Numbers, Medical Record Numbers (MRNs), Patient IDs, email addresses, phone numbers.
- **Secrets & Infrastructure Credentials:** OAuth Bearer tokens, JSON Web Tokens (JWTs), AWS access keys, private SSH keys, database connection URIs.
- **Internal Network Topography:** RFC 1918 private IPv4 addresses (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`).
- **Trade Secrets & Proprietary Algorithms:** Secret formula weights, quantitative trading signals, lock-free ring buffer implementations.

**The Failure Mode:** If an MCP server naively pipes raw log files into tool responses, external frontier models (e.g., Claude 3.5 Sonnet, GPT-4o) ingest sensitive data into their context windows. This triggers regulatory non-compliance, risks third-party training data ingestion, and exposes the enterprise to prompt injection attacks where malicious log strings exfiltrate credentials.

**The Solution:** The **Dynamic DLP Pattern** embeds high-throughput, context-aware redaction directly into the MCP server payload pipeline. The MCP server evaluates the client origin, operational mode, and connection transport, applying real-time regex and cryptographic checksum scrubbing before payloads exit the server boundary.

---

## 2. Architectural Sequence Flow

```mermaid
sequenceDiagram
    autonumber
    actor Dev as Developer / Agent Harness
    participant Client as MCP Client (IDE / Gateway)
    participant Server as Telemetry MCP Server (MCPServer 2.x)
    participant Sec as Security & Boundary Guards
    participant Storage as Log Storage (/logs/*.log)
    participant DLP as Dynamic DLP Engine (dlp.py)
    participant LLM as Frontier Cloud Model

    Dev->>Client: "Diagnose checkout failure in payment service"
    Client->>Server: tools/call: read_recent_errors(service_name="payment", lines=20)
    Server->>Sec: safe_resolve_log_path("payment")
    Sec-->>Server: Path OK (/logs/payment.log)
    Server->>Storage: Read bounded log lines
    Storage-->>Server: Raw log lines (contains PANs, JWTs, RFC1918 IPs)
    
    rect rgb(240, 248, 255)
        Note over Server,DLP: Dynamic DLP Middleware Pipeline
        Server->>DLP: sanitize_payload(raw_logs, mode=REDACTED_CLOUD)
        DLP->>DLP: Scan candidate PANs -> Validate via Luhn Checksum
        DLP->>DLP: Scrub Bearer tokens, JWTs, AWS credentials
        DLP->>DLP: Mask RFC 1918 private IPv4 addresses
        DLP->>DLP: Redact proprietary trade secret symbols
        DLP->>DLP: Record audit counters in DLPAuditMetrics
        DLP-->>Server: Sanitized Payload + Redaction Statistics
    end

    Server-->>Client: JSON-RPC 2.0 Response (Redacted Payload)
    Client-->>LLM: Sanitized context for root-cause synthesis
    LLM-->>Dev: "Root Cause: Connection pool exhausted at gateway. Payment failed safely."
```

---

## 3. Core Mechanics & Technical Specification

The implementation in [`src/telemetry_mcp_server/dlp.py`](../../src/telemetry_mcp_server/dlp.py) enforces a multi-tier detection pipeline designed for high throughput and zero false negatives on high-liability data.

### 3.1 Detection & Redaction Rules

| Category | Regex / Validation Algorithm | Raw Log Snippet | Sanitized MCP Output |
| :--- | :--- | :--- | :--- |
| **PCI-DSS (PAN)** | Candidate `(?:\d{4}[-\s]?){3}\d{1,7}` + **Luhn Checksum** | `card=4111-2222-3333-1111` | `card=[CARD_REDACTED_*1111]` |
| **PCI-DSS (CVV)** | `(?i)\b(cvv\|cvc\|cid)\s*[:=]\s*\d{3,4}\b` | `cvv: 842` | `[CVV_REDACTED]` |
| **HIPAA (SSN)** | `\b\d{3}-\d{2}-\d{4}\b` | `ssn: 000-12-3456` | `[SSN_REDACTED]` |
| **HIPAA (Patient ID)** | `(?i)\b(patient[_-]?id\|mrn)\s*[:=]\s*([a-zA-Z0-9_-]+)` | `patient_id: MRN-948201` | `patient_id: [PATIENT_ID_REDACTED]` |
| **Credentials (Bearer)** | `(?i)Bearer\s+[A-Za-z0-9_\-\.]{20,}` | `Bearer eyJhbGciOi...` | `Bearer [TOKEN_SCRUBBED]` |
| **Credentials (JWT)** | `\beyJ[A-Za-z0-9_-]{8,}\.eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b` | `token=eyJhbGciOi...` | `token=[JWT_SCRUBBED]` |
| **Credentials (AWS)** | `\b(?:AKIA\|ABIA\|ACCA\|ASIA)[A-Z0-9]{16}\b` | `key=AKIAIOSFODNN7EXAMPLE` | `key=[AWS_KEY_REDACTED]` |
| **Credentials (DB URL)** | `(?:postgresql\|mysql\|redis)://[^\s:]+:[^\s@]+@[^\s]+` | `postgres://admin:secret@db:5432` | `[DATABASE_URL_REDACTED]` |
| **Network (RFC 1918)** | `10.x.x.x`, `172.16-31.x.x`, `192.168.x.x` | `remote_addr=192.168.1.45` | `remote_addr=[IP_INTERNAL_REDACTED]` |
| **Trade Secrets** | Configurable proprietary identifiers & formula weights | `alpha_weight_vector: [0.82, 0.14]` | `[PROPRIETARY_ALGO_REDACTED]` |

### 3.2 The Luhn Checksum Algorithm for PANs

A major pitfall of naive regex redaction is over-redaction (e.g., masking UUIDs, transaction numbers, or build IDs that happen to contain 16 digits). 

The Telemetry MCP Server prevents over-redaction by verifying all 13-to-19 digit candidate numbers against the **Luhn Algorithm** ([`is_luhn_valid()`](../../src/telemetry_mcp_server/dlp.py)):

```python
def is_luhn_valid(number: str) -> bool:
    digits = [int(c) for c in number if c.isdigit()]
    if len(digits) < 13 or len(digits) > 19:
        return False
    checksum = 0
    reverse_digits = digits[::-1]
    for idx, d in enumerate(reverse_digits):
        if idx % 2 == 1:
            doubled = d * 2
            checksum += doubled - 9 if doubled > 9 else doubled
        else:
            checksum += d
    return checksum % 10 == 0
```

Only candidates passing the Luhn check are masked; random 16-digit order identifiers or trace IDs pass through unaltered.

---

## 4. Operational Modes: Context-Aware Governance

The DLP engine supports three operational modes configured via the environment variable `SECURITY_MODE` (or passed directly to `sanitize_payload()`):

```mermaid
flowchart TD
    Req["Incoming Log Payload"] --> ModeCheck{"Evaluate SECURITY_MODE"}
    
    ModeCheck -->|"STRICT_LOCAL"| Local["Local Trust Zone (stdio / 127.0.0.1)"]
    Local --> AuditOnlyLog["Record Metrics & Permit Raw Delivery"]
    AuditOnlyLog --> RetLocal["Full Diagnostic Fidelity for On-Prem Model"]
    
    ModeCheck -->|"REDACTED_CLOUD"| Cloud["Untrusted / Cloud Origin (Remote SSE)"]
    Cloud --> MaskRules["Apply Full Regex & Luhn Scrubbing"]
    MaskRules --> IncrMetric["Update DLPAuditMetrics"]
    IncrMetric --> RetCloud["Zero-Leak Sanitized Payload to Cloud Model"]
    
    ModeCheck -->|"AUDIT_ONLY"| Audit["Shadow / Staging Evaluation"]
    Audit --> RecordSim["Record What Would Be Masked"]
    RecordSim --> RetAudit["Deliver Raw Payload with Security Warnings"]
```

### 1. `REDACTED_CLOUD` (Default for External Agents)
- **Target:** External cloud-hosted agent harnesses, remote SSE callers, and commercial frontier models (Claude, OpenAI, Gemini).
- **Behavior:** Enforces aggressive zero-leak redaction. All sensitive tokens, PII, PANs, internal network topologies, and proprietary markers are replaced with structured redaction tokens.
- **Guarantee:** No secret or trade secret leaves the host boundary.

### 2. `STRICT_LOCAL` (On-Premise / Air-Gapped Workstations)
- **Target:** Local models (e.g., Qwen 2.5 Coder 32B running on Ollama or `llama.cpp` on the same machine) communicating over private `stdio`.
- **Behavior:** Allows full-fidelity, unredacted log inspection needed for low-level kernel, memory barrier, or exact trace analysis, while maintaining audit logs of detected sensitive patterns.

### 3. `AUDIT_ONLY` (Observation / Shadow Mode)
- **Target:** Staging environments, performance benchmarking, or compliance audit baselines.
- **Behavior:** Executes the complete regex and checksum pipeline, logs what *would* have been redacted in audit metrics, but returns the raw text untouched.

---

## 5. Live Payload Comparison: Before & After Redaction

### Before Redaction (Raw Log Entry from `payment.log`):
```text
2026-10-26T21:40:15.112Z [ERROR] payment.processor [trace_id=tr-94821]:
ChargeFailed: Gateway timeout connecting to backend at 10.240.12.8:8443.
Customer: user_id=usr_84920 email=jdoe@enterprise.com ssn=000-45-6789
PaymentMethod: card=4111-2222-3333-1111 cvv: 842 exp=12/28
Auth: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6Ikpv...
InternalState: formula_weights: [0.892, 0.104, 0.004] order_book_ring_buffer lock contention
```

### After Redaction (`REDACTED_CLOUD` Mode via Telemetry MCP Server):
```text
2026-10-26T21:40:15.112Z [ERROR] payment.processor [trace_id=tr-94821]:
ChargeFailed: Gateway timeout connecting to backend at [IP_INTERNAL_REDACTED]:8443.
Customer: user_id=usr_84920 email=[EMAIL_REDACTED] ssn=[SSN_REDACTED]
PaymentMethod: card=[CARD_REDACTED_*1111] [CVV_REDACTED] exp=12/28
Auth: Bearer [TOKEN_SCRUBBED]
InternalState: [PROPRIETARY_WEIGHTS_REDACTED] [PROPRIETARY_ALGO_REDACTED] lock contention
```

> [!TIP]
> **Diagnostic Usability:** Notice that the frontier model still has all the semantic information necessary to diagnose the architectural issue (gateway timeout, backend port 8443, lock contention), without any of the liability.

---

## 6. Audit Observability: `get_security_posture`

Compliance frameworks (SOC 2, PCI-DSS, ISO 27001) require verifiable audit trails of security enforcement. The server exposes a dedicated diagnostic tool:

```python
# Calling get_security_posture() in Python or via MCP:
result = mcp.call_tool("get_security_posture", {})
```

### Sample Structured Output:
```json
{
  "status": "HEALTHY",
  "security_mode": "REDACTED_CLOUD",
  "dlp_enabled": true,
  "trust_zone": "GOVERNED_EGRESS",
  "metrics": {
    "redaction_events_total": 42,
    "by_category": {
      "pci_dss_pan": 14,
      "pii_hipaa": 12,
      "credentials_and_tokens": 8,
      "network_topology_rfc1918": 6,
      "trade_secrets_and_algos": 2
    }
  },
  "compliance_status": {
    "pci_dss_requirement_3": "COMPLIANT",
    "hipaa_privacy_rule": "COMPLIANT",
    "zero_cloud_leakage": "ENFORCED"
  }
}
```

---

## 7. Implementation Blueprint for Your Own MCP Server

If you are building your own MCP server and want to replicate this pattern, follow these design rules:

1. **Keep Redaction Middleware Synchronous & Zero-Copy where possible:** Use compiled regex patterns (`re.compile`) at module initialization.
2. **Validate Checksums:** Never rely solely on digit counts for credit cards; always use Luhn validation to avoid destroying harmless telemetry data.
3. **Redact Both Tools and Resources:** Ensure that dynamic MCP resources (e.g., `telemetry://logs/{service}`) pass through the same DLP pipeline as callable tools (`read_recent_errors`).
4. **Never Throw Exceptions on Masking Failures:** If a regex parsing edge case occurs, fail closed by replacing the line with `[MALFORMED_LOG_REDACTED]` rather than crashing the MCP server process.

---

## 8. Related Documentation & Next Steps

- 🏢 [**Hybrid-Trust Architecture & Enterprise Use Cases**](./hybrid_trust_use_cases.md) — Comprehensive guide on HFT, HIPAA, and air-gapped threat models.
- 🤝 [**Sub-Agent Delegation Pattern**](./sub_agent_delegation_pattern.md) — Delegating raw telemetry inspection to an on-premise local sub-agent.
- ⚙️ [**Strict IDE Profile Binding**](./strict_ide_profile_binding.md) — Air-gapping MCP server instances within Continue.dev and VS Code.
- 📖 [**Agent Tool Catalog**](../tools_reference.md) — Full technical schemas for all exposed MCP diagnostic tools.
