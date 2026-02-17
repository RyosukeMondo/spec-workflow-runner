"""Precise checkbox-based task progress counter.

Counts task checkboxes in tasks.md files:
- [ ] = pending
- [-] = in_progress
- [x] = completed

Validates that tasks.md follows the checkbox format.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class TaskProgress:
    """Task progress counts."""

    pending: int
    in_progress: int
    completed: int

    @property
    def total(self) -> int:
        """Total task count."""
        return self.pending + self.in_progress + self.completed

    @property
    def percentage(self) -> float:
        """Completion percentage."""
        if self.total == 0:
            return 0.0
        return (self.completed / self.total) * 100.0

    def to_dict(self) -> dict[str, int | float]:
        """Convert to dictionary for JSON serialization."""
        return {
            "pending": self.pending,
            "in_progress": self.in_progress,
            "completed": self.completed,
            "total": self.total,
            "percentage": round(self.percentage, 1),
        }

    def summary(self) -> str:
        """Human-readable summary."""
        return (
            f"{self.completed}/{self.total} completed "
            f"({self.in_progress} in progress, {self.pending} pending)"
        )


# Regex pattern for checkbox tasks
# Matches: - [ ] 1. Task or - [x] Task or - [-] 2.1 Task
CHECKBOX_PATTERN = re.compile(
    r"^\s*-\s+\[(?P<state>[ x\-])\]\s+(?:\d+(?:\.\d+)?\.\s+)?(?P<title>.+)$",
    re.MULTILINE,
)


def count_tasks(tasks_md_path: Path) -> TaskProgress:
    """Count tasks from tasks.md file.

    Args:
        tasks_md_path: Path to tasks.md file

    Returns:
        TaskProgress object with counts

    Raises:
        FileNotFoundError: If tasks.md doesn't exist
        ValueError: If no tasks found in file
    """
    if not tasks_md_path.exists():
        raise FileNotFoundError(f"File not found: {tasks_md_path}")

    content = tasks_md_path.read_text(encoding="utf-8")

    # Extract Tasks section (stop at next ## heading)
    tasks_section_start = content.find("## Tasks")
    if tasks_section_start != -1:
        task_text_start = tasks_section_start + len("## Tasks")
        next_section = content.find("\n## ", task_text_start)
        if next_section == -1:
            task_text = content[tasks_section_start:]
        else:
            task_text = content[tasks_section_start:next_section]
    else:
        # Use entire file if no Tasks section
        task_text = content

    # Count checkboxes
    pending = in_progress = completed = 0

    for match in CHECKBOX_PATTERN.finditer(task_text):
        state = match.group("state")
        if state == "x":
            completed += 1
        elif state == "-":
            in_progress += 1
        else:  # space
            pending += 1

    if pending + in_progress + completed == 0:
        raise ValueError(
            f"No checkbox tasks found in {tasks_md_path}. Expected format: '- [ ] Task title'"
        )

    return TaskProgress(
        pending=pending,
        in_progress=in_progress,
        completed=completed,
    )


def validate_format(tasks_md_path: Path) -> list[str]:
    """Validate that tasks.md uses checkbox format.

    Args:
        tasks_md_path: Path to tasks.md file

    Returns:
        List of validation errors (empty if valid)
    """
    errors: list[str] = []

    if not tasks_md_path.exists():
        errors.append(f"File not found: {tasks_md_path}")
        return errors

    content = tasks_md_path.read_text(encoding="utf-8")

    # Check for invalid heading-based format
    heading_task_pattern = re.compile(r"^#{3,4}\s+Task\s+[A-Z]+-\d+", re.MULTILINE)
    if heading_task_pattern.search(content):
        errors.append(
            "Invalid format detected: Heading-based tasks (#### Task XX-N) are not allowed. "
            "Use checkbox format: '- [ ] N. Task title'"
        )

    # Check for tasks section
    if "## Tasks" not in content:
        errors.append("Missing '## Tasks' section header")

    # Check if we found any checkboxes
    try:
        progress = count_tasks(tasks_md_path)
        if progress.total == 0:
            errors.append("No checkbox tasks found. Expected format: '- [ ] N. Task title'")
    except ValueError as e:
        errors.append(str(e))

    return errors


def main() -> int:
    """CLI entry point for progress counting.

    Usage:
        python progress_count.py <path/to/tasks.md>
        python progress_count.py --validate <path/to/tasks.md>

    Returns:
        Exit code (0 = success, 1 = error)
    """
    import json

    if len(sys.argv) < 2:
        print("Usage: progress_count.py [--validate] <path/to/tasks.md>", file=sys.stderr)
        return 1

    validate_only = False
    tasks_path = None

    if sys.argv[1] == "--validate":
        validate_only = True
        if len(sys.argv) < 3:
            print("Usage: progress_count.py --validate <path/to/tasks.md>", file=sys.stderr)
            return 1
        tasks_path = Path(sys.argv[2])
    else:
        tasks_path = Path(sys.argv[1])

    # Validation mode
    if validate_only:
        errors = validate_format(tasks_path)
        if errors:
            print("❌ Validation failed:", file=sys.stderr)
            for error in errors:
                print(f"  - {error}", file=sys.stderr)
            return 1
        print("✅ Format valid: tasks.md uses checkbox format")
        return 0

    # Count mode
    try:
        progress = count_tasks(tasks_path)
        print(json.dumps(progress.to_dict(), indent=2))
        return 0
    except (FileNotFoundError, ValueError) as e:
        print(f"❌ Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
