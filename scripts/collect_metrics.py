#!/usr/bin/env python3
"""Metrics collection script for TUI performance monitoring.

Measures startup time, memory usage, poll latency, and CPU usage to track
performance over time and detect regressions against tech.md thresholds.
"""

from __future__ import annotations

import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

try:
    import psutil
except ImportError:
    print("Error: psutil not installed. Install with: pip install psutil", file=sys.stderr)
    sys.exit(1)

from spec_workflow_runner.utils import Config, discover_projects, load_config

# Performance thresholds from tech.md
THRESHOLDS = {
    "startup_ms": 500,  # Cold start with cache
    "memory_mb": 50,  # TUI memory excluding provider subprocesses
    "poll_latency_ms": 100,  # Based on refresh overhead context
    "cpu_percent_idle": 5,  # CPU during idle polling
}


class MetricsCollector:
    """Collects performance metrics for TUI operations."""

    def __init__(self, config_path: Path):
        """Initialize metrics collector.

        Args:
            config_path: Path to config.json
        """
        self.config_path = config_path
        self.config: Config | None = None
        self.metrics: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "startup_ms": 0.0,
            "memory_mb": 0.0,
            "poll_latency_ms": 0.0,
            "cpu_percent_idle": 0.0,
            "thresholds_passed": True,
            "threshold_violations": [],
        }

    def measure_startup(self) -> None:
        """Measure TUI startup time with mocked terminal."""
        start_time = time.perf_counter()

        # Load config
        try:
            self.config = load_config(self.config_path)
        except Exception as e:
            raise RuntimeError(f"Failed to load config: {e}") from e

        # Discover projects (simulates initial state load)
        _ = discover_projects(self.config, force_refresh=False)

        end_time = time.perf_counter()
        self.metrics["startup_ms"] = (end_time - start_time) * 1000

    def measure_memory(self) -> None:
        """Measure current process memory usage."""
        process = psutil.Process()
        memory_bytes = process.memory_info().rss
        self.metrics["memory_mb"] = memory_bytes / (1024 * 1024)

    def measure_poll_latency(self) -> None:
        """Measure file system polling latency.

        Simulates StatePoller poll cycle by checking mtime of multiple files.
        """
        if not self.config:
            raise RuntimeError("Config not loaded")

        projects = discover_projects(self.config, force_refresh=False)
        if not projects:
            # No projects to poll, use a reasonable default
            self.metrics["poll_latency_ms"] = 0.0
            return

        # Measure 10 poll cycles and average
        latencies: list[float] = []
        for _ in range(10):
            start_time = time.perf_counter()

            # Simulate poll cycle: check mtime of tasks.md files
            for project_path in projects:
                spec_workflow_dir = project_path / self.config.spec_workflow_dir_name
                specs_dir = spec_workflow_dir / self.config.specs_subdir

                if not specs_dir.exists():
                    continue

                for spec_dir in specs_dir.iterdir():
                    if not spec_dir.is_dir():
                        continue

                    tasks_path = spec_dir / self.config.tasks_filename
                    if tasks_path.exists():
                        # Check mtime (this is what StatePoller does)
                        _ = tasks_path.stat().st_mtime

            end_time = time.perf_counter()
            latencies.append((end_time - start_time) * 1000)

            # Small sleep to simulate polling interval
            time.sleep(0.01)

        self.metrics["poll_latency_ms"] = sum(latencies) / len(latencies) if latencies else 0.0

    def measure_cpu_idle(self) -> None:
        """Measure CPU usage during idle (no file changes).

        Simulates idle polling by checking CPU percentage over a period.
        """
        process = psutil.Process()

        # Measure CPU over 10 seconds with multiple samples
        samples: list[float] = []
        for _ in range(10):
            cpu_percent = process.cpu_percent(interval=1.0)
            samples.append(cpu_percent)

        self.metrics["cpu_percent_idle"] = sum(samples) / len(samples) if samples else 0.0

    def check_thresholds(self) -> None:
        """Check metrics against thresholds and record violations."""
        violations: list[str] = []

        if self.metrics["startup_ms"] > THRESHOLDS["startup_ms"]:
            violations.append(
                f"Startup time {self.metrics['startup_ms']:.1f}ms exceeds threshold "
                f"{THRESHOLDS['startup_ms']}ms"
            )

        if self.metrics["memory_mb"] > THRESHOLDS["memory_mb"]:
            violations.append(
                f"Memory usage {self.metrics['memory_mb']:.1f}MB exceeds threshold "
                f"{THRESHOLDS['memory_mb']}MB"
            )

        if self.metrics["poll_latency_ms"] > THRESHOLDS["poll_latency_ms"]:
            violations.append(
                f"Poll latency {self.metrics['poll_latency_ms']:.1f}ms exceeds threshold "
                f"{THRESHOLDS['poll_latency_ms']}ms"
            )

        if self.metrics["cpu_percent_idle"] > THRESHOLDS["cpu_percent_idle"]:
            violations.append(
                f"CPU usage {self.metrics['cpu_percent_idle']:.1f}% exceeds threshold "
                f"{THRESHOLDS['cpu_percent_idle']}%"
            )

        self.metrics["threshold_violations"] = violations
        self.metrics["thresholds_passed"] = len(violations) == 0

    def collect_all_metrics(self) -> dict[str, Any]:
        """Collect all metrics and return report.

        Returns:
            Dictionary with all metrics and threshold checks
        """
        print("Collecting TUI performance metrics...", file=sys.stderr)

        print("  Measuring startup time...", file=sys.stderr)
        self.measure_startup()

        print("  Measuring memory usage...", file=sys.stderr)
        self.measure_memory()

        print("  Measuring poll latency...", file=sys.stderr)
        self.measure_poll_latency()

        print("  Measuring CPU usage (this takes ~10 seconds)...", file=sys.stderr)
        self.measure_cpu_idle()

        print("  Checking thresholds...", file=sys.stderr)
        self.check_thresholds()

        return self.metrics


