"""Configuration module for Telemetry MCP Server.

Provides environment-based configuration for log directory paths, line bounding limits,
and server transport options.
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

    def ensure_log_dir_exists(self) -> None:
        """Ensure the target log directory exists on the filesystem."""
        self.log_dir.mkdir(parents=True, exist_ok=True)


settings = Settings()
