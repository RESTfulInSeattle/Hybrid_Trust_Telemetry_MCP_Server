#!/usr/bin/env python3
"""Synthetic Incident Generator for Telemetry MCP Server.

Continuously injects realistic production traffic and fault scenarios into
service log files for live agent demonstrations, interview showcases,
and automated testing.

Supported Scenarios:
  - redis_timeout: Connection timeouts to Redis cache cascading into auth failures
  - database_deadlock: Postgres transaction lock contention and pool exhaustion
  - payment_gateway_504: Stripe gateway latency spikes and 504 timeouts
  - memory_leak: Heap exhaustion and GC pause spikes
  - inference_saturation: Local LLM engine batch queue latency & KV-cache eviction
  - matching_engine_race: HFT lock-free ring buffer concurrency race condition
  - hipaa_pii_leak: Regulated PANs, SSNs, and patient IDs for DLP testing
  - all: Mixed production traffic across all services
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from telemetry_mcp_server.config import settings

# ---------------------------------------------------------------------------
# Scenario Definitions
# ---------------------------------------------------------------------------

SCENARIOS: dict[str, dict[str, Any]] = {
    "redis_timeout": {
        "service": "auth",
        "description": "Redis connection pool timeout cascading into session lookup failures",
        "events": [
            ("INFO", "Worker pool active worker_id=worker-2 jobs_processed=1420", 0.4),
            (
                "WARN",
                "Redis cluster ping latency elevated latency_ms=890 node=10.0.4.12:6379",
                0.2,
            ),
            (
                "ERROR",
                "Connection timeout to Redis cache at 10.0.4.12:6379 after 5000ms",
                0.15,
            ),
            (
                "ERROR",
                "Fallback session lookup failed: Redis connection unavailable trace_id=tr-auth-9912",
                0.15,
            ),
            (
                "CRITICAL",
                "Session store unreachable: degraded into read-only JWT authentication mode",
                0.1,
            ),
        ],
    },
    "database_deadlock": {
        "service": "database",
        "description": "PostgreSQL transaction deadlock and connection pool exhaustion",
        "events": [
            (
                "INFO",
                "Checkpoint complete: 64 buffers written in 1.4s active_connections=38",
                0.3,
            ),
            (
                "WARN",
                "Slow query detected duration_ms=2840 query=\"SELECT * FROM orders WHERE status = 'pending' FOR UPDATE\"",
                0.25,
            ),
            ("WARN", "Connection pool near capacity: active=49 idle=1 max=50", 0.2),
            (
                "ERROR",
                "deadlock detected: Process 4128 waits for ShareLock on transaction 891244; Process 4135 blocked",
                0.15,
            ),
            (
                "CRITICAL",
                "Transaction aborted due to lock timeout tx_id=tx_db_88491 table=orders",
                0.1,
            ),
        ],
    },
    "payment_gateway_504": {
        "service": "payment",
        "description": "Stripe payment gateway latency degradation and HTTP 504 timeouts",
        "events": [
            (
                "INFO",
                "Processed payment tx_id=tx_pay_102 amount=89.00 currency=USD status=success",
                0.4,
            ),
            (
                "WARN",
                "Gateway response time degraded gateway=stripe latency_ms=3120 tx_id=tx_pay_103",
                0.25,
            ),
            (
                "ERROR",
                "Payment capture failed tx_id=tx_pay_104: 504 Gateway Timeout from api.stripe.com",
                0.2,
            ),
            (
                "ERROR",
                "Circuit breaker opened for provider stripe-us-east failure_rate=42%",
                0.1,
            ),
            (
                "CRITICAL",
                "Webhook delivery backpressure: 184 events queued for retry",
                0.05,
            ),
        ],
    },
    "memory_leak": {
        "service": "auth",
        "description": "Memory pressure, excessive garbage collection pauses, and OOM alerts",
        "events": [
            (
                "INFO",
                "Heap memory utilization nominal: 58% allocated (2.1GB / 4.0GB)",
                0.35,
            ),
            (
                "WARN",
                "Minor GC frequency increased: 12 collections in 60s pause_ms=180",
                0.25,
            ),
            (
                "WARN",
                "Heap memory exceeded threshold: 88% allocated (3.52GB / 4.0GB)",
                0.2,
            ),
            ("ERROR", "Major stop-the-world GC pause exceeded SLA pause_ms=2140", 0.15),
            (
                "CRITICAL",
                "Near OOM hazard: Available heap < 128MB. Triggering heap dump worker-1",
                0.05,
            ),
        ],
    },
    "inference_saturation": {
        "service": "inference",
        "description": "Local AI inference queue saturation and KV-cache memory pressure",
        "events": [
            (
                "INFO",
                "vllm-mlx batch processed tokens_per_sec=78.4 active_requests=4",
                0.35,
            ),
            (
                "WARN",
                "Prompt processing queue backlog size=14 max_capacity=20 latency_ms=1240",
                0.25,
            ),
            (
                "WARN",
                "KV-cache capacity reached 94%: triggering LRU prefix eviction cache_slots=2048",
                0.2,
            ),
            (
                "ERROR",
                "Context window allocation failed: prompt exceeds remaining memory limit req_tokens=8192",
                0.15,
            ),
            (
                "CRITICAL",
                "Apple Silicon Metal GPU unified memory pressure level=critical throttling batching",
                0.05,
            ),
        ],
    },
    "matching_engine_race": {
        "service": "matching_engine",
        "description": "HFT order book lock-free ring buffer concurrency hazard (Hybrid-Trust Quant Use Case)",
        "events": [
            (
                "INFO",
                "Matching engine nominal: book_depth=500 sequence_head=204819 symbol=NVDA",
                0.35,
            ),
            (
                "WARN",
                "Sequence ring buffer barrier latency elevated: 480ns in order_book_ring_buffer",
                0.25,
            ),
            (
                "ERROR",
                "Lock_free_sequence_barrier hazard detected: Thread 3 missed release barrier sequence=204910",
                0.2,
            ),
            (
                "ERROR",
                "Desync in proprietary_pricing_model: formula_weights: [0.38, 0.22, 0.31, 0.09] buffer mismatch",
                0.15,
            ),
            (
                "CRITICAL",
                "Emergency trading pause initiated for symbol=NVDA due to sequence desync",
                0.05,
            ),
        ],
    },
    "hipaa_pii_leak": {
        "service": "payment",
        "description": "Diagnostic telemetry with embedded cardholder data and PII for DLP verification",
        "events": [
            (
                "INFO",
                "Customer checkout initiated email=david.clark@enterprise.com phone=+1-555-839-2041",
                0.3,
            ),
            (
                "WARN",
                "Billing retry on card 4111-2222-3333-4444 cvv: 382 auth_token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.doNotLeakThisSecretKey",
                0.25,
            ),
            (
                "ERROR",
                "Patient copay charge failed mrn=MRN-994821 patient_id=PT-88102 ssn=000-12-3456",
                0.25,
            ),
            (
                "ERROR",
                "AWS S3 invoice upload failed access_key=AKIAIOSFODNN7EXAMPLE secret_key=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
                0.2,
            ),
        ],
    },
}


def generate_event(
    scenario_key: str,
    output_format: str = "text",
) -> tuple[str, str]:
    """Generate a single formatted log line and identify the target service.

    Args:
        scenario_key: Key in SCENARIOS dictionary.
        output_format: 'text', 'json', or 'mixed'.

    Returns:
        Tuple of (service_name, formatted_log_line).
    """
    scenario = SCENARIOS[scenario_key]
    service = scenario["service"]
    events = scenario["events"]

    # Weighted random selection of event
    levels, msgs, weights = zip(*[(e[0], e[1], e[2]) for e in events], strict=False)
    selected_idx = random.choices(range(len(events)), weights=weights, k=1)[0]
    level = levels[selected_idx]
    msg = msgs[selected_idx]

    now = datetime.now(UTC)
    ts_iso = now.strftime("%Y-%m-%dT%H:%M:%S.%fZ")[:-4] + "Z"
    ts_text = now.strftime("%Y-%m-%d %H:%M:%S")

    trace_id = f"tr-{random.randint(100000, 999999)}"

    # Decide format
    use_json = output_format == "json" or (
        output_format == "mixed" and random.random() > 0.5
    )

    if use_json:
        entry = {
            "timestamp": ts_iso,
            "level": level,
            "service": service,
            "trace_id": trace_id,
            "caller": f"{service}.worker:{random.randint(40, 280)}",
            "message": msg,
            "scenario": scenario_key,
        }
        line = json.dumps(entry) + "\n"
    else:
        line = f"[{ts_text}] [{level}] [{service}] trace_id={trace_id} - {msg}\n"

    return service, line


def run_simulation(
    scenarios: list[str],
    log_dir: Path,
    interval_sec: float = 1.0,
    duration_sec: float | None = None,
    burst_count: int | None = None,
    output_format: str = "text",
    quiet: bool = False,
) -> None:
    """Run the synthetic incident log generator.

    Args:
        scenarios: List of scenario names to run.
        log_dir: Directory where log files are written.
        interval_sec: Delay between lines in continuous mode.
        duration_sec: Optional time cap for continuous execution.
        burst_count: Optional count of lines to emit immediately.
        output_format: 'text', 'json', or 'mixed'.
        quiet: If True, suppress console printing.
    """
    log_dir.mkdir(parents=True, exist_ok=True)

    if not quiet:
        print("=" * 70)
        print("🚨 Telemetry MCP Server: Synthetic Incident Generator")
        print("=" * 70)
        print(f"Target Directory : {log_dir}")
        print(f"Active Scenarios : {', '.join(scenarios)}")
        print(f"Log Format       : {output_format}")
        if burst_count:
            print(f"Mode             : Burst ({burst_count} events)")
        else:
            print(
                f"Mode             : Continuous (interval: {interval_sec}s, duration: {duration_sec or 'unlimited'}s)"
            )
        print("-" * 70)

    start_time = time.time()
    generated_count = 0

    try:
        while True:
            if burst_count is not None and generated_count >= burst_count:
                break

            if duration_sec is not None and (time.time() - start_time) >= duration_sec:
                break

            chosen_scenario = random.choice(scenarios)
            service, line = generate_event(chosen_scenario, output_format=output_format)

            target_file = log_dir / f"{service}.log"
            with open(target_file, "a", encoding="utf-8") as f:
                f.write(line)

            generated_count += 1

            if not quiet:
                prefix = f"[{generated_count:04d}] ({chosen_scenario})"
                print(f"{prefix:<32} -> {target_file.name}: {line.strip()[:80]}")

            if burst_count is None:
                time.sleep(interval_sec)

    except KeyboardInterrupt:
        if not quiet:
            print("\n🛑 Simulation interrupted by user.")

    elapsed = round(time.time() - start_time, 2)
    if not quiet:
        print("-" * 70)
        print(
            f"✅ Simulation complete. Emitted {generated_count} events in {elapsed}s."
        )
        print(
            f"Inspect updated logs via Telemetry MCP Server or: tail -n 20 {log_dir}/*.log"
        )
        print("=" * 70)


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Synthetic Incident Generator for Telemetry MCP Server",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Rapidly inject 20 mock incident events for live demo
  python scripts/simulate_incident.py --burst 20 --scenario all

  # Simulate continuous Redis timeouts and auth degradation
  python scripts/simulate_incident.py --scenario redis_timeout --interval 0.5

  # Emit structured JSON logs for HIPAA / PII DLP testing
  python scripts/simulate_incident.py --scenario hipaa_pii_leak --format json --burst 10

  # Simulate HFT quant matching engine race condition
  python scripts/simulate_incident.py --scenario matching_engine_race --burst 15
        """,
    )
    parser.add_argument(
        "--scenario",
        default="all",
        choices=[*list(SCENARIOS.keys()), "all"],
        help="Incident scenario to simulate (default: all)",
    )
    parser.add_argument(
        "--format",
        default="text",
        choices=["text", "json", "mixed"],
        help="Log entry format (default: text)",
    )
    parser.add_argument(
        "--burst",
        type=int,
        default=None,
        help="Emit N events immediately and exit (ideal for demos and tests)",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=1.0,
        help="Interval between generated events in seconds (default: 1.0)",
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=None,
        help="Total duration to run in seconds in continuous mode",
    )
    parser.add_argument(
        "--log-dir",
        type=Path,
        default=settings.log_dir,
        help="Directory to write log files to (defaults to configured settings.log_dir)",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress console log printing",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    selected_scenarios = (
        list(SCENARIOS.keys()) if args.scenario == "all" else [args.scenario]
    )
    run_simulation(
        scenarios=selected_scenarios,
        log_dir=args.log_dir,
        interval_sec=args.interval,
        duration_sec=args.duration,
        burst_count=args.burst,
        output_format=args.format,
        quiet=args.quiet,
    )
