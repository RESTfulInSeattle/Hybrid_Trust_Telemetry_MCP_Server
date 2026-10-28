#!/usr/bin/env python3
"""AI Gateway Router & Tool-Triggered Model Swapping Proxy.

Implements Hybrid-Trust Pattern 4 (Network Proxy Governance):
Intercepts OpenAI-compatible `/v1/chat/completions` requests, inspects tool schemas
and message histories for sensitive telemetry tools (e.g., `read_recent_errors`,
`get_system_health`), and dynamically routes them to an on-premise local model
(`local-secure`) while keeping benign coding prompts routed to frontier cloud
models (`frontier-reasoning`).

Key Capabilities:
1. Tool-Name Routing Engine: Evaluates tool definitions and execution traces.
2. Fail-Closed Security: Blocks execution if local secure endpoints are offline,
   guaranteeing zero telemetry leakage to cloud providers.
3. State Pruning & Context Hygiene: Strips or abstracts raw tool logs before cloud resumption.
4. Centralized Observability & Metrics: Tracks diversion metrics, token savings, and audit events.
"""

from __future__ import annotations

import argparse
import datetime
import json
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

PROJECT_ROOT = Path(__file__).resolve().parent.parent

DEFAULT_SENSITIVE_TOOLS: frozenset[str] = frozenset(
    {
        "read_recent_errors",
        "get_system_health",
        "search_logs_by_pattern",
        "filter_logs",
        "delegate_telemetry_investigation",
        "get_security_posture",
        "sanitize_telemetry_payload",
    }
)

DEFAULT_LOCAL_MODEL = "local-secure"
DEFAULT_CLOUD_MODEL = "frontier-reasoning"
DEFAULT_LOCAL_URL = "http://localhost:11434/v1"
DEFAULT_CLOUD_URL = "https://api.anthropic.com/v1"


@dataclass(frozen=True)
class RoutingDecision:
    """Represents a policy routing determination made by the Gateway Router."""

    target_model: str
    target_endpoint: str
    is_sensitive: bool
    matched_tools: list[str]
    reason: str
    fail_closed: bool = True
    strip_context: bool = True

    def to_dict(self) -> dict[str, Any]:
        """Convert routing decision to a serializable dictionary."""
        return {
            "target_model": self.target_model,
            "target_endpoint": self.target_endpoint,
            "is_sensitive": self.is_sensitive,
            "matched_tools": self.matched_tools,
            "reason": self.reason,
            "fail_closed": self.fail_closed,
            "strip_context": self.strip_context,
        }


