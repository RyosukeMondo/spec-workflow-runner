#!/usr/bin/env python3
"""Detect active claude-flow agents/workers to prevent false circuit breaker triggers.

When Claude launches agents to work in parallel, the main session ends with no commits.
But the agents are still working! This script detects active agents to inform the
circuit breaker that work is still in progress.
"""

import json
import subprocess
import sys
from pathlib import Path
from typing import Optional


def safe_print(text: str):
    """Print text handling Unicode errors."""
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode('ascii', errors='replace').decode('ascii'))


def check_claude_flow_daemon(project_path: Path) -> bool:
    """Check if claude-flow daemon is running for this project.

    Returns:
        True if daemon is running, False otherwise
    """
    try:
        # Check daemon status
        result = subprocess.run(
            ["npx", "@claude-flow/cli@latest", "daemon", "status"],
            cwd=project_path,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            timeout=10,
        )

        # If daemon status succeeds, it's running
        return result.returncode == 0

    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def get_active_workers(project_path: Path) -> list[dict]:
    """Get list of active claude-flow workers for this project.

    Returns:
        List of active worker info dicts, empty list if none active
    """
    try:
        # Get daemon state
        daemon_state_file = project_path / ".claude-flow" / "daemon-state.json"

        if not daemon_state_file.exists():
            return []

        with open(daemon_state_file, 'r', encoding='utf-8') as f:
            state = json.load(f)

        # Get active workers from state
        active_workers = []
        workers = state.get("workers", {})

        for worker_type, worker_data in workers.items():
            if isinstance(worker_data, dict):
                status = worker_data.get("status", "")
                if status in ("running", "pending", "queued"):
                    active_workers.append({
                        "type": worker_type,
                        "status": status,
                        "started_at": worker_data.get("startedAt"),
                        "last_run": worker_data.get("lastRun"),
                    })

        return active_workers

    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        return []


def get_recent_agent_logs(project_path: Path, minutes: int = 5) -> list[Path]:
    """Get agent log files created in the last N minutes.

    Args:
        project_path: Path to project
        minutes: Look back this many minutes (default: 5)

    Returns:
        List of recent log file paths
    """
    import time

    logs_dir = project_path / ".claude-flow" / "logs" / "headless"

    if not logs_dir.exists():
        return []

    cutoff_time = time.time() - (minutes * 60)
    recent_logs = []

    try:
        for log_file in logs_dir.glob("*_result.log"):
            if log_file.stat().st_mtime > cutoff_time:
                recent_logs.append(log_file)
    except OSError:
        pass

    return recent_logs


def check_task_agent_activity(project_path: Path) -> dict:
    """Check for Task tool agent activity (Claude spawned agents).

    Returns:
        Dict with activity info:
        {
            "has_activity": bool,
            "active_workers": list,
            "recent_logs": list,
            "daemon_running": bool
        }
    """
    daemon_running = check_claude_flow_daemon(project_path)
    active_workers = get_active_workers(project_path)
    recent_logs = get_recent_agent_logs(project_path, minutes=5)

    has_activity = bool(active_workers or recent_logs)

    return {
        "has_activity": has_activity,
        "active_workers": active_workers,
        "recent_logs": [str(log.name) for log in recent_logs],
        "daemon_running": daemon_running,
    }


def wait_for_agents_completion(
    project_path: Path,
    max_wait_seconds: int = 300,
    check_interval: int = 10,
) -> bool:
    """Wait for active agents to complete.

    Args:
        project_path: Path to project
        max_wait_seconds: Maximum time to wait (default: 300s/5min)
        check_interval: Check every N seconds (default: 10s)

    Returns:
        True if agents completed, False if timeout
    """
    import time

    start_time = time.time()
    last_check_time = 0

    safe_print(f"\n{'=' * 80}")
    safe_print("AGENTS DETECTED - Waiting for completion...")
    safe_print(f"{'=' * 80}")

    while True:
        elapsed = time.time() - start_time

        if elapsed > max_wait_seconds:
            safe_print(f"\n⏱️  Timeout after {max_wait_seconds}s")
            return False

        activity = check_task_agent_activity(project_path)

        if not activity["has_activity"]:
            safe_print(f"\n✅ All agents completed (waited {elapsed:.0f}s)")
            return True

        # Print status every check_interval seconds
        if time.time() - last_check_time >= check_interval:
            safe_print(
                f"⏳ Waiting... "
                f"({len(activity['active_workers'])} workers active, "
                f"elapsed: {elapsed:.0f}s)"
            )
            last_check_time = time.time()

        time.sleep(2)  # Check every 2 seconds


def enhanced_circuit_breaker_check(
    no_commit_streak: int,
    project_path: Path,
) -> tuple[int, str]:
    """Enhanced circuit breaker check that detects active agents.

    Args:
        no_commit_streak: Current no-commit streak
        project_path: Path to project

    Returns:
        Tuple of (updated_streak, status_message)
        - If agents active: (0, "agents_active")
        - If no activity: (streak, "no_activity")
    """
    activity = check_task_agent_activity(project_path)

    if activity["has_activity"]:
        safe_print("\n" + "=" * 80)
        safe_print("🔍 AGENT ACTIVITY DETECTED")
        safe_print("=" * 80)

        if activity["active_workers"]:
            safe_print(f"Active workers ({len(activity['active_workers'])}):")
            for worker in activity["active_workers"]:
                safe_print(f"  - {worker['type']}: {worker['status']}")

        if activity["recent_logs"]:
            safe_print(f"\nRecent logs ({len(activity['recent_logs'])}):")
            for log_name in activity["recent_logs"][:5]:
                safe_print(f"  - {log_name}")

        safe_print("\n✅ Agents are working - NOT incrementing circuit breaker")
        safe_print("=" * 80)

        return 0, "agents_active"
    else:
        return no_commit_streak, "no_activity"


def main():
    """Main entry point for agent detection."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Detect active claude-flow agents/workers"
    )
    parser.add_argument(
        "--project-path",
        type=Path,
        default=Path.cwd(),
        help="Path to project (default: current directory)",
    )
    parser.add_argument(
        "--wait",
        action="store_true",
        help="Wait for agents to complete",
    )
    parser.add_argument(
        "--wait-timeout",
        type=int,
        default=300,
        help="Maximum wait time in seconds (default: 300)",
    )

    args = parser.parse_args()

    # Check for activity
    activity = check_task_agent_activity(args.project_path)

    safe_print(f"\n{'=' * 80}")
    safe_print("AGENT ACTIVITY CHECK")
    safe_print(f"{'=' * 80}")
    safe_print(f"Project: {args.project_path}")
    safe_print(f"Daemon running: {activity['daemon_running']}")
    safe_print(f"Active workers: {len(activity['active_workers'])}")
    safe_print(f"Recent logs: {len(activity['recent_logs'])}")
    safe_print(f"Has activity: {activity['has_activity']}")

    if activity["active_workers"]:
        safe_print("\nActive workers:")
        for worker in activity["active_workers"]:
            safe_print(f"  - {worker['type']}: {worker['status']}")

    if activity["recent_logs"]:
        safe_print("\nRecent agent logs:")
        for log_name in activity["recent_logs"][:10]:
            safe_print(f"  - {log_name}")

    # Wait if requested
    if args.wait and activity["has_activity"]:
        success = wait_for_agents_completion(
            args.project_path,
            max_wait_seconds=args.wait_timeout,
        )
        sys.exit(0 if success else 1)

    # Exit with status
    sys.exit(0 if activity["has_activity"] else 1)


if __name__ == "__main__":
    main()
