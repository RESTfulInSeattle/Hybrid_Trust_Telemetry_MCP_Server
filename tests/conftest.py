"""Pytest fixtures and test environment configuration."""

from pathlib import Path

import pytest


@pytest.fixture
def mock_log_dir(tmp_path: Path) -> Path:
    """Create a temporary log directory with mock service log files."""
    log_dir = tmp_path / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    auth_log = log_dir / "auth.log"
    auth_log.write_text(
        "[INFO] Auth service started\n"
        "[WARN] High latency detected on login endpoint\n"
        "[ERROR] Connection timeout to Redis cache\n"
        "[ERROR] Token validation failed user_id=123\n",
        encoding="utf-8",
    )

    payment_log = log_dir / "payment.log"
    payment_log.write_text(
        "[INFO] Payment processor started\n"
        "[ERROR] Stripe webhook timeout tx=9988\n"
        "[ERROR] Gateway timeout 504\n",
        encoding="utf-8",
    )

    database_log = log_dir / "database.log"
    database_log.write_text(
        "[INFO] DB pool initialized\n[WARN] Slow query detected\n",
        encoding="utf-8",
    )

    return log_dir
