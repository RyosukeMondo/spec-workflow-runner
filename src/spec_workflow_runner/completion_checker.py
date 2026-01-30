"""Smart completion checker: git commits + continuation probing + commit rescue.

This module provides robust completion detection for Claude sessions by:
1. Checking git commits as primary signal
2. Probing session status with --continue when no commits
3. Running commit rescue to salvage uncommitted work
"""

from __future__ import annotations

import json
import logging
import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class CompletionResult:
    """Result of completion check."""

    complete: bool
    """Whether work is complete."""

    new_commits: int
    """Number of new commits detected."""

    probes_used: int
    """Number of probes performed."""

    rescued: bool
    """Whether commit rescue was performed."""

    status: str
    """Status code: commits_created, rescued, nothing_to_do, timeout, probe_error, llm_stopped."""


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
    except (subprocess.TimeoutExpired, ValueError, Exception) as e:
        logger.warning(f"Failed to count commits: {e}")
        return 0


def check_uncommitted_changes(project_path: Path) -> dict[str, bool | list[str]]:
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
        status_result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=10,
        )

        if status_result.returncode != 0:
            return {"has_changes": False, "changed_files": [], "staged_files": []}

        lines = status_result.stdout.strip().split("\n")
        changed_files = []
        staged_files = []

        for line in lines:
            if not line:
                continue
            status_code = line[:2]
            file_path = line[3:]

            # Staged changes (first char is not space/?)
            if status_code[0] not in (" ", "?"):
                staged_files.append(file_path)

            # Any change
            if status_code.strip():
                changed_files.append(file_path)

        return {
            "has_changes": bool(changed_files),
            "changed_files": changed_files,
            "staged_files": staged_files,
        }
    except (subprocess.TimeoutExpired, Exception) as e:
        logger.warning(f"Failed to check uncommitted changes: {e}")
        return {"has_changes": False, "changed_files": [], "staged_files": []}


def probe_session_status(project_path: Path) -> dict[str, str | bool | int | list[str]]:
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
                "--model",
                "sonnet",
                "--dangerously-skip-permissions",
                "--continue",
                probe_prompt,
            ],
            cwd=project_path,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
        )

        output = result.stdout

        # Extract JSON (might be wrapped in markdown)
        json_match = re.search(r"```json\s*(\{.*?\})\s*```", output, re.DOTALL)
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
        logger.warning("Probe timeout after 60s")
        return {
            "status": "error",
            "message": "Probe timeout",
            "should_continue": False,
        }
    except json.JSONDecodeError as e:
        logger.warning(f"Failed to parse JSON from probe: {e}")
        logger.debug(f"Output was: {output[:500]}")
        return {
            "status": "error",
            "message": f"Could not parse JSON response: {e}",
            "should_continue": False,
        }
    except Exception as e:
        logger.error(f"Probe failed: {e}")
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
    logger.info(f"Running commit rescue for spec '{spec_name}'")

    try:
        # Check if commit-rescue.py exists
        rescue_script = project_path / "commit-rescue.py"
        if not rescue_script.exists():
            logger.warning("commit-rescue.py not found, skipping rescue")
            return False

        result = subprocess.run(
            ["python", str(rescue_script), spec_name],
            cwd=project_path,
            capture_output=True,  # Capture to avoid polluting logs
            text=True,
            timeout=300,
        )

        if result.returncode == 0:
            logger.info("Commit rescue successful")
            return True
        else:
            logger.warning(f"Commit rescue failed with exit code {result.returncode}")
            return False

    except subprocess.TimeoutExpired:
        logger.error("Commit rescue timeout after 300s")
        return False
    except Exception as e:
        logger.error(f"Commit rescue failed: {e}")
        return False


