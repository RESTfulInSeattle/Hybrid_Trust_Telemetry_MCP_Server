#!/usr/bin/env python3
"""Pre-flight linting and verification script for Hybrid-Trust IDE configurations.

Scans Continue.dev, VS Code, and Cursor configuration files to verify:
1. Strict separation between Cloud Models and sensitive internal MCP servers.
2. Air-gapped profile binding: Internal Telemetry MCP servers must only attach
   to local inference engines (Ollama, llama.cpp, localhost) or enforce REDACTED_CLOUD.
3. Absence of leaked plaintext API keys or improper egress configurations.

Exit Codes:
  0: Configuration compliant with Hybrid-Trust governance policies.
  1: Security policy violation detected (blocking in CI / pre-commit).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

SENSITIVE_SERVER_NAMES = {
    "telemetry-inspector",
    "telemetry_mcp_server",
    "telemetryinspector",
    "telemetry-inspector-secure",
}


def evaluate_config(config_path: Path) -> tuple[bool, list[str], list[str]]:
    """Evaluate an IDE configuration file against Hybrid-Trust policies.

    Args:
        config_path: Path to JSON configuration file.

    Returns:
        Tuple of (is_compliant, list_of_violations, list_of_warnings).
    """
    violations: list[str] = []
    warnings: list[str] = []

    if not config_path.exists():
        return False, [f"Configuration file not found: {config_path}"], []

    try:
        content = config_path.read_text(encoding="utf-8")
        data = json.loads(content)
    except json.JSONDecodeError as e:
        return False, [f"Invalid JSON syntax in {config_path}: {e}"], []

    mcp_servers = data.get("mcpServers", {})
    models = data.get("models", [])

    # Identify if any sensitive telemetry MCP server is configured
    sensitive_mcp_present = False
    for server_key, server_cfg in mcp_servers.items():
        lowered_key = server_key.lower()
        if any(sens in lowered_key for sens in SENSITIVE_SERVER_NAMES):
            sensitive_mcp_present = True
            # Verify environment security mode
            env_vars = server_cfg.get("env", {})
            sec_mode = env_vars.get("SECURITY_MODE", "STRICT_LOCAL")
            dlp_enabled = env_vars.get("TELEMETRY_DLP_ENABLED", "true")

            if dlp_enabled.lower() not in ("true", "1", "yes"):
                violations.append(
                    f"MCP server '{server_key}' disables DLP ('TELEMETRY_DLP_ENABLED'={dlp_enabled}). "
                    "DLP must remain enabled for hybrid-trust governance."
                )

            if sec_mode not in ("STRICT_LOCAL", "REDACTED_CLOUD", "AUDIT_ONLY"):
                violations.append(
                    f"MCP server '{server_key}' has invalid SECURITY_MODE='{sec_mode}'. "
                    "Must be STRICT_LOCAL, REDACTED_CLOUD, or AUDIT_ONLY."
                )

    if not sensitive_mcp_present:
        # If no sensitive server is present, configuration is compliant
        return True, [], []

    # Check model isolation
    has_cloud_model = False
    has_local_model = False

    for model_cfg in models:
        provider = str(model_cfg.get("provider", "")).lower()
        api_base = str(model_cfg.get("apiBase", "")).lower()
        api_key = str(model_cfg.get("apiKey", ""))

        is_local = (
            provider in ("ollama", "llama.cpp", "local", "vllm")
            or "localhost" in api_base
            or "127.0.0.1" in api_base
            or "192.168." in api_base
            or "10." in api_base
        )

        if is_local:
            has_local_model = True
        else:
            has_cloud_model = True
            # Check for hardcoded plaintext API keys
            if api_key and not api_key.startswith("${") and len(api_key) > 15:
                violations.append(
                    f"Plaintext external API key detected in model '{model_cfg.get('title', provider)}'. "
                    "Use environment variable interpolation (e.g. '${ANTHROPIC_API_KEY}')."
                )

    # Hybrid-trust check: If sensitive MCP server is present and cloud models exist in same profile
    if has_cloud_model and not has_local_model:
        violations.append(
            "VIOLATION: Telemetry MCP server is attached to a configuration with ONLY cloud models "
            "and no local zero-egress models. This exposes internal telemetry directly to external APIs. "
            "Remediation: Separate into dual profiles or enforce SECURITY_MODE=REDACTED_CLOUD."
        )
    elif has_cloud_model and has_local_model:
        warnings.append(
            "NOTICE: Both cloud and local models exist in configuration alongside Telemetry MCP server. "
            "Ensure developers switch to the local profile when triaging sensitive or trade-secret incidents."
        )

    is_compliant = len(violations) == 0
    return is_compliant, violations, warnings


def main() -> int:
    """CLI runner for IDE isolation verification."""
    parser = argparse.ArgumentParser(
        description="Verify IDE configuration isolation for Hybrid-Trust MCP architecture",
    )
    parser.add_argument(
        "config_files",
        nargs="*",
        type=Path,
        default=[PROJECT_ROOT / "examples" / "continue_config.json"],
        help="Path to configuration JSON files to evaluate",
    )
    args = parser.parse_args()

    print("=" * 70)
    print("🛡️ Hybrid-Trust IDE Isolation & Pre-Flight Policy Linter")
    print("=" * 70)

    overall_pass = True

    for config_path in args.config_files:
        print(f"Evaluating: {config_path}")
        is_compliant, violations, warnings = evaluate_config(config_path)

        for warn in warnings:
            print(f"  ⚠️  {warn}")

        if not is_compliant:
            overall_pass = False
            for viol in violations:
                print(f"  ❌ {viol}")
        else:
            print("  ✅ Policy check passed: Hybrid-Trust boundaries satisfied.")

    print("-" * 70)
    if overall_pass:
        print("🎉 ALL CONFIGURATIONS COMPLIANT.")
        return 0
    else:
        print(
            "💥 FAILED: Policy violations detected. Resolve issues before deployment."
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