class GatewayMetrics:
    """Thread-safe telemetry metrics and audit recorder for Gateway Router."""

    def __init__(self) -> None:
        self.total_requests: int = 0
        self.routed_to_local: int = 0
        self.routed_to_cloud: int = 0
        self.sensitive_tools_intercepted: int = 0
        self.fail_closed_violations: int = 0
        self.estimated_tokens_saved: int = 0
        self.recent_latencies_ms: list[float] = []
        self.audit_events: list[dict[str, Any]] = []

    def record_routing(
        self,
        decision: RoutingDecision,
        status_code: int,
        latency_ms: float,
        tokens_saved: int = 0,
        client_ip: str = "127.0.0.1",
    ) -> None:
        """Record an evaluated routing transaction.

        Args:
            decision: Policy decision object.
            status_code: HTTP response status code.
            latency_ms: Processing latency in milliseconds.
            tokens_saved: Estimated token savings from zero-egress diversion.
            client_ip: Calling client IP address.
        """
        self.total_requests += 1
        if decision.is_sensitive:
            self.routed_to_local += 1
            self.sensitive_tools_intercepted += len(decision.matched_tools)
            self.estimated_tokens_saved += tokens_saved
        else:
            self.routed_to_cloud += 1

        self.recent_latencies_ms.append(round(latency_ms, 2))
        if len(self.recent_latencies_ms) > 100:
            self.recent_latencies_ms.pop(0)

        event = {
            "timestamp": datetime.datetime.now(datetime.UTC).isoformat(),
            "client_ip": client_ip,
            "target_model": decision.target_model,
            "target_endpoint": decision.target_endpoint,
            "is_sensitive": decision.is_sensitive,
            "matched_tools": decision.matched_tools,
            "status_code": status_code,
            "fail_closed": False,
            "latency_ms": round(latency_ms, 2),
            "tokens_saved": tokens_saved,
        }
        self.audit_events.append(event)
        if len(self.audit_events) > 200:
            self.audit_events.pop(0)

    def record_fail_closed(
        self,
        decision: RoutingDecision,
        error_message: str,
        client_ip: str = "127.0.0.1",
    ) -> None:
        """Record a fail-closed boundary enforcement event.

        Args:
            decision: Policy decision object that triggered fail-closed.
            error_message: Reason why local endpoint was unavailable.
            client_ip: Calling client IP address.
        """
        self.total_requests += 1
        self.routed_to_local += 1
        self.sensitive_tools_intercepted += len(decision.matched_tools)
        self.fail_closed_violations += 1

        event = {
            "timestamp": datetime.datetime.now(datetime.UTC).isoformat(),
            "client_ip": client_ip,
            "target_model": decision.target_model,
            "target_endpoint": decision.target_endpoint,
            "is_sensitive": True,
            "matched_tools": decision.matched_tools,
            "status_code": 503,
            "fail_closed": True,
            "error": error_message,
        }
        self.audit_events.append(event)
        if len(self.audit_events) > 200:
            self.audit_events.pop(0)

    def to_dict(self) -> dict[str, Any]:
        """Convert metrics state to structured dictionary."""
        avg_latency = (
            round(sum(self.recent_latencies_ms) / len(self.recent_latencies_ms), 2)
            if self.recent_latencies_ms
            else 0.0
        )
        return {
            "total_requests": self.total_requests,
            "routed_to_local": self.routed_to_local,
            "routed_to_cloud": self.routed_to_cloud,
            "sensitive_tools_intercepted": self.sensitive_tools_intercepted,
            "fail_closed_violations": self.fail_closed_violations,
            "estimated_tokens_saved": self.estimated_tokens_saved,
            "average_latency_ms": avg_latency,
            "active_audit_records": len(self.audit_events),
        }

    def reset(self) -> None:
        """Reset all metrics and audit records."""
        self.total_requests = 0
        self.routed_to_local = 0
        self.routed_to_cloud = 0
        self.sensitive_tools_intercepted = 0
        self.fail_closed_violations = 0
        self.estimated_tokens_saved = 0
        self.recent_latencies_ms.clear()
        self.audit_events.clear()


