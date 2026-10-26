"""Tests for system health telemetry probes."""

import json

from telemetry_mcp_server.tools.health import get_system_health


def test_get_system_health_structure() -> None:
    """Verify that get_system_health returns valid JSON with all required operational fields."""
    raw_response = get_system_health()
    data = json.loads(raw_response)

    assert isinstance(data, dict)
    assert data["status"] in ("healthy", "degraded", "unhealthy")
    assert isinstance(data["active_alerts"], int)
    assert isinstance(data["database_latency_ms"], (int, float))
    assert isinstance(data["active_connections"], int)
    assert "inference_gateway" in data
    assert data["inference_gateway"]["proxy"] == "litellm"
    assert data["inference_gateway"]["engine"] == "vllm-mlx"
