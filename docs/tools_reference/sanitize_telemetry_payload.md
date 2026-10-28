# MCP Tool Reference: `sanitize_telemetry_payload`

| Property | Value |
| :--- | :--- |
| **Tool Name** | `sanitize_telemetry_payload` |
| **Module** | [`telemetry_mcp_server.dlp`](../../src/telemetry_mcp_server/dlp.py) |
| **Server Entrypoint** | [`telemetry_mcp_server.server.sanitize_telemetry_payload`](../../src/telemetry_mcp_server/server.py) |
| **MCP Primitive** | Tool |
| **Category** | Data Loss Prevention (DLP) & Privacy Governance |
| **Trust Classification** | Governed Utility / Privacy Scrubber |

---

## 1. Overview & Operational Intent

The `sanitize_telemetry_payload` tool exposes the server's internal Data Loss Prevention (DLP) engine as an on-demand, callable MCP tool. It redacts Payment Card Industry data (PCI-DSS PANs validated via the Luhn algorithm), Healthcare and Personal Identifiable Information (HIPAA / PII), cloud credentials, secrets, RFC 1918 private network topology, and proprietary trade-secret markers.

### Why This Tool Replaces Fragile Client-Side Regex
In many AI architectures, developers attempt client-side string sanitization in TypeScript or Python before prompting an LLM.
This client-side approach suffers from critical flaws:
1. **False Positives on Random Integers:** Naive 16-digit regexes corrupt trace IDs, timestamps, or memory offsets. The DLP engine incorporates the mathematical **Luhn Checksum Algorithm** ($O(n)$) to verify that a number is a genuine payment card before masking it.
2. **Fragile Regex Engines:** Regexes in application code fail to catch multi-line private keys, escaped JWTs, or nested JSON structures.
3. **Inconsistent Trust Zones:** Sanitization rules must vary dynamically based on whether the downstream recipient is an on-premise local model or an external cloud endpoint.

`sanitize_telemetry_payload` centralizes data sanitization at the MCP protocol boundary, providing deterministic, thread-safe, and audited payload redaction.

---

## 2. Interface Specification

### Python Signature

```python
def sanitize_telemetry_payload(
    payload: str,
    trust_mode: str | None = None,
) -> str:
    """Sanitize a text or JSON telemetry payload through the server DLP engine.

    Use this tool to preview how the MCP server redacts credentials, PII/PANs,
    internal IPs, and proprietary symbols under different trust modes.

    Args:
        payload: Input text containing potential telemetry or error logs.
        trust_mode: Optional security mode ('STRICT_LOCAL', 'REDACTED_CLOUD', 'AUDIT_ONLY').
            Defaults to the server's active security_mode.

    Returns:
        Sanitized text payload.
    """
```

### Parameter Specification

| Parameter | Type | Required | Default | Allowed Values | Description |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `payload` | `string` | **Yes** | — | Any UTF-8 string | Input log line, stack trace, error dump, or JSON payload to scrub. |
| `trust_mode` | `string` | No | `None` | `STRICT_LOCAL`, `REDACTED_CLOUD`, `AUDIT_ONLY` | Security mode override. If omitted, uses server's `settings.security_mode`. |

### Generated MCP Tool Schema (`tools/list`)

```json
{
  "name": "sanitize_telemetry_payload",
  "description": "Sanitize a text or JSON telemetry payload through the server DLP engine. Use this tool to preview how the MCP server redacts credentials, PII/PANs, internal IPs, and proprietary symbols under different trust modes.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "payload": {
        "type": "string",
        "description": "Input text containing potential telemetry or error logs."
      },
      "trust_mode": {
        "type": "string",
        "description": "Optional security mode ('STRICT_LOCAL', 'REDACTED_CLOUD', 'AUDIT_ONLY'). Defaults to the server's active security_mode."
      }
    },
    "required": ["payload"]
  }
}
```

---

