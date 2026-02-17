#!/usr/bin/env python3
"""Commit rescue mechanism for circuit breaker enhancement.

When the circuit breaker detects no commits but uncommitted changes exist,
this script invokes a special "rescue" prompt to commit the work properly.
"""

import subprocess
import sys
from pathlib import Path


def safe_print(text: str):
    """Print text handling Unicode errors."""
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode("ascii", errors="replace").decode("ascii"))


def has_uncommitted_changes() -> tuple[bool, str]:
    """Check if there are uncommitted changes.

    Returns:
        Tuple of (has_changes, status_output)
    """
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    output = result.stdout.strip()
    has_changes = len(output) > 0

    return has_changes, output


def get_changed_files() -> list[str]:
    """Get list of changed/untracked files."""
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    files = []
    for line in result.stdout.strip().split("\n"):
        if line:
            # Format: "?? file.txt" or " M file.txt"
            parts = line.split(maxsplit=1)
            if len(parts) == 2:
                files.append(parts[1])

    return files


def get_diff_summary() -> str:
    """Get summary of changes."""
    # Get diff for tracked files
    result = subprocess.run(
        ["git", "diff", "--stat"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    diff_stat = result.stdout.strip()

    # Get list of untracked files
    result = subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    untracked = result.stdout.strip()

    summary = ""
    if diff_stat:
        summary += "Modified files:\n" + diff_stat + "\n\n"
    if untracked:
        summary += "Untracked files:\n" + untracked + "\n"

    return summary


def run_commit_rescue_prompt(spec_name: str, project_path: Path) -> bool:
    """Run the commit rescue prompt to salvage uncommitted work.

    Args:
        spec_name: Name of the spec being worked on
        project_path: Path to the project

    Returns:
        True if rescue succeeded, False otherwise
    """
    has_changes, status_output = has_uncommitted_changes()

    if not has_changes:
        safe_print("No uncommitted changes detected. Nothing to rescue.")
        return True

    changed_files = get_changed_files()
    diff_summary = get_diff_summary()

    safe_print("\n" + "=" * 80)
    safe_print("COMMIT RESCUE MODE ACTIVATED")
    safe_print("=" * 80)
    safe_print(f"\nDetected {len(changed_files)} changed/untracked files:")
    for f in changed_files[:10]:  # Show first 10
        safe_print(f"  - {f}")
    if len(changed_files) > 10:
        safe_print(f"  ... and {len(changed_files) - 10} more")

    safe_print("\n" + "=" * 80)
    safe_print("Running rescue prompt to commit the work...")
    safe_print("=" * 80 + "\n")

    # Build the rescue prompt
    rescue_prompt = f"""COMMIT RESCUE TASK

## Situation
You completed work on spec '{spec_name}' but forgot to commit the changes.
The circuit breaker was about to trigger, but we're giving you a chance to rescue this work.

## Your Task
Analyze the uncommitted changes and create proper atomic commits.

## Changed Files
{chr(10).join(f"- {f}" for f in changed_files)}

## Diff Summary
{diff_summary}

## Instructions

1. **Analyze changes**: Run `git status` and `git diff` to understand what was implemented

2. **Read tasks.md**: Check `.spec-workflow/specs/{spec_name}/tasks.md` to see which tasks these changes correspond to

3. **Create atomic commits**: Group related changes into logical commits
   - One commit per task if possible
   - Use conventional commit format: "feat(component): description" or "fix(component): description"
   - Example: "feat(security): implement LinuxKeyringManager for API key storage"

4. **Update tasks.md**: Mark completed tasks as "Completed" based on what was actually implemented
   - Be honest: only mark tasks complete if the code is actually there
   - If partially complete, mark as "In Progress"

5. **Commit tasks.md**: After updating, commit it separately:
   - `git add .spec-workflow/specs/{spec_name}/tasks.md`
   - `git commit -m "chore(spec): update task completion status"`

6. **Verify**: Run `git status` to ensure working tree is clean

## CRITICAL RULES

- **DO NOT skip commits** - This is your chance to save the work
- **DO NOT ask questions** - Analyze and commit
- **DO create multiple commits if needed** - One per logical change
- **DO include Co-Authored-By** - Add this to commit messages:
  Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>

## Expected Result

After you finish:
- All changes committed with proper messages
- tasks.md updated and committed
- `git status` shows "working tree clean"
- Circuit breaker reset

START RESCUE NOW.
"""

    # Run Claude with the rescue prompt
    try:
        result = subprocess.run(
            [
                "claude",
                "--print",
                "--model",
                "sonnet",
                "--dangerously-skip-permissions",
                "--output-format",
                "stream-json",
                "--verbose",
                rescue_prompt,
            ],
            cwd=project_path,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=300,  # 5 minute timeout
        )

        safe_print(result.stdout)

        if result.stderr:
            safe_print("\n[STDERR]:")
            safe_print(result.stderr)

        # Check if rescue succeeded
        has_changes_after, _ = has_uncommitted_changes()

        if not has_changes_after:
            safe_print("\n" + "=" * 80)
            safe_print("✅ RESCUE SUCCESSFUL - All changes committed!")
            safe_print("=" * 80)
            return True
        else:
            safe_print("\n" + "=" * 80)
            safe_print("⚠️  RESCUE INCOMPLETE - Some changes remain uncommitted")
            safe_print("=" * 80)
            safe_print("\nRemaining changes:")
            result = subprocess.run(
                ["git", "status", "--short"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            safe_print(result.stdout)
            return False

    except subprocess.TimeoutExpired:
        safe_print("\n" + "=" * 80)
        safe_print("❌ RESCUE TIMEOUT - Claude took too long")
        safe_print("=" * 80)
        return False
    except Exception as e:
        safe_print("\n" + "=" * 80)
        safe_print(f"❌ RESCUE FAILED - Exception: {e}")
        safe_print("=" * 80)
        import traceback

        traceback.print_exc()
        return False


def main():
    """Main entry point for commit rescue."""
    import argparse

    parser = argparse.ArgumentParser(description="Commit rescue for circuit breaker")
    parser.add_argument("spec_name", help="Name of the spec being worked on")
    parser.add_argument(
        "--project-path",
        type=Path,
        default=Path.cwd(),
        help="Path to the project (default: current directory)",
    )

    args = parser.parse_args()

    success = run_commit_rescue_prompt(args.spec_name, args.project_path)

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
