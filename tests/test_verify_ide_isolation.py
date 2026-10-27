"""Tests for IDE configuration isolation verification script."""

import json
from pathlib import Path

from scripts.verify_ide_isolation import evaluate_config


def test_evaluate_continue_config_compliant(tmp_path: Path) -> None:
    """Verify that a properly configured dual-profile configuration passes compliance."""
    config_file = tmp_path / "config.json"
    config_file.write_text(
        json.dumps(
            {
                "models": [
                    {
                        "title": "Local Secure Model",
                        "provider": "ollama",
                        "model": "qwen2.5-coder:32b",
                        "apiBase": "http://localhost:11434",
                    }
                ],
                "mcpServers": {
                    "telemetry-inspector-secure": {
                        "command": "uv",
                        "args": ["run", "python", "-m", "telemetry_mcp_server.server"],
                        "env": {
                            "SECURITY_MODE": "STRICT_LOCAL",
                            "TELEMETRY_DLP_ENABLED": "true",
                        },
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    is_compliant, violations, _warnings = evaluate_config(config_file)
    assert is_compliant is True
    assert len(violations) == 0


def test_evaluate_config_cloud_only_violation(tmp_path: Path) -> None:
    """Verify that attaching Telemetry MCP server to a cloud-only profile triggers a violation."""
    config_file = tmp_path / "unsafe_config.json"
    config_file.write_text(
        json.dumps(
            {
                "models": [
                    {
                        "title": "Cloud Only Model",
                        "provider": "anthropic",
                        "model": "claude-3-5-sonnet",
                        "apiKey": "${ANTHROPIC_API_KEY}",
                    }
                ],
                "mcpServers": {
                    "telemetry-inspector": {
                        "command": "uv",
                        "args": ["run", "python", "-m", "telemetry_mcp_server.server"],
                        "env": {"SECURITY_MODE": "STRICT_LOCAL"},
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    is_compliant, violations, _warnings = evaluate_config(config_file)
    assert is_compliant is False
    assert any("VIOLATION" in v for v in violations)


def test_evaluate_config_dlp_disabled_violation(tmp_path: Path) -> None:
    """Verify that disabling DLP on sensitive MCP server triggers a violation."""
    config_file = tmp_path / "no_dlp_config.json"
    config_file.write_text(
        json.dumps(
            {
                "models": [
                    {
                        "title": "Local Secure Model",
                        "provider": "ollama",
                        "apiBase": "http://localhost:11434",
                    }
                ],
                "mcpServers": {
                    "telemetry-inspector": {
                        "command": "uv",
                        "args": ["run"],
                        "env": {"TELEMETRY_DLP_ENABLED": "false"},
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    is_compliant, violations, _warnings = evaluate_config(config_file)
    assert is_compliant is False
    assert any("disables DLP" in v for v in violations)