def smart_completion_check(
    project_path: Path,
    spec_name: str,
    baseline_commit: str,
    max_probes: int = 5,
    probe_interval: int = 30,
) -> CompletionResult:
    """Smart completion check: commits + probing + rescue.

    Args:
        project_path: Path to project
        spec_name: Name of spec
        baseline_commit: Baseline commit before work started
        max_probes: Maximum probe attempts
        probe_interval: Seconds between probes

    Returns:
        CompletionResult with status
    """
    logger.info(
        f"Starting smart completion check for '{spec_name}' "
        f"(baseline: {baseline_commit[:8]}, max_probes: {max_probes})"
    )

    probes_used = 0
    rescued = False

    for probe_num in range(1, max_probes + 1):
        probes_used = probe_num

        logger.debug(f"Completion check {probe_num}/{max_probes}")

        # 1. PRIMARY SIGNAL: Check for new commits
        new_commits = get_new_commits_count(project_path, baseline_commit)
        logger.debug(f"New commits: {new_commits}")

        if new_commits > 0:
            logger.info(f"Work complete - {new_commits} commits detected")
            return CompletionResult(
                complete=True,
                new_commits=new_commits,
                probes_used=probes_used,
                rescued=rescued,
                status="commits_created",
            )

        # 2. FALLBACK: No commits - probe status with --continue
        logger.debug("No commits detected - probing status with --continue")
        status = probe_session_status(project_path)

        logger.debug(f"Probe response: {status.get('status')}")

        # 3. INTERPRET STATUS
        if status.get("status") == "complete":
            # LLM says complete but no commits - check for uncommitted changes
            changes = check_uncommitted_changes(project_path)

            if changes["has_changes"]:
                logger.info(
                    f"Status complete but {len(changes['changed_files'])} files changed, "
                    f"running rescue"
                )

                if run_commit_rescue(project_path, spec_name):
                    rescued = True
                    # Re-check commits after rescue
                    new_commits = get_new_commits_count(project_path, baseline_commit)
                    if new_commits > 0:
                        logger.info(f"Rescue successful - {new_commits} commits created")
                        return CompletionResult(
                            complete=True,
                            new_commits=new_commits,
                            probes_used=probes_used,
                            rescued=rescued,
                            status="rescued",
                        )
            else:
                # Complete and no changes - genuinely done (maybe nothing to do)
                logger.info("Complete with no changes")
                return CompletionResult(
                    complete=True,
                    new_commits=0,
                    probes_used=probes_used,
                    rescued=False,
                    status="nothing_to_do",
                )

        elif status.get("status") == "waiting":
            logger.info(f"Waiting for agents: {status.get('agents_details', 'unknown')}")

        elif status.get("status") == "working":
            logger.info(f"Work in progress: {status.get('message', 'unknown')}")

        elif status.get("status") == "error":
            logger.warning(f"Probe error: {status.get('message')}")
            return CompletionResult(
                complete=False,
                new_commits=new_commits,
                probes_used=probes_used,
                rescued=rescued,
                status="probe_error",
            )

        # 4. CHECK IF SHOULD CONTINUE
        if not status.get("should_continue", True):
            logger.info("LLM says should not continue")
            return CompletionResult(
                complete=False,
                new_commits=new_commits,
                probes_used=probes_used,
                rescued=rescued,
                status="llm_stopped",
            )

        # 5. WAIT BEFORE NEXT PROBE
        if probe_num < max_probes:
            logger.debug(f"Waiting {probe_interval}s before next check")
            time.sleep(probe_interval)

    # Max probes reached
    logger.warning(f"Max probes ({max_probes}) reached")

    # Final attempt: check for uncommitted changes
    changes = check_uncommitted_changes(project_path)
    if changes["has_changes"]:
        logger.info(f"Final rescue attempt ({len(changes['changed_files'])} files changed)")
        if run_commit_rescue(project_path, spec_name):
            rescued = True
            new_commits = get_new_commits_count(project_path, baseline_commit)
            if new_commits > 0:
                logger.info(f"Final rescue successful - {new_commits} commits created")
                return CompletionResult(
                    complete=True,
                    new_commits=new_commits,
                    probes_used=probes_used,
                    rescued=rescued,
                    status="rescued_final",
                )

    return CompletionResult(
        complete=False,
        new_commits=new_commits,
        probes_used=probes_used,
        rescued=rescued,
        status="timeout",
    )
