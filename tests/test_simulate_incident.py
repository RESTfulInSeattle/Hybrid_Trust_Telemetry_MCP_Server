"""Tests for synthetic incident generator script."""

import json
from pathlib import Path

from scripts.simulate_incident import SCENARIOS, generate_event, run_simulation


def test_generate_event_all_scenarios() -> None:
    """Verify that event generation produces valid lines and service mappings across all scenarios."""
    for scenario_name in SCENARIOS:
        service, line = generate_event(scenario_name, output_format="text")
        assert service == SCENARIOS[scenario_name]["service"]
        assert len(line) > 10
        assert f"[{service}]" in line


def test_generate_event_json_format() -> None:
    """Verify that json format emits valid parseable JSON entries with all metadata."""
    service, line = generate_event("redis_timeout", output_format="json")
    assert service == "auth"
    data = json.loads(line)
    assert isinstance(data, dict)
    assert data["service"] == "auth"
    assert data["scenario"] == "redis_timeout"
    assert "timestamp" in data
    assert "level" in data
    assert "trace_id" in data


def test_run_simulation_burst_mode(tmp_path: Path) -> None:
    """Verify run_simulation in burst mode creates files and populates lines."""
    log_dir = tmp_path / "sim_logs"
    run_simulation(
        scenarios=["redis_timeout", "payment_gateway_504"],
        log_dir=log_dir,
        burst_count=6,
        output_format="text",
        quiet=True,
    )

    created_files = list(log_dir.glob("*.log"))
    assert len(created_files) >= 1

    total_lines = 0
    for f in created_files:
        lines = f.read_text(encoding="utf-8").strip().split("\n")
        total_lines += len(lines)

    assert total_lines == 6