@dataclass
class ToolRoutingEngine:
    """Evaluates JSON-RPC / OpenAI completion payloads for sensitive MCP tools."""

    sensitive_tools: set[str] = field(
        default_factory=lambda: set(DEFAULT_SENSITIVE_TOOLS)
    )
    local_model: str = DEFAULT_LOCAL_MODEL
    cloud_model: str = DEFAULT_CLOUD_MODEL
    local_url: str = DEFAULT_LOCAL_URL
    cloud_url: str = DEFAULT_CLOUD_URL
    strip_raw_results: bool = True
    fail_closed: bool = True

    def evaluate_request(self, payload: dict[str, Any]) -> RoutingDecision:
        """Evaluate an incoming completion request against routing policies.

        Args:
            payload: OpenAI-compatible JSON payload containing messages and tools.

        Returns:
            RoutingDecision specifying the target tier, model, and justification.
        """
        matched: list[str] = []

        # 1. Inspect tool schemas in payload
        tools = payload.get("tools")
        if isinstance(tools, list):
            for t in tools:
                if isinstance(t, dict):
                    fn = t.get("function")
                    name = (
                        fn.get("name")
                        if isinstance(fn, dict)
                        else (t.get("name") or "")
                    )
                    if name in self.sensitive_tools:
                        matched.append(str(name))

        # 2. Inspect message history (tool calls and results)
        messages = payload.get("messages")
        if isinstance(messages, list):
            for msg in messages:
                if not isinstance(msg, dict):
                    continue

                # Check assistant tool_calls
                tool_calls = msg.get("tool_calls")
                if isinstance(tool_calls, list):
                    for tc in tool_calls:
                        if isinstance(tc, dict):
                            fn = tc.get("function")
                            name = (
                                fn.get("name")
                                if isinstance(fn, dict)
                                else (tc.get("name") or "")
                            )
                            if name in self.sensitive_tools:
                                matched.append(str(name))

                # Check tool response role
                role = str(msg.get("role", "")).lower()
                if role in ("tool", "function"):
                    name = str(msg.get("name", ""))
                    if name in self.sensitive_tools:
                        matched.append(name)

                    # Inspect tool content for sensitive telemetry signatures
                    content = str(msg.get("content", ""))
                    if any(
                        sig in content.lower()
                        for sig in (
                            "order_book_ring_buffer",
                            "lock_free_sequence",
                            "formula_weights",
                            "redis connection timeout",
                            "desync in proprietary",
                        )
                    ):
                        matched.append("embedded_telemetry_trace")

        # 3. Explicit model override check
        requested_model = str(payload.get("model", "")).lower()
        if requested_model == self.local_model.lower():
            matched.append("explicit_local_model_requested")

        is_sensitive = len(matched) > 0
        deduped_matches = sorted(set(matched))

        if is_sensitive:
            return RoutingDecision(
                target_model=self.local_model,
                target_endpoint=self.local_url,
                is_sensitive=True,
                matched_tools=deduped_matches,
                reason=f"Sensitive telemetry tool(s) detected: {deduped_matches}",
                fail_closed=self.fail_closed,
                strip_context=self.strip_raw_results,
            )

        return RoutingDecision(
            target_model=self.cloud_model,
            target_endpoint=self.cloud_url,
            is_sensitive=False,
            matched_tools=[],
            reason="No sensitive telemetry tools detected; routing to frontier reasoning tier",
            fail_closed=self.fail_closed,
            strip_context=self.strip_raw_results,
        )

    def prune_context_for_cloud(
        self, messages: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Prune multi-line raw tool logs from message history before cloud handoff.

        Args:
            messages: Message history list.

        Returns:
            Sanitized message list with raw logs abstracted.
        """
        pruned_messages: list[dict[str, Any]] = []
        for msg in messages:
            msg_copy = dict(msg)
            role = str(msg_copy.get("role", "")).lower()
            if role in ("tool", "function"):
                content = str(msg_copy.get("content", ""))
                if (
                    len(content) > 150
                    or "\n" in content
                    or any(
                        sens in content.lower()
                        for sens in ("timeout", "error", "weights", "barrier")
                    )
                ):
                    msg_copy["content"] = (
                        "[LOCAL_MODEL_SYNTHESIZED_BRIEF: Raw internal telemetry and proprietary "
                        "stack traces pruned to prevent cloud egress]"
                    )
            pruned_messages.append(msg_copy)
        return pruned_messages

    def estimate_tokens_in_payload(self, payload: dict[str, Any]) -> int:
        """Estimate token volume within request messages (~4 chars per token).

        Args:
            payload: Request dictionary.

        Returns:
            Approximate token count.
        """
        messages = payload.get("messages", [])
        total_chars = 0
        if isinstance(messages, list):
            for m in messages:
                if isinstance(m, dict):
                    content = str(m.get("content", ""))
                    total_chars += len(content)
        return max(1, total_chars // 4)


def parse_litellm_yaml(config_path: Path) -> ToolRoutingEngine:
    """Parse LiteLLM YAML config file to instantiate a ToolRoutingEngine.

    Handles standard PyYAML if installed, or falls back to built-in structured parsing.

    Args:
        config_path: Path to `litellm_config.yaml`.

    Returns:
        Configured ToolRoutingEngine instance.
    """
    engine = ToolRoutingEngine()
    if not config_path.exists():
        return engine

    content = config_path.read_text(encoding="utf-8")

    # Try PyYAML if available
    try:
        import yaml  # type: ignore

        data = yaml.safe_load(content)
        if isinstance(data, dict):
            # Parse models
            models = data.get("model_list", [])
            for m in models:
                if isinstance(m, dict):
                    name = m.get("model_name", "")
                    params = m.get("litellm_params", {})
                    if "local" in name.lower():
                        engine.local_model = name
                        if "api_base" in params:
                            engine.local_url = params["api_base"]
                    elif (
                        "frontier" in name.lower()
                        or "general" in name.lower()
                        or "cloud" in name.lower()
                    ):
                        engine.cloud_model = name

            # Parse router settings
            router = data.get("router_settings", {})
            rules = router.get("rules", [])
            for rule in rules:
                if isinstance(rule, dict):
                    if "match_tool_names" in rule:
                        engine.sensitive_tools = set(rule["match_tool_names"])
                    if "route_to" in rule:
                        engine.local_model = rule["route_to"]
                    if "strip_raw_tool_results_before_cloud_handoff" in rule:
                        engine.strip_raw_results = bool(
                            rule["strip_raw_tool_results_before_cloud_handoff"]
                        )
                    if "fail_closed" in rule:
                        engine.fail_closed = bool(rule["fail_closed"])
                    if "default" in rule:
                        engine.cloud_model = rule["default"]

            return engine
    except ImportError:
        pass

    # Built-in lightweight regex/key-value parser for litellm_config.yaml
    sensitive_tools: list[str] = []
    in_match_tool_names = False

    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        if "model_name:" in line:
            parts = line.split(":", 1)
            name = parts[1].strip()
            if "local" in name.lower():
                engine.local_model = name
            elif "frontier" in name.lower() or "general" in name.lower():
                engine.cloud_model = name

        elif "api_base:" in line:
            parts = line.split(":", 1)
            engine.local_url = parts[1].strip().strip('"').strip("'")

        elif "match_tool_names:" in line:
            in_match_tool_names = True
            continue

        elif in_match_tool_names:
            if line.startswith("- "):
                tool = line[2:].strip().strip('"').strip("'")
                sensitive_tools.append(tool)
            else:
                in_match_tool_names = False

        if "strip_raw_tool_results_before_cloud_handoff:" in line:
            val = line.split(":", 1)[1].strip().lower()
            engine.strip_raw_results = val in ("true", "1", "yes")

        elif "fail_closed:" in line:
            val = line.split(":", 1)[1].strip().lower()
            engine.fail_closed = val in ("true", "1", "yes")

        elif "default:" in line:
            val = line.split(":", 1)[1].strip().strip('"').strip("'")
            engine.cloud_model = val

    if sensitive_tools:
        engine.sensitive_tools = set(sensitive_tools)

    return engine


def simulate_upstream_response(
    decision: RoutingDecision,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Generate a realistic mock OpenAI completion response for testing and demonstrations.

    Args:
        decision: The evaluated routing decision.
        payload: Input request payload.

    Returns:
        Structured OpenAI-compatible chat completion response dictionary.
    """
    timestamp = int(time.time())

    if decision.is_sensitive:
        content = (
            "### 🛡️ Local Sub-Agent Telemetry Briefing (Zero-Cloud Egress)\n"
            "- Analyzed internal service logs for error signatures.\n"
            "- Identified recurring connection timeouts to Redis cache at 10.0.4.12:6379.\n"
            "- Recommended remediation: Verify Redis cluster failover and connection pool size.\n"
            "*(Proprietary trade secrets and internal IPs retained inside local trust zone)*"
        )
        model_name = decision.target_model
        return {
            "id": f"chatcmpl-local-{timestamp}",
            "object": "chat.completion",
            "created": timestamp,
            "model": model_name,
            "routing_metadata": {
                "routed_tier": "local-secure",
                "zero_cloud_egress": True,
                "matched_sensitive_tools": decision.matched_tools,
                "target_endpoint": decision.target_endpoint,
            },
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": content,
                    },
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": 140,
                "completion_tokens": 65,
                "total_tokens": 205,
            },
        }

    # Frontier reasoning tier mock
    content = (
        "I have reviewed the plan. To safely triage this issue without exposing internal logs, "
        "we will coordinate high-level architecture tasks while delegating telemetry analysis "
        "to the local secure analyzer."
    )
    return {
        "id": f"chatcmpl-frontier-{timestamp}",
        "object": "chat.completion",
        "created": timestamp,
        "model": decision.target_model,
        "routing_metadata": {
            "routed_tier": "frontier-reasoning",
            "zero_cloud_egress": False,
            "matched_sensitive_tools": [],
            "target_endpoint": decision.target_endpoint,
        },
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": content,
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": 80,
            "completion_tokens": 35,
            "total_tokens": 115,
        },
    }


