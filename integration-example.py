#!/usr/bin/env python3
"""Example integration of commit rescue into existing workflow.

This shows how to enhance your run_tasks.py or monitoring script
with the intelligent circuit breaker.
"""

import subprocess
from pathlib import Path


def has_uncommitted_changes(project_path: Path) -> bool:
    """Check if there are uncommitted changes."""
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=project_path,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return len(result.stdout.strip()) > 0


def run_commit_rescue(spec_name: str, project_path: Path) -> bool:
    """Run commit rescue script.

    Returns:
        True if rescue succeeded, False otherwise
    """
    rescue_script = Path(__file__).parent / "commit-rescue.py"

    result = subprocess.run(
        ["python", str(rescue_script), spec_name, "--project-path", str(project_path)],
        capture_output=False,  # Show output to user
    )

    return result.returncode == 0


# ============================================================================
# INTEGRATION INTO YOUR EXISTING WORKFLOW
# ============================================================================


def enhanced_circuit_breaker_check(
    no_commit_streak: int,
    no_commit_limit: int,
    project_path: Path,
    spec_name: str,
    enable_rescue: bool = True,
) -> int:
    """Enhanced circuit breaker with commit rescue.

    Args:
        no_commit_streak: Current streak of iterations without commits
        no_commit_limit: Maximum allowed streak (usually 3)
        project_path: Path to the project
        spec_name: Name of spec being worked on
        enable_rescue: Whether to attempt rescue (default: True)

    Returns:
        Updated no_commit_streak (reset to 0 if rescue successful)

    Raises:
        Exception: If circuit breaker triggers after failed rescue
    """

    if no_commit_streak < no_commit_limit:
        # Not at limit yet, just return current streak
        return no_commit_streak

    # Circuit breaker limit reached
    print(f"\n{'=' * 80}")
    print(f"⚠️  CIRCUIT BREAKER: {no_commit_streak}/{no_commit_limit} iterations with no commits")
    print(f"{'=' * 80}\n")

    if not enable_rescue:
        # Rescue disabled, trigger immediately
        raise Exception(
            f"Circuit breaker: reached consecutive no-commit limit. "
            f"No commits for {no_commit_streak} iterations."
        )

    # Check for uncommitted changes
    if has_uncommitted_changes(project_path):
        print("🔍 Uncommitted changes detected!")
        print("🚑 Activating COMMIT RESCUE mode...\n")

        # Attempt rescue
        rescue_success = run_commit_rescue(spec_name, project_path)

        if rescue_success:
            print("\n" + "=" * 80)
            print("✅ RESCUE SUCCESSFUL - Work committed, circuit breaker RESET")
            print("=" * 80)
            return 0  # Reset streak
        else:
            print("\n" + "=" * 80)
            print("❌ RESCUE FAILED - Could not commit work")
            print("=" * 80)
            raise Exception("Circuit breaker: rescue attempt failed")
    else:
        # No uncommitted changes - genuine stall
        print("No uncommitted changes found - genuine stall detected")
        raise Exception(
            f"Circuit breaker: No progress for {no_commit_streak} iterations. "
            f"No uncommitted changes to rescue."
        )


# ============================================================================
# EXAMPLE USAGE IN YOUR MONITORING LOOP
# ============================================================================


def example_monitoring_loop():
    """Example of how to integrate into your existing monitoring loop."""

    # Your existing config
    NO_COMMIT_LIMIT = 3
    project_path = Path.cwd()
    spec_name = "security-fixes"

    # Monitoring loop
    no_commit_streak = 0
    iteration = 0

    while iteration < 10:
        iteration += 1
        print(f"\n[Iteration {iteration}]")

        # Run Claude (your existing code)
        # ... run_claude_session(spec_name) ...

        # Check for new commits (your existing code)
        # ... get current commit hash ...

        # Simulate: no commit detected
        new_commit_detected = False  # This would be your actual check

        if not new_commit_detected:
            no_commit_streak += 1
            print(f"[!]  No commit detected. Streak: {no_commit_streak}/{NO_COMMIT_LIMIT}")

            try:
                # **NEW**: Enhanced circuit breaker with rescue
                no_commit_streak = enhanced_circuit_breaker_check(
                    no_commit_streak=no_commit_streak,
                    no_commit_limit=NO_COMMIT_LIMIT,
                    project_path=project_path,
                    spec_name=spec_name,
                    enable_rescue=True,  # Enable rescue
                )

                if no_commit_streak == 0:
                    print("Continuing with next iteration after successful rescue")
                    continue

            except Exception as e:
                print(f"\n❌ Circuit breaker triggered: {e}")
                print("Aborting workflow.")
                break
        else:
            # Commit detected - reset streak
            no_commit_streak = 0
            print("✅ New commit detected - streak reset")


# ============================================================================
# QUICK INTEGRATION SNIPPET FOR YOUR CODE
# ============================================================================

"""
# In your existing run_tasks.py or monitoring script, replace this:

if no_commit_streak >= NO_COMMIT_LIMIT:
    raise Exception("Circuit breaker triggered")

# With this:

if no_commit_streak >= NO_COMMIT_LIMIT:
    # Check for uncommitted changes
    if has_uncommitted_changes(project_path):
        print("Uncommitted changes detected - attempting rescue...")
        if run_commit_rescue(spec_name, project_path):
            no_commit_streak = 0  # Reset on success
            continue
    raise Exception("Circuit breaker triggered")
"""

if __name__ == "__main__":
    print("This is an integration example. See code for usage.")
    print("\nKey functions:")
    print("  - has_uncommitted_changes(project_path)")
    print("  - run_commit_rescue(spec_name, project_path)")
    print("  - enhanced_circuit_breaker_check(...)")
    print("\nSee inline comments for integration into your workflow.")