## 3. DLP Scrubber Categories & Replacement Rules

```mermaid
flowchart TD
    RawInput["Input Payload String"] --> LuhnTest{"Candidate PAN (13-19 digits)?<br/>Run Luhn Checksum"}
    LuhnTest -->|Valid PAN| MaskPAN["Replace with [CARD_REDACTED_*last4]"]
    LuhnTest -->|Invalid| NextRule1["Check HIPAA / PII"]
    
    NextRule1 --> SSN{"SSN / MRN / Patient ID / Email?"}
    SSN -->|Match| MaskPII["Replace with [SSN_REDACTED] / [PATIENT_ID_REDACTED]"]
    SSN -->|No| NextRule2["Check Secrets & Keys"]
    
    NextRule2 --> Secrets{"Bearer / JWT / AWS / Private Key / DB URL?"}
    Secrets -->|Match| MaskSecrets["Replace with [TOKEN_SCRUBBED] / [KEY_REDACTED]"]
    Secrets -->|No| NextRule3["Check Topology & Trade Secrets"]
    
    NextRule3 --> Topology{"RFC 1918 IP / HFT Algo Symbols?"}
    Topology -->|Match| MaskTopology["Replace with [INTERNAL_IP_REDACTED] / [PROPRIETARY_ALGO_REDACTED]"]
    Topology -->|No| FinalOutput["Emit Clean Payload"]
    
    MaskPAN --> FinalOutput
    MaskPII --> FinalOutput
    MaskSecrets --> FinalOutput
    MaskTopology --> FinalOutput
```

| Category | Target Patterns | Sanitization Rule / Replacement | Regulatory Driver |
| :--- | :--- | :--- | :--- |
| **Payment Cards** | Luhn-valid credit card numbers (13-19 digits) | `[CARD_REDACTED_*<last4>]` | PCI-DSS v4.0 Req 3.4 |
| **Card Security Codes** | `cvv: 123`, `cvc = 4567` | `[CVV_REDACTED]` | PCI-DSS v4.0 Req 3.2 |
| **Healthcare / PII** | US Social Security Numbers (`\d{3}-\d{2}-\d{4}`) | `[SSN_REDACTED]` | HIPAA Privacy Rule § 164.514 |
| **Patient Identifiers** | `patient_id: P-881`, `MRN: 99482` | `patient_id: [PATIENT_ID_REDACTED]` | HIPAA Expert Determination |
| **OAuth & Bearer** | `Bearer eyJ...`, `Authorization: Bearer <token>` | `Bearer [TOKEN_SCRUBBED]` | NIST SP 800-63B |
| **AWS Credentials** | Access keys starting with `AKIA`, `ASIA` | `[AWS_KEY_REDACTED]` | CIS Security Benchmark |
| **Private Keys** | `-----BEGIN RSA PRIVATE KEY-----` | `[PRIVATE_KEY_REDACTED]` | FIPS 140-3 |
| **Database URLs** | `postgres://user:pass@host:5432/db` | `[DATABASE_URL_REDACTED]` | Zero Trust Architecture |
| **Network Topology** | `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16` | `[INTERNAL_IP_REDACTED]` | Network Perimeter Defense |
| **Trade Secrets** | HFT ring buffers, proprietary formula weights | `[PROPRIETARY_ALGO_REDACTED]` | Defend Trade Secrets Act (DTSA) |

---

## 4. Operational Trust Modes

The DLP engine supports three operational modes:

1. **`REDACTED_CLOUD` (Default for Cloud Models):**
   - Zero-leak policy. All PII, PCI, credentials, RFC 1918 IPs, and proprietary symbols are actively scrubbed.
   - Used whenever responses may transit to public cloud providers (Anthropic, OpenAI, Google Cloud).
2. **`STRICT_LOCAL` (On-Premise Engineering):**
   - Preserves internal RFC 1918 IPs and trace identifiers for low-level local debugging over trusted `stdio`.
   - Still scrubs cleartext passwords, private keys, and live credit card numbers.
