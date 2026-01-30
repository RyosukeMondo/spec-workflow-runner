#!/usr/bin/env python3
"""Smart completion check: git commits + continuation probing + commit rescue.

Primary signal: New git commits = work complete
Fallback: Use --continue to probe status and rescue uncommitted work

Usage:
    python smart-completion-check.py --project-path . --baseline-commit abc123
"""

import json
import subprocess
import sys
import time
from pathlib import Path


def safe_print(text: str):
    """Print text handling Unicode errors."""
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode('ascii', errors='replace').decode('ascii'))


def get_new_commits_count(project_path: Path, baseline_commit: str) -> int:
    """Count new commits since baseline.

    Args:
        project_path: Path to project
        baseline_commit: Baseline commit hash

    Returns:
        Number of new commits
    """
    try:
        result = subprocess.run(
            ["git", "rev-list", f"{baseline_commit}..HEAD", "--count"],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=10,
        )

        if result.returncode == 0:
            return int(result.stdout.strip())
        return 0
    except (subprocess.TimeoutExpired, ValueError):
        return 0


def check_uncommitted_changes(project_path: Path) -> dict:
    """Check for uncommitted changes in working tree.

    Returns:
        Dict with:
        {
            "has_changes": bool,
            "changed_files": list[str],
            "staged_files": list[str]
        }
    """
    try:
        # Check for any changes (staged or unstaged)
        status_result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=10,
        )

        if status_result.returncode != 0:
            return {"has_changes": False, "changed_files": [], "staged_files": []}

        lines = status_result.stdout.strip().split('\n')
        changed_files = []
        staged_files = []

        for line in lines:
            if not line:
                continue
            status_code = line[:2]
            file_path = line[3:]

            # Staged changes (first char is not space/?)
            if status_code[0] not in (' ', '?'):
                staged_files.append(file_path)

            # Any change
            if status_code.strip():
                changed_files.append(file_path)

        return {
            "has_changes": bool(changed_files),
            "changed_files": changed_files,
            "staged_files": staged_files,
        }
    except subprocess.TimeoutExpired:
        return {"has_changes": False, "changed_files": [], "staged_files": []}


