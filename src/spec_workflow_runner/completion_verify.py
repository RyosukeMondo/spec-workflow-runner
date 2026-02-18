"""Post-session verification script.

Verifies implementation completeness, updates tasks.md, and makes git commits.
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from .progress_count import CHECKBOX_PATTERN
from .subprocess_helpers import run_command


@dataclass(frozen=True)
class AcceptanceCriteria:
    """Acceptance criteria for a task."""

    criteria: list[str]
    checked: list[bool]

    @property
    def all_met(self) -> bool:
        """Check if all criteria are met."""
        return all(self.checked)

    @property
    def completion_rate(self) -> float:
        """Calculate completion rate."""
        if not self.criteria:
            return 0.0
        return sum(self.checked) / len(self.criteria) * 100


@dataclass(frozen=True)
class TaskVerification:
    """Verification result for a single task."""

    task_id: str
    title: str
    current_status: str
    files_modified: list[str]
    acceptance: AcceptanceCriteria | None
    verification_passed: bool
    issues: list[str]

    @property
    def should_mark_complete(self) -> bool:
        """Determine if task should be marked complete."""
        if not self.verification_passed:
            return False
        if self.acceptance and not self.acceptance.all_met:
            return False
        return True


@dataclass(frozen=True)
class VerificationResult:
    """Overall verification result."""

    spec_name: str
    tasks_verified: int
    tasks_completed: int
    tasks_incomplete: int
    verifications: list[TaskVerification]
    commits_made: list[str]

    def summary(self) -> str:
        """Generate summary message."""
        return (
            f"✅ {self.tasks_completed} tasks completed, "
            f"⏸️  {self.tasks_incomplete} still in progress"
        )


def extract_acceptance_criteria(task_text: str) -> AcceptanceCriteria | None:
    """Extract acceptance criteria checkboxes from task.

    Looks for:
    - **Acceptance**: or - **Acceptance Criteria**:
      - [ ] Criterion 1
      - [x] Criterion 2
    """
    # Find acceptance section
    acceptance_match = re.search(
        r"-\s+\*\*Acceptance(?:\s+Criteria)?\*\*:\s*\n((?:\s+-\s+\[[ x]\].*\n?)+)",
        task_text,
        re.MULTILINE,
    )

    if not acceptance_match:
        return None

    acceptance_section = acceptance_match.group(1)

    # Extract checkboxes
    criteria = []
    checked = []

    checkbox_pattern = re.compile(r"^\s+-\s+\[(?P<state>[ x])\]\s+(?P<text>.+)$", re.MULTILINE)

    for match in checkbox_pattern.finditer(acceptance_section):
        criteria.append(match.group("text").strip())
        checked.append(match.group("state") == "x")

    if not criteria:
        return None

    return AcceptanceCriteria(criteria=criteria, checked=checked)


def get_modified_files(project_path: Path, since_ref: str = "HEAD~1") -> list[str]:
    """Get list of files modified since reference commit.

    Args:
        project_path: Path to project root
        since_ref: Git reference to compare against

    Returns:
        List of modified file paths
    """
    try:
        # Get staged and unstaged changes
        result = run_command(
            ["git", "diff", "--name-only", "HEAD"],
            cwd=project_path,
            check=False,
        )

        if result.returncode != 0:
            return []

        files = [f.strip() for f in result.stdout.splitlines() if f.strip()]
        return files

    except Exception:
        return []


def check_files_exist(project_path: Path, files: list[str]) -> tuple[bool, list[str]]:
    """Check if required files exist.

    Args:
        project_path: Path to project root
        files: List of file paths to check

    Returns:
        Tuple of (all_exist, missing_files)
    """
    missing = []

    for file_path in files:
        full_path = project_path / file_path
        # Skip test files from strict checking
        if "test/" not in file_path and "_test." not in file_path:
            if not full_path.exists():
                missing.append(file_path)

    return len(missing) == 0, missing


def verify_in_progress_tasks(
    tasks_md_path: Path,
    project_path: Path,
) -> list[TaskVerification]:
    """Verify all in-progress tasks for completion.

    Args:
        tasks_md_path: Path to tasks.md
        project_path: Path to project root

    Returns:
        List of TaskVerification results
    """
    if not tasks_md_path.exists():
        return []

    content = tasks_md_path.read_text(encoding="utf-8")

    # Extract Tasks section
    tasks_section_start = content.find("## Tasks")
    if tasks_section_start == -1:
        task_text = content
    else:
        task_text_start = tasks_section_start + len("## Tasks")
        next_section = content.find("\n## ", task_text_start)
        task_text = (
            content[tasks_section_start:next_section]
            if next_section != -1
            else content[tasks_section_start:]
        )

    verifications = []
    modified_files = get_modified_files(project_path)

    # Find all checkbox tasks that are in-progress
    for match in CHECKBOX_PATTERN.finditer(task_text):
        state = match.group("state")
        title = match.group("title").strip()

        # Only verify in-progress tasks
        if state != "-":
            continue

        # Extract task section
        start_pos = match.start()
        next_task = CHECKBOX_PATTERN.search(task_text, match.end())
        end_pos = next_task.start() if next_task else len(task_text)
        task_section = task_text[start_pos:end_pos]

        # Extract acceptance criteria
        acceptance = extract_acceptance_criteria(task_section)

        # Extract required files
        files = extract_files_from_task_section(task_section)

        # Verify implementation
        issues = []
        verification_passed = True

        # Check if files were created/modified
        if files:
            files_exist, missing = check_files_exist(project_path, files)
            if not files_exist:
                issues.append(f"Missing files: {', '.join(missing)}")
                verification_passed = False

            # Check if any task files were modified in this session
            task_files_modified = [f for f in files if f in modified_files]
            if not task_files_modified and not files_exist:
                issues.append("No files modified for this task")
                verification_passed = False
        else:
            # No files specified - check if any files were modified
            if not modified_files:
                issues.append("No files modified and no files specified in task")
                verification_passed = False

        # Check acceptance criteria
        if acceptance and not acceptance.all_met:
            issues.append(
                f"Acceptance criteria not fully met: "
                f"{sum(acceptance.checked)}/{len(acceptance.criteria)} complete"
            )
            verification_passed = False

        verifications.append(
            TaskVerification(
                task_id=title.split(".")[0] if "." in title else title[:10],
                title=title,
                current_status="in_progress",
                files_modified=(
                    [f for f in files if f in modified_files] if files else modified_files
                ),
                acceptance=acceptance,
                verification_passed=verification_passed,
                issues=issues,
            )
        )

    return verifications


def extract_files_from_task_section(task_text: str) -> list[str]:
    """Extract file paths from task section."""
    files = []

    # Pattern: - **File**: path or - **Files**:
    file_field = re.findall(r"-\s+\*\*Files?\*\*:\s*(.+)", task_text)
    for match in file_field:
        paths = re.split(r"[,\n]", match)
        for path in paths:
            path = path.strip().strip("`").strip("(").strip(")").strip()
            if path and not path.startswith("-"):
                files.append(path)

    # Pattern: `path/to/file.ext` in backticks
    backtick_files = re.findall(r"`([^`]+\.\w+)`", task_text)
    files.extend(backtick_files)

    # Deduplicate
    return list(dict.fromkeys(files))


def update_verified_tasks(tasks_md_path: Path, verified_tasks: list[TaskVerification]) -> int:
    """Update tasks.md to mark verified tasks as complete.

    Args:
        tasks_md_path: Path to tasks.md
        verified_tasks: List of verified tasks

    Returns:
        Number of tasks marked complete
    """
    if not verified_tasks:
        return 0

    content = tasks_md_path.read_text(encoding="utf-8")
    completed_count = 0

    for task in verified_tasks:
        if not task.should_mark_complete:
            continue

        # Find and replace [-] with [x] for this task
        pattern = re.compile(
            rf"^(\s*-\s+)\[-\](\s+.*{re.escape(task.title[:30])}.*?)$",
            re.MULTILINE,
        )

        match = pattern.search(content)
        if match:
            new_content = pattern.sub(r"\1[x]\2", content, count=1)
            if new_content != content:
                content = new_content
                completed_count += 1

    if completed_count > 0:
        tasks_md_path.write_text(content, encoding="utf-8")

    return completed_count


def make_commit_for_verified_work(
    project_path: Path,
    spec_name: str,
    verified_tasks: list[TaskVerification],
) -> list[str]:
    """Make git commits for verified work.

    Args:
        project_path: Path to project root
        spec_name: Name of spec
        verified_tasks: List of verified tasks

    Returns:
        List of commit SHAs created
    """
    commits = []

    # Group verified tasks by completion status
    completed_tasks = [t for t in verified_tasks if t.should_mark_complete]

    if not completed_tasks:
        return commits

    # Stage all modified files
    try:
        run_command(["git", "add", "-A"], cwd=project_path, check=True)

        # Create commit message
        task_ids = [t.task_id for t in completed_tasks]
        if len(task_ids) == 1:
            commit_msg = f"feat({spec_name}): complete task {task_ids[0]}\n\n"
            commit_msg += f"{completed_tasks[0].title}"
        else:
            commit_msg = f"feat({spec_name}): complete {len(task_ids)} tasks\n\n"
            for task in completed_tasks:
                commit_msg += f"- {task.task_id}: {task.title}\n"

        commit_msg += "\n\nCo-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"

        # Make commit
        result = run_command(
            ["git", "commit", "-m", commit_msg],
            cwd=project_path,
            check=False,
        )

        if result.returncode == 0:
            # Get commit SHA
            sha_result = run_command(
                ["git", "rev-parse", "HEAD"],
                cwd=project_path,
                check=True,
            )
            commits.append(sha_result.stdout.strip())

    except Exception as e:
        print(f"⚠️  Failed to create commit: {e}", file=sys.stderr)

    return commits


def run_verification(
    spec_name: str,
    spec_path: Path,
    project_path: Path,
    make_commits: bool = True,
    tasks_filename: str = "tasks.md",
) -> VerificationResult:
    """Run verification check on spec tasks.

    Args:
        spec_name: Name of the spec
        spec_path: Path to spec directory
        project_path: Path to project root
        make_commits: Whether to make git commits for verified work
        tasks_filename: Name of tasks file

    Returns:
        VerificationResult with findings
    """
    tasks_md_path = spec_path / tasks_filename

    # Verify in-progress tasks
    verifications = verify_in_progress_tasks(tasks_md_path, project_path)

    # Update tasks.md for verified tasks
    completed_count = update_verified_tasks(
        tasks_md_path,
        [v for v in verifications if v.should_mark_complete],
    )

    # Make commits for verified work
    commits = []
    if make_commits and completed_count > 0:
        commits = make_commit_for_verified_work(
            project_path,
            spec_name,
            verifications,
        )

    return VerificationResult(
        spec_name=spec_name,
        tasks_verified=len(verifications),
        tasks_completed=completed_count,
        tasks_incomplete=len(verifications) - completed_count,
        verifications=verifications,
        commits_made=commits,
    )


def main() -> int:
    """CLI entry point for completion verification.

    Usage:
        python completion_verify.py <spec_name> <spec_path> <project_path> [--no-commit]

    Returns:
        Exit code (0 = success, 1 = error)
    """
    if len(sys.argv) < 4:
        print(
            "Usage: completion_verify.py <spec_name> <spec_path> <project_path> [--no-commit]",
            file=sys.stderr,
        )
        return 1

    spec_name = sys.argv[1]
    spec_path = Path(sys.argv[2])
    project_path = Path(sys.argv[3])
    make_commits = "--no-commit" not in sys.argv

    result = run_verification(spec_name, spec_path, project_path, make_commits)

    # Print summary
    print(result.summary())

    # Print details
    completed = [v for v in result.verifications if v.should_mark_complete]
    incomplete = [v for v in result.verifications if not v.should_mark_complete]

    if completed:
        print("\n✅ Verified and marked complete:\n")
        for task in completed:
            print(f"  {task.task_id}: {task.title}")
            if task.files_modified:
                print(f"    Files: {', '.join(task.files_modified)}")

    if incomplete:
        print("\n⏸️  Still in progress (not ready):\n")
        for task in incomplete:
            print(f"  {task.task_id}: {task.title}")
            for issue in task.issues:
                print(f"    - {issue}")

    if result.commits_made:
        print(f"\n📝 Commits created: {len(result.commits_made)}")
        for sha in result.commits_made:
            print(f"  {sha[:8]}")

    # Output JSON for runner
    output = {
        "spec_name": result.spec_name,
        "tasks_verified": result.tasks_verified,
        "tasks_completed": result.tasks_completed,
        "tasks_incomplete": result.tasks_incomplete,
        "commits_made": result.commits_made,
    }
    print(f"\n{json.dumps(output, indent=2)}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