3. **`AUDIT_ONLY` (Shadow Mode):**
   - Emits unredacted payloads while updating internal audit counters. Used during staging to measure false-positive rates before turning on enforcement.

---

## 5. Concrete Invocation Example

### Sanitize Multi-Threat Log Snippet

#### Request
```json
{
  "jsonrpc": "2.0",
  "id": 108,
  "method": "tools/call",
  "params": {
    "name": "sanitize_telemetry_payload",
    "arguments": {
      "payload": "[2026-10-25 19:00:01] Customer email=john.doe@example.com charged card=4532-0150-1892-4242 cvv=882 on host 10.0.4.15 using Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.e30.t-419b",
      "trust_mode": "REDACTED_CLOUD"
    }
  }
}
```

#### Response
```json
{
  "jsonrpc": "2.0",
  "id": 108,
  "result": {
    "content": [
      {
        "type": "text",
        "text": "[2026-10-25 19:00:01] Customer email=[EMAIL_REDACTED] charged card=[CARD_REDACTED_*4242] [CVV_REDACTED] on host [INTERNAL_IP_REDACTED] using Bearer [TOKEN_SCRUBBED]"
      }
    ],
    "isError": false
  }
}
```

---

## 6. Enterprise Productionization & Expansion Blueprint

In enterprise environments, `sanitize_telemetry_payload` scales into an **Enterprise DLP Gateway with Named Entity Recognition (NER) & Reversible Tokenization**.

```mermaid
flowchart TD
    RawInput["Raw Telemetry / Error Payload"] --> Hyperscan["Intel Hyperscan / Vectorscan Engine<br/>(Multi-Gigabit/s SIMD Regex Scan)"]
    
    Hyperscan --> RegexOutput["Regex Masked Intermediate"]
    RegexOutput --> Presidio["Microsoft Presidio / spaCy NER Engine<br/>(Transformer Model for Unstructured PII)"]
    
    Presidio --> Tokenizer{"Tokenization Strategy Router"}
    
    Tokenizer -->|Irreversible| Mask["Static [REDACTED] Masking"]
    Tokenizer -->|Format Preserving| Vault["HashiCorp Vault Transform / Protegrity<br/>(Reversible Cryptographic Tokenization)"]
    Tokenizer -->|Differential Privacy| Synthetic["Synthetic Data Injection (Faker)<br/>(Preserves LLM grammar & context)"]
    
    Mask --> AuditSIEM["Stream Metric to SIEM (Splunk / Sentinel)"]
    Vault --> AuditSIEM
    Synthetic --> AuditSIEM
    
    AuditSIEM --> CleanOutput["Clean Payload Delivered to Agent"]
```

### Key Enterprise Expansions

#### 1. Hybrid Regex + Named Entity Recognition (NER) Models (Microsoft Presidio)
Regex is effective for structured identifiers (credit cards, SSNs) but fails on unstructured clinical or conversational text (e.g., doctor notes: *"Patient John Doe presented with elevated heart rate"*).
**Enterprise Expansion:** Pipe text through Microsoft Presidio backed by a lightweight transformer (e.g. `roberta-base-ner`) to detect real names, medical terms, and geographic addresses that have no fixed regex format.

#### 2. Reversible Format-Preserving Encryption (FPE) & Vault Tokenization
When an incident is escalated from an AI agent to human SREs, humans may need to un-redact a customer transaction ID to query the payment processor.
**Enterprise Expansion:** Integrate with HashiCorp Vault Transform or Protegrity. The credit card `4532-0150-1892-4242` is transformed into an encrypted format-preserving token `4532-9901-7712-4242`. The AI model can reason over the distinct token, and authorized security staff can de-tokenize it in Vault using authorized audit keys.

