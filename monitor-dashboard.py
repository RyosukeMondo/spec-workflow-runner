#!/usr/bin/env python3
"""Real-time monitoring dashboard for spec-workflow-runner + claude-flow integration."""

import json
import os
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Any


def clear_screen():
    """Clear the terminal screen."""
    os.system('cls' if os.name == 'nt' else 'clear')


def get_git_status(project_path: Path) -> dict[str, Any]:
    """Get git repository status."""
    try:
        # Get current commit
        result = subprocess.run(
            ["git", "-C", str(project_path), "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
        current_commit = result.stdout.strip()

        # Get commits in last hour
        result = subprocess.run(
            ["git", "-C", str(project_path), "log", "--oneline", "--since=1 hour ago"],
            capture_output=True,
            text=True,
            check=True,
        )
        recent_commits = len(result.stdout.strip().split('\n')) if result.stdout.strip() else 0

        # Get uncommitted changes
        result = subprocess.run(
            ["git", "-C", str(project_path), "status", "--short"],
            capture_output=True,
            text=True,
            check=True,
        )
        uncommitted_files = len(result.stdout.strip().split('\n')) if result.stdout.strip() else 0

        return {
            "current_commit": current_commit,
            "recent_commits": recent_commits,
            "uncommitted_files": uncommitted_files,
        }
    except subprocess.CalledProcessError:
        return {"current_commit": "N/A", "recent_commits": 0, "uncommitted_files": 0}


def get_claude_flow_workers(project_path: Path) -> dict[str, dict]:
    """Get claude-flow worker statistics."""
    daemon_state_file = project_path / ".claude-flow" / "daemon-state.json"
    if not daemon_state_file.exists():
        return {}

    try:
        with open(daemon_state_file, encoding="utf-8") as f:
            data = json.load(f)
            return data.get("workers", {})
    except (json.JSONDecodeError, OSError):
        return {}


def get_spec_workflow_stats(project_path: Path) -> dict[str, Any]:
    """Get spec-workflow statistics."""
    spec_dir = project_path / ".spec-workflow" / "specs"
    if not spec_dir.exists():
        return {"total_specs": 0, "completed": 0, "active": 0}

    total_specs = 0
    completed = 0
    active = 0

    for spec_path in spec_dir.iterdir():
        if not spec_path.is_dir():
            continue

        tasks_file = spec_path / "tasks.md"
        if not tasks_file.exists():
            continue

        total_specs += 1

        # Simple completion check - look for task status
        try:
            content = tasks_file.read_text(encoding="utf-8")
            completed_count = content.count("**Status**: Completed")
            pending_count = content.count("**Status**: Pending")
            in_progress_count = content.count("**Status**: In Progress")

            total_tasks = completed_count + pending_count + in_progress_count
            if total_tasks > 0:
                if completed_count == total_tasks:
                    completed += 1
                elif in_progress_count > 0 or pending_count > 0:
                    active += 1
        except OSError:
            continue

    return {
        "total_specs": total_specs,
        "completed": completed,
        "active": active,
        "remaining": total_specs - completed,
    }


def get_active_processes() -> list[dict]:
    """Get active spec-workflow-run processes."""
    try:
        if os.name == 'nt':  # Windows
            result = subprocess.run(
                ["tasklist", "/FI", "IMAGENAME eq spec-workflow-run.exe", "/FO", "CSV"],
                capture_output=True,
                text=True,
            )
            lines = result.stdout.strip().split('\n')[1:]  # Skip header
            return [{"pid": line.split(',')[1].strip('"')} for line in lines if line]
        else:  # Linux/Mac
            result = subprocess.run(
                ["pgrep", "-f", "spec-workflow-run"],
                capture_output=True,
                text=True,
            )
            pids = result.stdout.strip().split('\n')
            return [{"pid": pid} for pid in pids if pid]
    except subprocess.CalledProcessError:
        return []


def format_worker_status(workers: dict[str, dict]) -> str:
    """Format claude-flow worker status for display."""
    if not workers:
        return "  No claude-flow workers detected"

    lines = []
    for name, stats in workers.items():
        status = "[RUNNING]" if stats.get("isRunning") else "[IDLE]   "
        runs = stats.get("runCount", 0)
        success = stats.get("successCount", 0)
        avg_ms = stats.get("averageDurationMs", 0)

        success_rate = (success / runs * 100) if runs > 0 else 0
        health = "✓" if success_rate > 80 else "!" if success_rate > 50 else "✗"

        lines.append(
            f"  {health} {status} {name:15} | "
            f"Runs: {runs:4} | Success: {success_rate:5.1f}% | Avg: {avg_ms:8.1f}ms"
        )

    return '\n'.join(lines)


def display_dashboard(projects: list[Path]):
    """Display the monitoring dashboard."""
    clear_screen()

    print("=" * 100)
    print(" " * 30 + "SPEC-WORKFLOW MONITORING DASHBOARD")
    print("=" * 100)
    print(f"Updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    # Active processes
    processes = get_active_processes()
    print(f"Active Processes: {len(processes)}")
    if processes:
        for proc in processes:
            print(f"  PID: {proc['pid']}")
    print()

    # Per-project status
    for project_path in projects:
        if not project_path.exists():
            continue

        print("-" * 100)
        print(f"PROJECT: {project_path.name}")
        print("-" * 100)

        # Git status
        git_status = get_git_status(project_path)
        print(f"Git: {git_status['current_commit']} | "
              f"Recent commits (1h): {git_status['recent_commits']} | "
              f"Uncommitted: {git_status['uncommitted_files']} files")

        # Spec workflow stats
        spec_stats = get_spec_workflow_stats(project_path)
        if spec_stats["total_specs"] > 0:
            completion_pct = (spec_stats["completed"] / spec_stats["total_specs"]) * 100
            print(f"Specs: {spec_stats['completed']}/{spec_stats['total_specs']} complete "
                  f"({completion_pct:.1f}%) | Active: {spec_stats['active']} | "
                  f"Remaining: {spec_stats['remaining']}")
        else:
            print("Specs: No .spec-workflow directory found")

        # Claude-flow workers
        workers = get_claude_flow_workers(project_path)
        print("\nClaude-Flow Workers:")
        print(format_worker_status(workers))
        print()

    print("=" * 100)
    print("Press Ctrl+C to exit | Refreshing every 5 seconds...")
    print("=" * 100)


def main():
    """Main monitoring loop."""
    # Project paths (Windows)
    projects = [
        Path(r"C:\Users\ryosu\repos\kids-guard2"),
        Path(r"C:\Users\ryosu\repos\keyrx"),
    ]

    print("Starting spec-workflow monitoring dashboard...")
    print("Monitoring projects:")
    for p in projects:
        print(f"  - {p}")
    print("\nInitializing...")
    time.sleep(2)

    try:
        while True:
            display_dashboard(projects)
            time.sleep(5)  # Refresh every 5 seconds
    except KeyboardInterrupt:
        print("\n\nMonitoring stopped.")


if __name__ == "__main__":
    main()
