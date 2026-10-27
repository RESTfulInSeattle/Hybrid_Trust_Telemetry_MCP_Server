"""Pytest fixtures and test environment configuration."""

from pathlib import Path

import pytest

from telemetry_mcp_server.dlp import audit_metrics


@pytest.fixture(autouse=True)
def reset_audit_metrics() -> None:
    """Reset DLP audit metrics before each test."""
    audit_metrics.reset()


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


@pytest.fixture
def mock_structured_log_dir(tmp_path: Path) -> Path:
    """Create a temporary log directory containing structured JSON and timestamped logs."""
    log_dir = tmp_path / "structured_logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    auth_log = log_dir / "auth.log"
    auth_log.write_text(
        '{"timestamp": "2026-10-25T18:00:00Z", "level": "INFO", "service": "auth", "message": "Auth service initialized"}\n'
        '{"timestamp": "2026-10-25T18:15:30Z", "level": "WARN", "service": "auth", "message": "High latency on token endpoint"}\n'
        '{"timestamp": "2026-10-25T18:30:00Z", "level": "ERROR", "service": "auth", "message": "Redis connection timeout at 10.0.4.12:6379"}\n'
        '{"timestamp": "2026-10-25T18:45:00Z", "level": "CRITICAL", "service": "auth", "message": "Session store completely unavailable"}\n',
        encoding="utf-8",
    )

    payment_log = log_dir / "payment.log"
    payment_log.write_text(
        "[2026-10-25 18:00:00] [INFO] Payment processor worker-1 started\n"
        "[2026-10-25 18:20:00] [WARN] Gateway latency degraded to 920ms\n"
        "[2026-10-25 18:40:00] [ERROR] Payment capture failed: 504 Gateway Timeout tx_id=tx_9921\n",
        encoding="utf-8",
    )

    hft_log = log_dir / "matching_engine.log"
    hft_log.write_text(
        "[2026-10-25 18:00:00] [INFO] Matching engine initialized book_depth=500\n"
        "[2026-10-25 18:30:00] [WARN] High latency in order_book_ring_buffer\n"
        "[2026-10-25 18:45:00] [ERROR] Lock_free_sequence_barrier hazard detected on Thread 2\n"
        "[2026-10-25 18:50:00] [ERROR] Corrupted formula_weights: [0.1, 0.4, 0.5]\n",
        encoding="utf-8",
    )

    return log_dir
