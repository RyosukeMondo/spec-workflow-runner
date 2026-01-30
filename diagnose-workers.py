#!/usr/bin/env python3
"""Diagnose claude-flow worker failures and provide recommendations."""

import json
from pathlib import Path
from typing import Any


def analyze_worker(name: str, stats: dict[str, Any]) -> dict[str, Any]:
    """Analyze a single worker's performance and issues."""
    runs = stats.get("runCount", 0)
    successes = stats.get("successCount", 0)
    failures = stats.get("failureCount", 0)
    avg_duration = stats.get("averageDurationMs", 0)
    is_running = stats.get("isRunning", False)

    success_rate = (successes / runs * 100) if runs > 0 else 0

    # Determine health status
    if success_rate >= 95:
        health = "HEALTHY"
        severity = "info"
    elif success_rate >= 80:
        health = "WARNING"
        severity = "warning"
    elif success_rate >= 50:
        health = "DEGRADED"
        severity = "error"
    else:
        health = "CRITICAL"
        severity = "critical"

    # Identify specific issues
    issues = []
    recommendations = []

    if runs == 0:
        issues.append("Worker has never run")
        recommendations.append("Check if worker is configured correctly")
    elif success_rate == 0:
        issues.append(f"All {runs} runs failed - worker is completely broken")
        recommendations.append("Review worker implementation and dependencies")
        recommendations.append("Check logs in .claude-flow/logs/headless/")
    elif success_rate < 50:
        issues.append(f"High failure rate: {failures}/{runs} failures ({100-success_rate:.1f}%)")
        recommendations.append("Investigate common failure patterns")
        recommendations.append("Consider disabling worker until fixed")

    if avg_duration > 60000:  # > 1 minute
        issues.append(f"Very slow execution: {avg_duration/1000:.1f}s average")
        recommendations.append("Optimize worker logic or increase timeout")
    elif avg_duration > 30000:  # > 30 seconds
        issues.append(f"Slow execution: {avg_duration/1000:.1f}s average")
        recommendations.append("Consider performance improvements")

    if is_running and avg_duration > 0:
        expected_completion = avg_duration / 1000
        issues.append(f"Currently running (expected completion in ~{expected_completion:.0f}s)")

    return {
        "name": name,
        "health": health,
        "severity": severity,
        "success_rate": success_rate,
        "issues": issues,
        "recommendations": recommendations,
        "stats": {
            "runs": runs,
            "successes": successes,
            "failures": failures,
            "avg_duration_sec": avg_duration / 1000,
        }
    }


def diagnose_project(project_path: Path) -> dict[str, Any]:
    """Diagnose all workers in a project."""
    daemon_state = project_path / ".claude-flow" / "daemon-state.json"

    if not daemon_state.exists():
        return {
            "project": project_path.name,
            "claude_flow_enabled": False,
            "message": "No .claude-flow directory found - claude-flow not initialized"
        }

    try:
        with open(daemon_state, encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        return {
            "project": project_path.name,
            "claude_flow_enabled": False,
            "error": str(e)
        }

    workers = data.get("workers", {})
    if not workers:
        return {
            "project": project_path.name,
            "claude_flow_enabled": True,
            "workers_count": 0,
            "message": "No workers configured"
        }

    analyses = [analyze_worker(name, stats) for name, stats in workers.items()]

    # Categorize by severity
    critical = [a for a in analyses if a["severity"] == "critical"]
    errors = [a for a in analyses if a["severity"] == "error"]
    warnings = [a for a in analyses if a["severity"] == "warning"]
    healthy = [a for a in analyses if a["severity"] == "info"]

    return {
        "project": project_path.name,
        "claude_flow_enabled": True,
        "workers_count": len(workers),
        "workers": analyses,
        "summary": {
            "critical": len(critical),
            "errors": len(errors),
            "warnings": len(warnings),
            "healthy": len(healthy),
        },
        "daemon_running": data.get("running", False),
    }


def print_diagnosis(diagnosis: dict[str, Any]):
    """Print diagnosis results in a readable format."""
    print("=" * 100)
    print(f"PROJECT: {diagnosis['project']}")
    print("=" * 100)

    if not diagnosis.get("claude_flow_enabled"):
        print(f"[!] {diagnosis.get('message', diagnosis.get('error', 'Unknown error'))}")
        print()
        return

    print(f"Claude-Flow Status: {'[RUNNING]' if diagnosis.get('daemon_running') else '[STOPPED]'}")
    print(f"Workers: {diagnosis['workers_count']}")
    print()

    summary = diagnosis.get("summary", {})
    if summary.get("critical", 0) > 0:
        print(f"[!] CRITICAL: {summary['critical']} worker(s) completely broken")
    if summary.get("errors", 0) > 0:
        print(f"[!] DEGRADED: {summary['errors']} worker(s) with high failure rate")
    if summary.get("warnings", 0) > 0:
        print(f"[*] WARNING: {summary['warnings']} worker(s) need attention")
    if summary.get("healthy", 0) > 0:
        print(f"[+] HEALTHY: {summary['healthy']} worker(s) operating normally")
    print()

    # Detailed worker reports
    for worker in diagnosis.get("workers", []):
        severity_icons = {
            "critical": "[!!]",
            "error": "[!]",
            "warning": "[*]",
            "info": "[+]",
        }
        icon = severity_icons.get(worker["severity"], "[-]")

        print("-" * 100)
        print(f"{icon} {worker['name'].upper()} - {worker['health']}")
        print("-" * 100)

        stats = worker["stats"]
        print(f"Runs: {stats['runs']} | "
              f"Successes: {stats['successes']} | "
              f"Failures: {stats['failures']} | "
              f"Success Rate: {worker['success_rate']:.1f}%")
        print(f"Average Duration: {stats['avg_duration_sec']:.2f}s")
        print()

        if worker["issues"]:
            print("Issues:")
            for issue in worker["issues"]:
                print(f"  ! {issue}")
            print()

        if worker["recommendations"]:
            print("Recommendations:")
            for rec in worker["recommendations"]:
                print(f"  > {rec}")
            print()


def main():
    """Main diagnostic routine."""
    projects = [
        Path(r"C:\Users\ryosu\repos\kids-guard2"),
        Path(r"C:\Users\ryosu\repos\keyrx"),
    ]

    print("\nCLAUDE-FLOW WORKER DIAGNOSTICS")
    print("=" * 100)
    print()

    for project_path in projects:
        if not project_path.exists():
            print(f"[!] Project not found: {project_path}")
            print()
            continue

        diagnosis = diagnose_project(project_path)
        print_diagnosis(diagnosis)
        print()

    print("=" * 100)
    print("RECOMMENDATIONS SUMMARY")
    print("=" * 100)
    print()
    print("For completely broken workers (0% success):")
    print("  1. Check .claude-flow/logs/headless/ for error logs")
    print("  2. Review worker configuration in CLAUDE.md")
    print("  3. Consider disabling worker until fixed")
    print()
    print("For slow workers (>30s average):")
    print("  1. Review worker logic for optimization opportunities")
    print("  2. Increase timeout settings if needed")
    print("  3. Consider splitting into smaller workers")
    print()
    print("For intermittent failures:")
    print("  1. Check for race conditions or resource contention")
    print("  2. Review error patterns in logs")
    print("  3. Add retry logic with exponential backoff")
    print()


if __name__ == "__main__":
    main()
