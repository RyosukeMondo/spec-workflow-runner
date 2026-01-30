#!/usr/bin/env python3
"""Smart continuation loop using --continue to probe for completion.

When Claude launches agents, use --continue to probe status until actual completion.
"""

import subprocess
import time
from pathlib import Path


def safe_print(text: str):
    """Print text handling Unicode errors."""
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode('ascii', errors='replace').decode('ascii'))


def run_continue_session(
    project_path: Path,
    spec_name: str,
    prompt: str,
    max_probes: int = 3,
) -> bool:
    """Run continuation probes until completion or max attempts.

    Args:
        project_path: Path to project
        spec_name: Name of spec
        prompt: Prompt to send with --continue
        max_probes: Maximum number of continuation attempts

    Returns:
        True if work completed, False if max attempts reached
    """
    for attempt in range(1, max_probes + 1):
        safe_print(f"\n{'=' * 80}")
        safe_print(f"CONTINUATION PROBE {attempt}/{max_probes}")
        safe_print(f"{'=' * 80}\n")

        # Run Claude with --continue
        result = subprocess.run(
            [
                "claude",
                "--print",
                "--model", "sonnet",
                "--dangerously-skip-permissions",
                "--output-format", "stream-json",
                "--verbose",
                "--continue",  # KEY: Resume previous session
                prompt,
            ],
            cwd=project_path,
            capture_output=False,  # Show output to user
            text=True,
            encoding='utf-8',
            errors='replace',
        )

        if result.returncode != 0:
            safe_print(f"\n⚠️  Continuation returned non-zero: {result.returncode}")

        # Give a moment for files to be written
        time.sleep(2)

        # Check completion after this probe
        from detect_completion import assess_completion_confidence
        from detect_active_agents import check_agent_activity

        # Get log file (most recent)
        log_dir = project_path / ".spec-workflow" / "specs" / spec_name / "logs"
        if not log_dir.exists():
            log_dir = project_path / "logs" / spec_name

        log_files = sorted(log_dir.glob("*.log"), key=lambda p: p.stat().st_mtime)
        last_log = log_files[-1] if log_files else None

        if not last_log:
            safe_print("Warning: Could not find log file")
            continue

        # Check agents
        activity = check_agent_activity(project_path)

        # Assess completion
        # (Would parse log and check commits here - simplified for example)
        if not activity["has_activity"]:
            safe_print("\n✅ No active agents detected - assuming complete")
            return True

        safe_print(f"\n⏳ Agents still active, waiting before next probe...")
        time.sleep(30)  # Wait 30s between probes

    safe_print(f"\n⚠️  Reached max probes ({max_probes}), stopping")
    return False


def smart_continuation_loop(
    project_path: Path,
    spec_name: str,
    baseline_commit: str,
) -> dict:
    """Smart loop that uses --continue to probe for completion.

    Args:
        project_path: Path to project
        spec_name: Name of spec
        baseline_commit: Commit hash before work started

    Returns:
        Dict with results:
        {
            "completed": bool,
            "new_commits": int,
            "probes_used": int
        }
    """
    max_probes = 5
    probes_used = 0

    safe_print("\n" + "=" * 80)
    safe_print("SMART CONTINUATION LOOP")
    safe_print("=" * 80)
    safe_print(f"Spec: {spec_name}")
    safe_print(f"Max probes: {max_probes}")
    safe_print("=" * 80 + "\n")

    # Initial status check
    prompt = """STATUS CHECK:

Review current state and report:

1. Are background agents/workers still running?
2. Have tasks been completed?
3. Have commits been made?

If agents are working: Report status and continue waiting
If work is complete: Report results and update tasks.md
If work is pending: Continue with next task

Be specific and actionable."""

    for probe_num in range(1, max_probes + 1):
        probes_used = probe_num

        safe_print(f"\n{'=' * 80}")
        safe_print(f"PROBE {probe_num}/{max_probes}")
        safe_print(f"{'=' * 80}\n")

        # Run continuation
        result = subprocess.run(
            [
                "claude",
                "--print",
                "--model", "sonnet",
                "--dangerously-skip-permissions",
                "--output-format", "stream-json",
                "--verbose",
                "--continue",
                prompt,
            ],
            cwd=project_path,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            timeout=300,
        )

        safe_print(result.stdout)

        if result.stderr:
            safe_print(f"\n[STDERR]: {result.stderr}")

        time.sleep(2)

        # Check for new commits
        commit_check = subprocess.run(
            ["git", "rev-list", f"{baseline_commit}..HEAD", "--count"],
            cwd=project_path,
            capture_output=True,
            text=True,
        )

        new_commits = int(commit_check.stdout.strip()) if commit_check.returncode == 0 else 0

        # Check agent activity
        from detect_active_agents import check_agent_activity
        activity = check_agent_activity(project_path)

        safe_print(f"\n{'=' * 80}")
        safe_print(f"PROBE {probe_num} RESULTS")
        safe_print(f"{'=' * 80}")
        safe_print(f"New commits: {new_commits}")
        safe_print(f"Agents active: {activity['has_activity']}")

        # Decide if complete
        if new_commits >= 2 and not activity["has_activity"]:
            safe_print("\n✅ COMPLETE: Commits made and no agents active")
            return {
                "completed": True,
                "new_commits": new_commits,
                "probes_used": probes_used,
            }

        if probe_num >= max_probes:
            safe_print(f"\n⚠️  Max probes reached ({max_probes})")
            return {
                "completed": False,
                "new_commits": new_commits,
                "probes_used": probes_used,
            }

        # Wait before next probe
        safe_print(f"\n⏳ Waiting 30s before next probe...")
        time.sleep(30)

    return {
        "completed": False,
        "new_commits": new_commits,
        "probes_used": probes_used,
    }


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Smart continuation loop")
    parser.add_argument("spec_name", help="Name of spec")
    parser.add_argument(
        "--project-path",
        type=Path,
        default=Path.cwd(),
        help="Path to project",
    )
    parser.add_argument(
        "--baseline-commit",
        help="Baseline commit hash",
    )

    args = parser.parse_args()

    # Get baseline commit if not provided
    if not args.baseline_commit:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=args.project_path,
            capture_output=True,
            text=True,
        )
        args.baseline_commit = result.stdout.strip()

    # Run smart continuation loop
    results = smart_continuation_loop(
        project_path=args.project_path,
        spec_name=args.spec_name,
        baseline_commit=args.baseline_commit,
    )

    safe_print("\n" + "=" * 80)
    safe_print("FINAL RESULTS")
    safe_print("=" * 80)
    safe_print(f"Completed: {results['completed']}")
    safe_print(f"New commits: {results['new_commits']}")
    safe_print(f"Probes used: {results['probes_used']}/{5}")
    safe_print("=" * 80)

    return 0 if results["completed"] else 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
