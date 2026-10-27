"""Sub-agent delegation tool for multi-tier Hybrid-Trust architectures.

Enables frontier cloud models (Claude 3.5 Sonnet, GPT-4o) to delegate sensitive
telemetry diagnostics to an on-premise local model (Qwen 2.5 Coder via Ollama or llama.cpp)
or governed local analyzer, returning an abstract, trade-secret-free root cause summary.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path

from telemetry_mcp_server.config import settings
from telemetry_mcp_server.dlp import sanitize_payload
from telemetry_mcp_server.security import safe_resolve_log_path
from telemetry_mcp_server.tools.logs import list_available_services, read_recent_errors


def _query_local_llm(
    prompt: str,
    system_prompt: str,
    url: str,
    model: str,
    timeout_sec: float = 2.0,
) -> str | None:
    """Attempt to query local Ollama or OpenAI-compatible endpoint with strict timeout.

    Args:
        prompt: User prompt content.
        system_prompt: System instruction content.
        url: Base URL (e.g. http://localhost:11434).
        model: Model identifier (e.g. qwen2.5-coder:32b).
        timeout_sec: Connection timeout in seconds.

    Returns:
        Generated text response or None if endpoint unreachable.
    """
    clean_url = url.rstrip("/")
    # Try Ollama native generate endpoint
    ollama_endpoint = f"{clean_url}/api/generate"
    payload = {
        "model": model,
        "prompt": prompt,
        "system": system_prompt,
        "stream": False,
        "options": {"num_predict": 400, "temperature": 0.2},
    }

    try:
        req = urllib.request.Request(
            ollama_endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if isinstance(data, dict) and "response" in data:
                return str(data["response"]).strip()
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        # Fallback to OpenAI-compatible /v1/chat/completions endpoint (LiteLLM, vLLM, llama.cpp)
        openai_endpoint = f"{clean_url}/v1/chat/completions"
        chat_payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            "max_tokens": 400,
            "temperature": 0.2,
        }
        try:
            req = urllib.request.Request(
                openai_endpoint,
                data=json.dumps(chat_payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                if (
                    isinstance(data, dict)
                    and "choices" in data
                    and len(data["choices"]) > 0
                ):
                    choice = data["choices"][0]
                    msg = choice.get("message", {}).get("content", "")
                    if msg:
                        return str(msg).strip()
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
            return None

    return None


def _synthesize_local_briefing(
    service_name: str,
    issue_description: str,
    recent_logs: str,
    max_summary_tokens: int,
) -> str:
    """Perform deterministic, governed local heuristic synthesis when local LLM is offline.

    Extracts error signatures, failure domains, and abstracts proprietary symbols
    into standard computer science concepts.

    Args:
        service_name: Affected service name.
        issue_description: User's reported problem.
        recent_logs: Raw log lines from service.
        max_summary_tokens: Target token ceiling.

    Returns:
        Structured, sanitized incident briefing.
    """
    lines = [line.strip() for line in recent_logs.strip().split("\n") if line.strip()]
    error_lines = [
        line
        for line in lines
        if any(
            lvl in line.upper()
            for lvl in ("ERROR", "CRITICAL", "FATAL", "WARN", "FAIL", "TIMEOUT")
        )
    ]

    # Detect common failure signatures
    signatures: list[str] = []
    remediation_steps: list[str] = []

    joined_text = "\n".join(lines).lower()

    if "redis" in joined_text and "timeout" in joined_text:
        signatures.append("Distributed cache connectivity timeout (Redis pool)")
        remediation_steps.append(
            "Verify Redis node health, network partition status, and connection pool sizing."
        )

    if "deadlock" in joined_text or "lock" in joined_text or "pool" in joined_text:
        signatures.append(
            "Relational database transaction lock contention / pool saturation"
        )
        remediation_steps.append(
            "Inspect slow queries holding row locks; review connection pool idle-timeout configurations."
        )

    if "504" in joined_text or "gateway timeout" in joined_text:
        signatures.append("Upstream external payment gateway timeout (HTTP 504)")
        remediation_steps.append(
            "Activate circuit-breaker fallback and review upstream gateway SLA latency."
        )

    if (
        "ring_buffer" in joined_text
        or "barrier" in joined_text
        or "race" in joined_text
        or "concurrency" in joined_text
        or "lock_free" in joined_text
    ):
        signatures.append(
            "Thread synchronization hazard in lock-free sequence ring buffer"
        )
        remediation_steps.append(
            "Ensure acquire/release memory barrier semantics prior to consumer index advancement."
        )

    if (
        "memory" in joined_text
        or "kv-cache" in joined_text
        or "eviction" in joined_text
        or "oom" in joined_text
    ):
        signatures.append(
            "Inference runtime memory pressure / continuous batching KV-cache exhaustion"
        )
        remediation_steps.append(
            "Enable aggressive prefix caching or adjust max context length batch allocation."
        )

    if not signatures:
        signatures.append("Elevated error rates detected in service telemetry")
        remediation_steps.append(
            "Inspect downstream dependency latencies and recent deployment changes."
        )

    briefing_sections = [
        f"### 🛡️ Local Sub-Agent Telemetry Briefing: `{service_name}`",
        f"**Reported Issue:** {issue_description}",
        "**Identified Root Causes:**",
    ]
    for sig in signatures:
        briefing_sections.append(f"- {sig}")

    briefing_sections.append(
        f"**Sample Telemetry Signals (Sanitized):** {len(error_lines)} anomalous events observed out of {len(lines)} inspected lines."
    )
    briefing_sections.append("**Recommended Next Steps:**")
    for step in remediation_steps:
        briefing_sections.append(f"1. {step}")

    briefing_sections.append(
        "*(Note: Raw telemetry and proprietary algorithm logic retained strictly inside local trust zone)*"
    )

    briefing_text = "\n".join(briefing_sections)

    # Apply strict cloud redaction so no internal secrets or proprietary formulas escape
    sanitized = sanitize_payload(briefing_text, mode="REDACTED_CLOUD")

    # Bound length to approximate max_summary_tokens (~4 chars per token)
    char_limit = max_summary_tokens * 4
    if len(sanitized) > char_limit:
        sanitized = sanitized[:char_limit] + "\n... [briefing truncated to token limit]"

    return sanitized


def delegate_telemetry_investigation(
    service_name: str,
    issue_description: str,
    max_summary_tokens: int = 400,
    base_dir: Path | str | None = None,
) -> str:
    """Delegate raw telemetry analysis and proprietary log inspection to an on-premise local sub-agent.

    Use this tool when triaging incidents that may involve proprietary business logic,
    trade secrets, internal algorithm details, or sensitive system telemetry. Instead of
    requesting raw error logs into frontier cloud model context, this hands off diagnostic
    inspection to an on-premise local model (or governed local analyzer) which synthesizes
    the findings and returns an abstract, trade-secret-free root cause summary.

    Args:
        service_name: Name of target service (e.g., 'auth', 'payment', 'database', 'inference', 'matching_engine').
        issue_description: Description of the observed symptom, alert, or diagnostic goal.
        max_summary_tokens: Maximum tokens in the returned sanitized brief (100-800, default 400).
        base_dir: Optional base directory override for tests or custom environments.

    Returns:
        Sanitized, abstract incident brief containing root-cause analysis, affected
        components, and remediation recommendations without proprietary IP or sensitive data.
    """
    validation = safe_resolve_log_path(service_name, base_dir=base_dir)
    if not validation.is_valid or validation.path is None:
        return f"Error: {validation.error_message}"

    log_path = validation.path
    if not log_path.exists() or not log_path.is_file():
        available = list_available_services(base_dir=base_dir)
        return (
            f"Error: Service '{service_name}' not found. "
            f"Available services: {available}"
        )

    bounded_tokens = max(100, min(max_summary_tokens, 800))

    # Read recent logs strictly locally
    raw_logs = read_recent_errors(
        service_name=service_name, lines=60, base_dir=base_dir
    )

    # Step 1: Attempt query to local LLM if configured and reachable
    system_prompt = (
        "You are an on-premise SRE diagnostic sub-agent operating in a zero-egress zone. "
        "Your task is to analyze internal logs, diagnose root cause, and synthesize an "
        "abstract incident briefing. CRITICAL REQUIREMENT: Redact and abstract all proprietary "
        "trade secret symbols, file paths, and internal IPs into standard computer science concepts. "
        f"Keep your entire briefing under {bounded_tokens} tokens."
    )
    user_prompt = (
        f"Service: {service_name}\n"
        f"Reported Issue: {issue_description}\n\n"
        f"Recent Telemetry Logs:\n{raw_logs}\n\n"
        "Provide: 1) Abstract Root Cause, 2) Blast Radius, 3) Recommended Remediation."
    )

    local_llm_result = _query_local_llm(
        prompt=user_prompt,
        system_prompt=system_prompt,
        url=settings.local_llm_url,
        model=settings.local_llm_model,
        timeout_sec=1.5,
    )

    if local_llm_result:
        # Enforce DLP pass on LLM output to guarantee zero leak
        sanitized_llm_output = sanitize_payload(local_llm_result, mode="REDACTED_CLOUD")
        return (
            f"### 🛡️ On-Premise Sub-Agent ({settings.local_llm_model}) Diagnostic Brief\n"
            f"{sanitized_llm_output}"
        )

    # Step 2: Fallback to governed local heuristic synthesizer
    return _synthesize_local_briefing(
        service_name=service_name,
        issue_description=issue_description,
        recent_logs=raw_logs,
        max_summary_tokens=bounded_tokens,
    )