#### 3. Hardware SIMD Acceleration with Intel Hyperscan
For multi-gigabyte log streams, Python's `re` module becomes CPU-bound. Replace it with **Intel Hyperscan** or **Vectorscan** bindings. Hyperscan compiles thousands of regular expressions into a single Deterministic Finite Automaton (DFA) executed using AVX-512 instructions, scanning payloads at **over 4 GB/second per core**.

#### 4. Synthetic Replacement & Differential Privacy
Rather than inserting jarring `[REDACTED]` markers which can degrade LLM grammar and reasoning, use synthetic generation (e.g., Python `Faker`) to replace real patient names with plausible pseudonyms (*"Patient Alice Smith"*), preserving natural language semantics while maintaining 100% privacy.

### Production Reference Implementation

Below is a reference implementation showing how to integrate Microsoft Presidio and format-preserving tokenization into an enterprise DLP engine:

```python
"""Enterprise DLP Engine with Presidio NER and Vault Tokenization."""

from __future__ import annotations

import re
from typing import Any
from presidio_analyzer import AnalyzerEngine, PatternRecognizer
from presidio_anonymizer import AnonymizerEngine
from presidio_anonymizer.entities import OperatorConfig


class EnterpriseDLPEngine:
    """Production DLP engine combining compiled regexes and NLP NER."""

    def __init__(self) -> None:
        # Initialize Presidio NLP analyzer
        self.analyzer = AnalyzerEngine()
        self.anonymizer = AnonymizerEngine()

        # Add custom HFT / Enterprise recognizers
        hft_pattern = (
            r"\b(order_book_ring_buffer|lock_free_sequence_barrier|alpha_weight)\b"
        )
        hft_recognizer = PatternRecognizer(
            supported_entity="TRADE_SECRET",
            deny_list=[
                "order_book_ring_buffer",
                "lock_free_sequence_barrier",
                "alpha_weight",
            ],
        )
        self.analyzer.registry.add_recognizer(hft_recognizer)

    def sanitize(
        self,
        text: str,
        mode: str = "REDACTED_CLOUD",
    ) -> str:
        """Sanitize text using hybrid NLP and regex pipelines."""
        if mode == "AUDIT_ONLY":
            return text

        # 1. Analyze text for PII, Financials, and Trade Secrets
        results = self.analyzer.analyze(
            text=text,
            entities=[
                "CREDIT_CARD",
                "EMAIL_ADDRESS",
                "PHONE_NUMBER",
                "US_SSN",
                "IP_ADDRESS",
                "TRADE_SECRET",
            ],
            language="en",
        )

        # 2. Anonymize entities with custom replacement operators
        operators = {
            "CREDIT_CARD": OperatorConfig("mask", {"masking_char": "*", "chars_to_mask": 12, "from_end": True}),
            "EMAIL_ADDRESS": OperatorConfig("replace", {"new_value": "[EMAIL_REDACTED]"}),
            "PHONE_NUMBER": OperatorConfig("replace", {"new_value": "[PHONE_REDACTED]"}),
            "US_SSN": OperatorConfig("replace", {"new_value": "[SSN_REDACTED]"}),
            "IP_ADDRESS": OperatorConfig("replace", {"new_value": "[INTERNAL_IP_REDACTED]"}),
            "TRADE_SECRET": OperatorConfig("replace", {"new_value": "[PROPRIETARY_ALGO_REDACTED]"}),
        }

        anonymized_result = self.anonymizer.anonymize(
            text=text,
            analyzer_results=results,
            operators=operators,
        )

        return anonymized_result.text
```

---

## 7. Related MCP Primitives

- **Complementary Tool:** [`get_security_posture`](./get_security_posture.md) — Inspects real-time redaction counters incremented by this tool.
- **Governed Tool:** [`read_recent_errors`](./read_recent_errors.md) — Uses this engine as mandatory output middleware.
- **Architectural Pattern:** [Dynamic DLP Pattern](../architecture/dynamic_dlp_pattern.md) — Detailed system design of the in-server DLP layer.