def forward_http_request(
    endpoint: str,
    payload: dict[str, Any],
    timeout_sec: float = 3.0,
) -> tuple[int, dict[str, Any]]:
    """Forward an OpenAI completion request over HTTP to an upstream inference endpoint.

    Args:
        endpoint: Target base URL or complete chat completions endpoint.
        payload: JSON request body.
        timeout_sec: HTTP timeout limit.

    Returns:
        Tuple of (status_code, response_dict).
    """
    clean_url = endpoint.rstrip("/")
    if not clean_url.endswith("/chat/completions"):
        clean_url = f"{clean_url}/chat/completions"

    data_bytes = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        clean_url,
        data=data_bytes,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            body = resp.read().decode("utf-8")
            return resp.status, json.loads(body)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")
        try:
            parsed = json.loads(body)
        except (json.JSONDecodeError, UnicodeDecodeError):
            parsed = {"error": {"message": str(e), "code": e.code}}
        return e.code, parsed
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        return 503, {
            "error": {
                "message": f"Upstream connection failed: {e}",
                "type": "upstream_unreachable",
                "code": 503,
            }
        }


def create_gateway_app(
    engine: ToolRoutingEngine | None = None,
    mock_mode: bool = False,
    metrics: GatewayMetrics | None = None,
) -> Starlette:
    """Create a configured Starlette ASGI application for the Gateway Router.

    Args:
        engine: ToolRoutingEngine determining routing policy rules.
        mock_mode: If True, simulates upstream completions without network calls.
        metrics: Optional shared metrics tracker instance.

    Returns:
        Starlette application instance.
    """
    active_engine = engine or ToolRoutingEngine()
    active_metrics = metrics or GatewayMetrics()

    async def chat_completions(request: Request) -> Response:
        """Handle POST /v1/chat/completions with tool-triggered model routing."""
        start_time = time.perf_counter()
        client_ip = request.client.host if request.client else "127.0.0.1"

        try:
            payload = await request.json()
        except (json.JSONDecodeError, ValueError):
            return JSONResponse(
                {"error": {"message": "Invalid JSON body", "type": "bad_request"}},
                status_code=400,
            )

        if not isinstance(payload, dict):
            return JSONResponse(
                {
                    "error": {
                        "message": "Payload must be a JSON object",
                        "type": "bad_request",
                    }
                },
                status_code=400,
            )

        decision = active_engine.evaluate_request(payload)
        tokens_in_payload = active_engine.estimate_tokens_in_payload(payload)

        # -------------------------------------------------------------
        # 🛡️ FAIL-CLOSED SECURITY GUARANTEE
        # -------------------------------------------------------------
        # If the request contains sensitive tools and upstream is not mock,
        # verify that the local secure endpoint is reachable. If unreachable,
        # ABORT immediately with 503. NEVER FAIL OPEN TO CLOUD!
        # -------------------------------------------------------------
        if mock_mode:
            response_data = simulate_upstream_response(decision, payload)
            status_code = 200
        else:
            # If routing to cloud, ensure context is pruned if requested
            forward_payload = dict(payload)
            if (
                not decision.is_sensitive
                and decision.strip_context
                and "messages" in forward_payload
                and isinstance(forward_payload["messages"], list)
            ):
                forward_payload["messages"] = active_engine.prune_context_for_cloud(
                    forward_payload["messages"]
                )

            status_code, response_data = forward_http_request(
                endpoint=decision.target_endpoint,
                payload=forward_payload,
            )

            # FAIL-CLOSED CHECK: If sensitive and local endpoint failed
            if decision.is_sensitive and status_code >= 500:
                fail_msg = (
                    "Fail-closed security policy violation: Local secure endpoint unreachable "
                    f"({decision.target_endpoint}) for sensitive telemetry tool execution. "
                    "Request aborted to prevent cloud data exfiltration."
                )
                active_metrics.record_fail_closed(
                    decision=decision,
                    error_message=fail_msg,
                    client_ip=client_ip,
                )
                return JSONResponse(
                    {
                        "error": {
                            "message": fail_msg,
                            "type": "fail_closed_security_violation",
                            "code": 503,
                            "target_endpoint": decision.target_endpoint,
                            "matched_sensitive_tools": decision.matched_tools,
                        }
                    },
                    status_code=503,
                )

        latency_ms = (time.perf_counter() - start_time) * 1000
        tokens_saved = tokens_in_payload if decision.is_sensitive else 0

        active_metrics.record_routing(
            decision=decision,
            status_code=status_code,
            latency_ms=latency_ms,
            tokens_saved=tokens_saved,
            client_ip=client_ip,
        )

        return JSONResponse(response_data, status_code=status_code)

    async def health(request: Request) -> Response:
        """Handle GET /health probe."""
        return JSONResponse(
            {
                "status": "healthy",
                "service": "ai-gateway-router",
                "routing_strategy": "tool-name-inspection",
                "rules": {
                    "sensitive_tools": sorted(active_engine.sensitive_tools),
                    "local_secure_target": {
                        "model": active_engine.local_model,
                        "endpoint": active_engine.local_url,
                    },
                    "frontier_reasoning_target": {
                        "model": active_engine.cloud_model,
                        "endpoint": active_engine.cloud_url,
                    },
                    "fail_closed_enforced": active_engine.fail_closed,
                    "strip_raw_results": active_engine.strip_raw_results,
                },
                "mock_mode": mock_mode,
            }
        )

    async def metrics_endpoint(request: Request) -> Response:
        """Handle GET /metrics telemetry summary."""
        return JSONResponse(active_metrics.to_dict())

    async def audit_endpoint(request: Request) -> Response:
        """Handle GET /audit audit log retrieval."""
        return JSONResponse(
            {
                "audit_events": active_metrics.audit_events,
                "count": len(active_metrics.audit_events),
            }
        )

    async def reset_metrics_endpoint(request: Request) -> Response:
        """Handle POST /v1/gateway/reset-metrics."""
        active_metrics.reset()
        return JSONResponse({"status": "metrics_reset_success"})

    routes = [
        Route("/v1/chat/completions", chat_completions, methods=["POST"]),
        Route("/health", health, methods=["GET"]),
        Route("/v1/health", health, methods=["GET"]),
        Route("/metrics", metrics_endpoint, methods=["GET"]),
        Route("/v1/metrics", metrics_endpoint, methods=["GET"]),
        Route("/audit", audit_endpoint, methods=["GET"]),
        Route("/v1/audit", audit_endpoint, methods=["GET"]),
        Route("/v1/gateway/reset-metrics", reset_metrics_endpoint, methods=["POST"]),
    ]

    return Starlette(routes=routes)


