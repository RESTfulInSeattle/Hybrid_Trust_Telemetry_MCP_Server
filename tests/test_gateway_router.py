"""Tests for AI Gateway Router and Tool-Triggered Model Swapping (Hybrid-Trust Phase 8)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from starlette.testclient import TestClient

from scripts.gateway_proxy import (
    GatewayMetrics,
    ToolRoutingEngine,
    create_gateway_app,
    parse_litellm_yaml,
)


def test_parse_litellm_yaml() -> None:
    """Verify that litellm_config.yaml loads properly with rules and endpoints."""
    config_path = (
        Path(__file__).resolve().parent.parent / "config" / "litellm_config.yaml"
    )
    assert config_path.exists(), "config/litellm_config.yaml must exist"

    engine = parse_litellm_yaml(config_path)
    assert engine.local_model == "local-secure"
    assert engine.cloud_model == "frontier-reasoning"
    assert "localhost" in engine.local_url or "11434" in engine.local_url
    assert engine.fail_closed is True
    assert engine.strip_raw_results is True
    assert "read_recent_errors" in engine.sensitive_tools
    assert "get_system_health" in engine.sensitive_tools
    assert "search_logs_by_pattern" in engine.sensitive_tools


def test_route_non_sensitive_prompt_to_frontier() -> None:
    """Verify that standard coding prompts without telemetry tools route to cloud."""
    engine = ToolRoutingEngine()
    metrics = GatewayMetrics()
    app = create_gateway_app(engine=engine, mock_mode=True, metrics=metrics)
    client = TestClient(app)

    payload = {
        "model": "frontier-reasoning",
        "messages": [
            {
                "role": "user",
                "content": "Can you refactor this quicksort algorithm in Python?",
            }
        ],
    }

    resp = client.post("/v1/chat/completions", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["routing_metadata"]["routed_tier"] == "frontier-reasoning"
    assert data["routing_metadata"]["zero_cloud_egress"] is False
    assert len(data["routing_metadata"]["matched_sensitive_tools"]) == 0

    assert metrics.total_requests == 1
    assert metrics.routed_to_cloud == 1
    assert metrics.routed_to_local == 0


def test_route_sensitive_tool_schema_to_local() -> None:
    """Verify that requests providing sensitive MCP tools in schema route to local model."""
    engine = ToolRoutingEngine()
    metrics = GatewayMetrics()
    app = create_gateway_app(engine=engine, mock_mode=True, metrics=metrics)
    client = TestClient(app)

    payload = {
        "model": "general-reasoning",
        "messages": [
            {
                "role": "user",
                "content": "Investigate why checkout is returning 504 errors.",
            }
        ],
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": "read_recent_errors",
                    "description": "Tail recent service logs",
                },
            }
        ],
    }

    resp = client.post("/v1/chat/completions", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["routing_metadata"]["routed_tier"] == "local-secure"
    assert data["routing_metadata"]["zero_cloud_egress"] is True
    assert "read_recent_errors" in data["routing_metadata"]["matched_sensitive_tools"]

    assert metrics.total_requests == 1
    assert metrics.routed_to_local == 1
    assert metrics.routed_to_cloud == 0
    assert metrics.sensitive_tools_intercepted == 1


def test_route_sensitive_assistant_tool_call_to_local() -> None:
    """Verify that requests where assistant generated a sensitive tool call route to local."""
    engine = ToolRoutingEngine()
    app = create_gateway_app(engine=engine, mock_mode=True)
    client = TestClient(app)

    payload = {
        "messages": [
            {"role": "user", "content": "Triage the database incident"},
            {
                "role": "assistant",
                "content": "I will check database health.",
                "tool_calls": [
                    {
                        "id": "call_123",
                        "type": "function",
                        "function": {"name": "get_system_health", "arguments": "{}"},
                    }
                ],
            },
        ]
    }

    resp = client.post("/v1/chat/completions", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["routing_metadata"]["routed_tier"] == "local-secure"
    assert "get_system_health" in data["routing_metadata"]["matched_sensitive_tools"]


def test_route_sensitive_tool_result_to_local() -> None:
    """Verify that tool response messages containing telemetry route to local tier."""
    engine = ToolRoutingEngine()
    app = create_gateway_app(engine=engine, mock_mode=True)
    client = TestClient(app)

    payload = {
        "messages": [
            {"role": "user", "content": "Search error patterns"},
            {
                "role": "tool",
                "name": "search_logs_by_pattern",
                "content": "ERROR: Connection timeout to Redis cache at 10.0.4.12:6379",
            },
        ]
    }

    resp = client.post("/v1/chat/completions", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["routing_metadata"]["routed_tier"] == "local-secure"


def test_route_embedded_telemetry_signature_to_local() -> None:
    """Verify that raw proprietary traces trigger local routing even if tool name is omitted."""
    engine = ToolRoutingEngine()
    app = create_gateway_app(engine=engine, mock_mode=True)
    client = TestClient(app)

    payload = {
        "messages": [
            {
                "role": "tool",
                "name": "unknown_tool",
                "content": "Desync in proprietary_pricing_model: formula_weights corrupted in order_book_ring_buffer",
            }
        ]
    }

    resp = client.post("/v1/chat/completions", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["routing_metadata"]["routed_tier"] == "local-secure"


def test_fail_closed_security_guarantee() -> None:
    """Verify that when local endpoint is unreachable, sensitive tool execution ABORTS with 503.

    CRITICAL SECURITY INVARIANT: Must NEVER fail-open to cloud providers.
    """
    # Point local url to an invalid/dead port on localhost
    engine = ToolRoutingEngine(local_url="http://127.0.0.1:59999/v1")
    metrics = GatewayMetrics()
    # mock_mode=False exercises real HTTP forwarding and error handling
    app = create_gateway_app(engine=engine, mock_mode=False, metrics=metrics)
    client = TestClient(app)

    payload = {
        "messages": [
            {"role": "user", "content": "Tail the auth logs"},
            {
                "role": "assistant",
                "tool_calls": [
                    {
                        "id": "call_456",
                        "function": {
                            "name": "read_recent_errors",
                            "arguments": json.dumps({"service_name": "auth"}),
                        },
                    }
                ],
            },
        ]
    }

    resp = client.post("/v1/chat/completions", json=payload)
    assert resp.status_code == 503
    err_data = resp.json()
    assert err_data["error"]["type"] == "fail_closed_security_violation"
    assert "Fail-closed security policy violation" in err_data["error"]["message"]
    assert "read_recent_errors" in err_data["error"]["matched_sensitive_tools"]

    # Verify metrics recorded the security violation
    assert metrics.fail_closed_violations == 1
    assert metrics.total_requests == 1
    assert metrics.routed_to_local == 1
    assert metrics.routed_to_cloud == 0
    assert len(metrics.audit_events) == 1
    assert metrics.audit_events[0]["fail_closed"] is True


def test_context_state_pruning() -> None:
    """Verify that prune_context_for_cloud sanitizes multi-line raw logs before cloud resumption."""
    engine = ToolRoutingEngine()
    raw_logs = (
        "[ERROR] Connection timeout to Redis cache at 10.0.4.12:6379\n"
        "[ERROR] Fallback session lookup failed: Redis connection unavailable\n"
        "[CRITICAL] Formula weights [0.42, 0.18, 0.35, 0.05] buffer corrupted"
    )
    messages: list[dict[str, Any]] = [
        {"role": "user", "content": "Please inspect this issue."},
        {"role": "tool", "name": "read_recent_errors", "content": raw_logs},
    ]

    pruned = engine.prune_context_for_cloud(messages)
    assert len(pruned) == 2
    assert "LOCAL_MODEL_SYNTHESIZED_BRIEF" in pruned[1]["content"]
    assert "10.0.4.12" not in pruned[1]["content"]
    assert "Formula weights" not in pruned[1]["content"]


def test_gateway_metrics_and_audit_endpoints() -> None:
    """Verify /metrics and /audit endpoints reflect live traffic and routing state."""
    engine = ToolRoutingEngine()
    metrics = GatewayMetrics()
    app = create_gateway_app(engine=engine, mock_mode=True, metrics=metrics)
    client = TestClient(app)

    # 1. Non-sensitive request
    client.post(
        "/v1/chat/completions",
        json={"messages": [{"role": "user", "content": "Hello"}]},
    )

    # 2. Sensitive request
    client.post(
        "/v1/chat/completions",
        json={
            "messages": [{"role": "user", "content": "Check health"}],
            "tools": [{"function": {"name": "get_system_health"}}],
        },
    )

    # Check metrics endpoint
    metrics_resp = client.get("/metrics")
    assert metrics_resp.status_code == 200
    m_data = metrics_resp.json()
    assert m_data["total_requests"] == 2
    assert m_data["routed_to_local"] == 1
    assert m_data["routed_to_cloud"] == 1
    assert m_data["sensitive_tools_intercepted"] == 1
    assert m_data["fail_closed_violations"] == 0
    assert m_data["active_audit_records"] == 2

    # Check audit endpoint
    audit_resp = client.get("/audit")
    assert audit_resp.status_code == 200
    a_data = audit_resp.json()
    assert a_data["count"] == 2
    assert len(a_data["audit_events"]) == 2
    assert a_data["audit_events"][0]["target_model"] == "frontier-reasoning"
    assert a_data["audit_events"][1]["target_model"] == "local-secure"

    # Check reset endpoint
    reset_resp = client.post("/v1/gateway/reset-metrics")
    assert reset_resp.status_code == 200
    assert reset_resp.json()["status"] == "metrics_reset_success"
    assert metrics.total_requests == 0


def test_gateway_health_endpoint() -> None:
    """Verify /health reports active routing policies and models."""
    engine = ToolRoutingEngine()
    app = create_gateway_app(engine=engine, mock_mode=True)
    client = TestClient(app)

    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "healthy"
    assert data["service"] == "ai-gateway-router"
    assert "read_recent_errors" in data["rules"]["sensitive_tools"]
    assert data["rules"]["local_secure_target"]["model"] == "local-secure"
    assert data["rules"]["frontier_reasoning_target"]["model"] == "frontier-reasoning"
    assert data["rules"]["fail_closed_enforced"] is True


def test_invalid_json_payload() -> None:
    """Verify gateway handles malformed or non-dictionary request payloads gracefully."""
    app = create_gateway_app(mock_mode=True)
    client = TestClient(app)

    # Non-dictionary payload
    resp = client.post(
        "/v1/chat/completions",
        content="not a json",
        headers={"Content-Type": "application/json"},
    )
    assert resp.status_code == 400
    assert "Invalid JSON body" in resp.json()["error"]["message"]
