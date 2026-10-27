"""Security posture and trust boundary observability tool for Telemetry MCP Server.

Provides AI clients, enterprise gateways, and audit automation with real-time
telemetry on active trust modes, DLP scrubber statistics, path containment policies,
and local inference engine connectivity.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from telemetry_mcp_server.config import settings
from telemetry_mcp_server.dlp import audit_metrics
from telemetry_mcp_server.tools.logs import list_available_services


def _check_local_llm_health(url: str, timeout_sec: float = 0.5) -> dict[str, Any]:
    """Perform non-blocking health check against the local inference endpoint."""
    clean_url = url.rstrip("/")
    probe_url = f"{clean_url}/api/tags"  # Ollama tag endpoint
    try:
        req = urllib.request.Request(probe_url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            if resp.status == 200:
                return {
                    "status": "online",
                    "endpoint": clean_url,
                    "model": settings.local_llm_model,
                    "protocol": "ollama-native",
                }
    except (urllib.error.URLError, TimeoutError, OSError):
        pass

    # Secondary check: /v1/models (LiteLLM, vLLM, llama.cpp)
    probe_url_v1 = f"{clean_url}/v1/models"
    try:
        req = urllib.request.Request(probe_url_v1, method="GET")
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            if resp.status == 200:
                return {
                    "status": "online",
                    "endpoint": clean_url,
                    "model": settings.local_llm_model,
                    "protocol": "openai-compatible",
                }
    except (urllib.error.URLError, TimeoutError, OSError):
        pass

    return {
        "status": "standby / offline",
        "endpoint": clean_url,
        "model": settings.local_llm_model,
        "note": "Sub-agent delegation active with governed local heuristic fallback",
    }


def get_security_posture() -> str:
    """Returns the current hybrid-trust security posture and governance telemetry.

    Use this tool to verify active trust zones (STRICT_LOCAL vs REDACTED_CLOUD),
    inspect real-time DLP redaction counts, verify path containment, and confirm
    least-privilege boundaries before performing sensitive operations.

    Returns:
        JSON string containing trust mode, active DLP rules, cumulative redaction metrics,
        monitored services, and local inference gateway connectivity.
    """
    local_gateway_status = _check_local_llm_health(settings.local_llm_url)

    posture_payload: dict[str, Any] = {
        "hybrid_trust_posture": {
            "active_security_mode": settings.security_mode,
            "dlp_enabled": settings.dlp_enabled,
            "egress_classification": (
                "Zero-Leak Cloud Redaction Active"
                if settings.security_mode == "REDACTED_CLOUD"
                else "Trusted Local stdio (Audited)"
            ),
        },
        "dlp_scrubbers": {
            "pci_dss": "Luhn algorithm checksum verification & cardholder PAN masking",
            "hipaa_pii": "SSN, patient/MRN IDs, email addresses, and phone numbers",
            "secrets_credentials": "OAuth Bearer tokens, JWTs, AWS access keys, private keys, database URLs",
            "network_topology": "RFC 1918 private IPv4 addresses (10.x, 172.16-31.x, 192.168.x)",
            "trade_secrets": "Proprietary HFT symbols and algorithmic weight vectors",
        },
        "redaction_metrics": audit_metrics.to_dict(),
        "governed_boundaries": {
            "filesystem_access": "Strict read-only containment within log directory",
            "path_traversal_guards": "Multi-layer sanitization (null byte, URL decode, regex whitelist, canonical realpath)",
            "log_root": str(settings.log_dir),
            "context_window_caps": {
                "max_lines_tail": settings.max_lines,
                "max_line_length_chars": settings.max_line_length,
            },
        },
        "available_services": list_available_services(),
        "local_inference_gateway": local_gateway_status,
    }

    return json.dumps(posture_payload, indent=2)