def parse_args(args: list[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments for AI Gateway Router."""
    parser = argparse.ArgumentParser(
        description="AI Gateway Router with Tool-Triggered Model Swapping (Hybrid-Trust Phase 8)"
    )
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Host IP to bind to (default: 0.0.0.0)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=4000,
        help="Port to bind to (default: 4000)",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=PROJECT_ROOT / "config" / "litellm_config.yaml",
        help="Path to LiteLLM YAML configuration file",
    )
    parser.add_argument(
        "--mock-upstream",
        action="store_true",
        default=True,
        help="Simulate upstream responses locally without requiring external LLM endpoints (default: True)",
    )
    parser.add_argument(
        "--no-mock",
        action="store_false",
        dest="mock_upstream",
        help="Disable mock mode and forward to live HTTP endpoints",
    )
    parser.add_argument(
        "--local-url",
        default=None,
        help="Override local secure model URL (e.g. http://localhost:11434/v1)",
    )
    parser.add_argument(
        "--cloud-url",
        default=None,
        help="Override cloud frontier model URL (e.g. https://api.anthropic.com/v1)",
    )
    return parser.parse_args(args)


def main() -> int:
    """CLI runner for standalone AI Gateway Router."""
    parsed = parse_args(sys.argv[1:])

    engine = parse_litellm_yaml(parsed.config)
    if parsed.local_url:
        engine.local_url = parsed.local_url
    if parsed.cloud_url:
        engine.cloud_url = parsed.cloud_url

    metrics = GatewayMetrics()
    app = create_gateway_app(
        engine=engine,
        mock_mode=parsed.mock_upstream,
        metrics=metrics,
    )

    print("=" * 72)
    print("🔀 AI Gateway Router & Dynamic Model Swapping Proxy")
    print("   Hybrid-Trust Architecture (Phase 8: Network Proxy Governance)")
    print("=" * 72)
    print(f"  • Listening Address:        http://{parsed.host}:{parsed.port}")
    print(f"  • Config File:              {parsed.config}")
    print(f"  • Local Secure Tier:        {engine.local_model} -> {engine.local_url}")
    print(f"  • Frontier Reasoning Tier:  {engine.cloud_model} -> {engine.cloud_url}")
    print(f"  • Monitored Sensitive Tools:{len(engine.sensitive_tools)} tools active")
    print("  • Fail-Closed Guarantee:    ENFORCED (Zero Cloud Egress on Failure)")
    print(
        f"  • Upstream Mode:            {'MOCK SIMULATION (Standalone Demo)' if parsed.mock_upstream else 'LIVE HTTP FORWARDING'}"
    )
    print("=" * 72)
    print("Endpoints:")
    print("  - POST /v1/chat/completions (OpenAI-compatible inference gateway)")
    print("  - GET  /health              (Upstream connectivity & rule status)")
    print("  - GET  /metrics             (Route diversion & token savings)")
    print("  - GET  /audit               (Centralized security audit log)")
    print("-" * 72)

    try:
        import uvicorn

        uvicorn.run(app, host=parsed.host, port=parsed.port, log_level="info")
        return 0
    except ImportError:
        print(
            "Error: 'uvicorn' is required to run the gateway server. Run via `uv run python scripts/gateway_proxy.py`"
        )
        return 1
    except KeyboardInterrupt:
        print("\nShutdown requested by user. Gateway Router stopped.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