def probe_session_status(project_path: Path) -> dict:
    """Probe Claude session status using --continue.

    Returns:
        Dict with status, agents_active, tasks_completed, etc.
    """
    probe_prompt = """STATUS PROBE - Respond in JSON only:

Analyze current state and respond with JSON:

```json
{
  "status": "complete|waiting|working",
  "message": "Brief status description",
  "agents_active": true/false,
  "agents_details": "What agents are doing (if any)",
  "tasks_completed": ["Task X.Y completed"],
  "tasks_pending": ["Task X.Y still pending"],
  "commits_made": 0,
  "should_continue": true/false,
  "next_action": "What should happen next"
}
```

Status values:
- "complete": All work done, tasks committed, ready for next iteration
- "waiting": Agents/workers running in background, need to wait
- "working": Currently implementing tasks, need more time

RESPOND WITH ONLY THE JSON OBJECT. No other text."""

    try:
        result = subprocess.run(
            [
                "claude",
                "--print",
                "--model", "sonnet",
                "--dangerously-skip-permissions",
                "--continue",
                probe_prompt,
            ],
            cwd=project_path,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            timeout=60,
        )

        output = result.stdout

        # Extract JSON (might be wrapped in markdown)
        import re
        json_match = re.search(r'```json\s*(\{.*?\})\s*```', output, re.DOTALL)
        if json_match:
            json_str = json_match.group(1)
        else:
            # Try to find raw JSON
            json_match = re.search(r'(\{[^{}]*"status"[^{}]*\})', output, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
            else:
                json_str = output

        status = json.loads(json_str)
        return status

    except subprocess.TimeoutExpired:
        return {
            "status": "error",
            "message": "Probe timeout",
            "should_continue": False,
        }
    except json.JSONDecodeError as e:
        safe_print(f"Error parsing JSON: {e}")
        safe_print(f"Output was: {output[:500]}")
        return {
            "status": "error",
            "message": f"Could not parse JSON response: {e}",
            "should_continue": False,
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Probe failed: {e}",
            "should_continue": False,
        }


def run_commit_rescue(project_path: Path, spec_name: str) -> bool:
    """Run commit rescue to salvage uncommitted work.

    Args:
        project_path: Path to project
        spec_name: Name of spec

    Returns:
        True if rescue successful (commits created), False otherwise
    """
    safe_print("\n" + "=" * 80)
    safe_print("COMMIT RESCUE - Salvaging uncommitted work")
    safe_print("=" * 80)

    try:
        # Check if commit-rescue.py exists
        rescue_script = project_path / "commit-rescue.py"
        if not rescue_script.exists():
            safe_print("Warning: commit-rescue.py not found")
            return False

        result = subprocess.run(
            ["python", str(rescue_script), spec_name],
            cwd=project_path,
            capture_output=False,  # Show output to user
            text=True,
            timeout=300,
        )

        return result.returncode == 0

    except subprocess.TimeoutExpired:
        safe_print("Timeout during commit rescue")
        return False
    except Exception as e:
        safe_print(f"Commit rescue failed: {e}")
        return False


def smart_completion_check(
    project_path: Path,
    spec_name: str,
    baseline_commit: str,
    max_probes: int = 5,
    probe_interval: int = 30,
) -> dict:
    """Smart completion check: commits + probing + rescue.

    Args:
        project_path: Path to project
        spec_name: Name of spec
        baseline_commit: Baseline commit before work started
        max_probes: Maximum probe attempts
        probe_interval: Seconds between probes

    Returns:
        Dict with:
        {
            "complete": bool,
            "new_commits": int,
            "probes_used": int,
            "rescued": bool,
            "status": str
        }
    """
    safe_print("\n" + "=" * 80)
    safe_print("SMART COMPLETION CHECK")
    safe_print("=" * 80)
    safe_print(f"Spec: {spec_name}")
    safe_print(f"Baseline: {baseline_commit}")
    safe_print(f"Max probes: {max_probes}")
    safe_print("=" * 80 + "\n")

    probes_used = 0
    rescued = False

    for probe_num in range(1, max_probes + 1):
        probes_used = probe_num

        safe_print(f"\n{'=' * 80}")
        safe_print(f"CHECK {probe_num}/{max_probes}")
        safe_print(f"{'=' * 80}\n")

        # 1. PRIMARY SIGNAL: Check for new commits
        new_commits = get_new_commits_count(project_path, baseline_commit)
        safe_print(f"New commits: {new_commits}")

        if new_commits > 0:
            safe_print("\n[OK] Work complete - commits detected")
            return {
                "complete": True,
                "new_commits": new_commits,
                "probes_used": probes_used,
                "rescued": rescued,
                "status": "commits_created",
            }

        # 2. FALLBACK: No commits - probe status with --continue
        safe_print("\nNo commits detected - probing status...")
        status = probe_session_status(project_path)

        safe_print("\nProbe response:")
        safe_print(json.dumps(status, indent=2))

        # 3. INTERPRET STATUS
        if status.get("status") == "complete":
            # LLM says complete but no commits - check for uncommitted changes
            changes = check_uncommitted_changes(project_path)

            if changes["has_changes"]:
                safe_print(f"\n[!] Status: complete but {len(changes['changed_files'])} files changed")
                safe_print("Running commit rescue...")

                if run_commit_rescue(project_path, spec_name):
                    rescued = True
                    # Re-check commits after rescue
                    new_commits = get_new_commits_count(project_path, baseline_commit)
                    if new_commits > 0:
                        safe_print("\n[OK] Rescue successful - commits created")
                        return {
                            "complete": True,
                            "new_commits": new_commits,
                            "probes_used": probes_used,
                            "rescued": rescued,
                            "status": "rescued",
                        }
            else:
                # Complete and no changes - genuinely done (maybe nothing to do)
                safe_print("\n[OK] Complete with no changes")
                return {
                    "complete": True,
                    "new_commits": 0,
                    "probes_used": probes_used,
                    "rescued": False,
                    "status": "nothing_to_do",
                }

        elif status.get("status") == "waiting":
            safe_print(f"\n[...] Waiting for agents: {status.get('agents_details', 'unknown')}")

        elif status.get("status") == "working":
            safe_print(f"\n[...] Work in progress: {status.get('message', 'unknown')}")

        elif status.get("status") == "error":
            safe_print(f"\n[!] Probe error: {status.get('message')}")
            return {
                "complete": False,
                "new_commits": new_commits,
                "probes_used": probes_used,
                "rescued": rescued,
                "status": "probe_error",
            }

        # 4. CHECK IF SHOULD CONTINUE
        if not status.get("should_continue", True):
            safe_print("\n[!] LLM says should not continue")
            return {
                "complete": False,
                "new_commits": new_commits,
                "probes_used": probes_used,
                "rescued": rescued,
                "status": "llm_stopped",
            }

        # 5. WAIT BEFORE NEXT PROBE
        if probe_num < max_probes:
            safe_print(f"\nWaiting {probe_interval}s before next check...")
            time.sleep(probe_interval)

    # Max probes reached
    safe_print(f"\n[!] Max probes ({max_probes}) reached")

    # Final attempt: check for uncommitted changes
    changes = check_uncommitted_changes(project_path)
    if changes["has_changes"]:
        safe_print(f"\nFinal rescue attempt ({len(changes['changed_files'])} files changed)...")
        if run_commit_rescue(project_path, spec_name):
            rescued = True
            new_commits = get_new_commits_count(project_path, baseline_commit)
            if new_commits > 0:
                return {
                    "complete": True,
                    "new_commits": new_commits,
                    "probes_used": probes_used,
                    "rescued": rescued,
                    "status": "rescued_final",
                }

    return {
        "complete": False,
        "new_commits": new_commits,
        "probes_used": probes_used,
        "rescued": rescued,
        "status": "timeout",
    }


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Smart completion check: commits + probing + rescue"
    )
    parser.add_argument("spec_name", help="Name of spec")
    parser.add_argument(
        "--project-path",
        type=Path,
        default=Path.cwd(),
        help="Path to project",
    )
    parser.add_argument(
        "--baseline-commit",
        required=True,
        help="Baseline commit hash",
    )
    parser.add_argument(
        "--max-probes",
        type=int,
        default=5,
        help="Maximum probe attempts (default: 5)",
    )
    parser.add_argument(
        "--probe-interval",
        type=int,
        default=30,
        help="Seconds between probes (default: 30)",
    )

    args = parser.parse_args()

    # Run smart completion check
    result = smart_completion_check(
        project_path=args.project_path,
        spec_name=args.spec_name,
        baseline_commit=args.baseline_commit,
        max_probes=args.max_probes,
        probe_interval=args.probe_interval,
    )

    # Display final result
    safe_print("\n" + "=" * 80)
    safe_print("FINAL RESULT")
    safe_print("=" * 80)
    safe_print(f"Complete: {result['complete']}")
    safe_print(f"Status: {result['status']}")
    safe_print(f"New commits: {result['new_commits']}")
    safe_print(f"Probes used: {result['probes_used']}/{args.max_probes}")
    safe_print(f"Rescued: {result['rescued']}")
    safe_print("=" * 80)

    sys.exit(0 if result["complete"] else 1)


if __name__ == "__main__":
    main()
