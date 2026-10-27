"""Configuration module for Telemetry MCP Server.

Provides environment-based configuration for log directory paths, line bounding limits,
server transport options, and hybrid-trust security settings.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def _get_default_log_dir() -> Path:
    return Path(os.getenv("TELEMETRY_LOG_DIR", str(PROJECT_ROOT / "logs"))).resolve()


@dataclass(frozen=True)
class Settings:
    """Server and telemetry operational settings."""

    project_root: Path = PROJECT_ROOT
    log_dir: Path = field(default_factory=_get_default_log_dir)
    default_lines: int = field(
        default_factory=lambda: int(os.getenv("TELEMETRY_DEFAULT_LINES", "50"))
    )
    max_lines: int = field(
        default_factory=lambda: int(os.getenv("TELEMETRY_MAX_LINES", "200"))
    )
    max_line_length: int = field(
        default_factory=lambda: int(os.getenv("TELEMETRY_MAX_LINE_LENGTH", "1000"))
    )
    default_transport: str = field(
        default_factory=lambda: os.getenv("MCP_TRANSPORT", "stdio")
    )
    default_host: str = field(default_factory=lambda: os.getenv("MCP_HOST", "0.0.0.0"))
    default_port: int = field(
        default_factory=lambda: int(os.getenv("MCP_PORT", "8080"))
    )

    # Hybrid-Trust Security Settings
    # Modes: STRICT_LOCAL (trusted, no redaction), REDACTED_CLOUD (enforce DLP redaction), AUDIT_ONLY (log redactions)
    security_mode: str = field(
        default_factory=lambda: os.getenv("SECURITY_MODE", "STRICT_LOCAL").upper()
    )
    dlp_enabled: bool = field(
        default_factory=lambda: (
            os.getenv("TELEMETRY_DLP_ENABLED", "true").lower() in ("true", "1", "yes")
        )
    )
    local_llm_url: str = field(
        default_factory=lambda: os.getenv("LOCAL_LLM_URL", "http://localhost:11434")
    )
    local_llm_model: str = field(
        default_factory=lambda: os.getenv("LOCAL_LLM_MODEL", "qwen2.5-coder:32b")
    )

    def ensure_log_dir_exists(self) -> None:
        """Ensure the target log directory exists on the filesystem."""
        self.log_dir.mkdir(parents=True, exist_ok=True)


settings = Settings()