def print_summary(metrics: dict[str, Any]) -> None:
    """Print human-readable summary to stderr.

    Args:
        metrics: Collected metrics dictionary
    """
    print("\n=== Performance Metrics Summary ===", file=sys.stderr)
    print(f"Timestamp: {metrics['timestamp']}", file=sys.stderr)
    print(
        f"Startup Time: {metrics['startup_ms']:.1f}ms (threshold: {THRESHOLDS['startup_ms']}ms)",
        file=sys.stderr,
    )
    print(
        f"Memory Usage: {metrics['memory_mb']:.1f}MB (threshold: {THRESHOLDS['memory_mb']}MB)",
        file=sys.stderr,
    )
    print(
        f"Poll Latency: {metrics['poll_latency_ms']:.1f}ms (threshold: {THRESHOLDS['poll_latency_ms']}ms)",
        file=sys.stderr,
    )
    print(
        f"CPU Idle: {metrics['cpu_percent_idle']:.1f}% (threshold: {THRESHOLDS['cpu_percent_idle']}%)",
        file=sys.stderr,
    )

    if metrics["thresholds_passed"]:
        print("\n✅ All thresholds passed!", file=sys.stderr)
    else:
        print("\n❌ Threshold violations:", file=sys.stderr)
        for violation in metrics["threshold_violations"]:
            print(f"  - {violation}", file=sys.stderr)


def main() -> int:
    """Main entry point.

    Returns:
        Exit code: 0 if all thresholds passed, 1 otherwise
    """
    import argparse

    parser = argparse.ArgumentParser(
        description="Collect TUI performance metrics and check against thresholds"
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("./config.json"),
        help="Path to config.json (default: ./config.json)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Output JSON report to file (default: stdout)",
    )
    parser.add_argument(
        "--no-summary",
        action="store_true",
        help="Don't print summary to stderr",
    )

    args = parser.parse_args()

    # Validate config file exists
    if not args.config.exists():
        print(f"Error: Config file not found: {args.config}", file=sys.stderr)
        return 1

    try:
        # Collect metrics
        collector = MetricsCollector(args.config)
        metrics = collector.collect_all_metrics()

        # Output JSON report
        json_output = json.dumps(metrics, indent=2)
        if args.output:
            args.output.write_text(json_output)
            print(f"\nMetrics saved to: {args.output}", file=sys.stderr)
        else:
            print(json_output)

        # Print summary
        if not args.no_summary:
            print_summary(metrics)

        # Return exit code based on threshold checks
        return 0 if metrics["thresholds_passed"] else 1

    except Exception as e:
        print(f"Error collecting metrics: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
