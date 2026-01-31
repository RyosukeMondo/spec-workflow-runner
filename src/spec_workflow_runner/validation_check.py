"""Pre-session validation script.

Validates that completed tasks actually have implementations (not just tests/mocks).
Resets task status if implementation is missing.
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from .progress_count import CHECKBOX_PATTERN


@dataclass(frozen=True)
class TaskValidation:
    """Validation result for a single task."""

    task_id: str
    title: str
    status: str
    issues: list[str]
    files_to_check: list[str]

    @property
    def is_valid(self) -> bool:
        """Check if task is valid."""
        return len(self.issues) == 0


@dataclass(frozen=True)
class ValidationResult:
    """Overall validation result."""

    spec_name: str
    tasks_checked: int
    tasks_reset: int
    validations: list[TaskValidation]

    def summary(self) -> str:
        """Generate summary message."""
        if self.tasks_reset == 0:
            return f"✅ All {self.tasks_checked} completed tasks verified"
        return f"🔄 Reset {self.tasks_reset}/{self.tasks_checked} tasks with missing implementations"


def extract_files_from_task(task_text: str) -> list[str]:
    """Extract file paths mentioned in task description.

    Looks for:
    - File: path/to/file.dart
    - Files: list of paths
    - `path/to/file.dart` in backticks
    - lib/path/to/file.dart patterns
    """
    files = []

    # Pattern: - **File**: path or - **Files**:
    file_field = re.findall(r"-\s+\*\*Files?\*\*:\s*(.+)", task_text)
    for match in file_field:
        # Split by comma or newline
        paths = re.split(r"[,\n]", match)
        for path in paths:
            path = path.strip().strip("`").strip()
            if path and not path.startswith("-"):
                files.append(path)

    # Pattern: `path/to/file.dart` in backticks
    backtick_files = re.findall(r"`([^`]+\.\w+)`", task_text)
    files.extend(backtick_files)

    # Pattern: lib/path/to/file.dart or src/path/to/file.dart
    path_pattern = re.findall(
        r"\b((?:lib|src|test)/[a-zA-Z0-9_/]+\.[a-zA-Z0-9]+)\b",
        task_text,
    )
    files.extend(path_pattern)

    # Deduplicate and filter
    seen = set()
    unique_files = []
    for f in files:
        # Remove common markdown artifacts
        f = f.strip().strip("`").strip("(").strip(")").strip()
        if f and f not in seen:
            seen.add(f)
            unique_files.append(f)

    return unique_files


def check_implementation_exists(
    project_path: Path,
    files: list[str],
) -> tuple[bool, list[str]]:
    """Check if implementation files exist (not just mocks/tests).

    Args:
        project_path: Path to project root
        files: List of file paths to check

    Returns:
        Tuple of (has_implementation, issues)
    """
    issues = []
    has_real_implementation = False

    for file_path in files:
        full_path = project_path / file_path

        # Skip test/mock files for implementation check
        is_test_file = "test/" in file_path or "_test." in file_path or "mock" in file_path.lower()

        if not full_path.exists():
            if not is_test_file:
                issues.append(f"Missing implementation: {file_path}")
        else:
            # File exists - check if it's a real implementation
            if not is_test_file:
                has_real_implementation = True
            elif is_test_file and not has_real_implementation:
                # Only tests exist, no implementation
                pass

    # If we only found test files, that's an issue
    if not has_real_implementation and len([f for f in files if "test/" not in f]) > 0:
        issues.append("Only test/mock files exist, no production implementation found")

    return has_real_implementation, issues


def validate_completed_tasks(
    tasks_md_path: Path,
    project_path: Path,
) -> list[TaskValidation]:
    """Validate all completed tasks have actual implementations.

    Args:
        tasks_md_path: Path to tasks.md
        project_path: Path to project root

    Returns:
        List of TaskValidation results
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

    validations = []

    # Find all checkbox tasks
    for match in CHECKBOX_PATTERN.finditer(task_text):
        state = match.group("state")
        title = match.group("title").strip()

        # Only validate completed tasks
        if state != "x":
            continue

        # Extract task section (from this match to next checkbox or end)
        start_pos = match.start()
        next_task = CHECKBOX_PATTERN.search(task_text, match.end())
        end_pos = next_task.start() if next_task else len(task_text)
        task_section = task_text[start_pos:end_pos]

        # Extract files mentioned in task
        files = extract_files_from_task(task_section)

        # Check if implementation exists
        issues = []
        if files:
            has_impl, file_issues = check_implementation_exists(project_path, files)
            issues.extend(file_issues)
        else:
            # No files specified - can't validate
            issues.append("No files specified in task - cannot verify implementation")

        validations.append(
            TaskValidation(
                task_id=title.split(".")[0] if "." in title else title[:10],
                title=title,
                status="completed",
                issues=issues,
                files_to_check=files,
            )
        )

    return validations


def reset_invalid_tasks(tasks_md_path: Path, invalid_tasks: list[TaskValidation]) -> int:
    """Reset invalid completed tasks to in-progress.

    Args:
        tasks_md_path: Path to tasks.md
        invalid_tasks: List of invalid task validations

    Returns:
        Number of tasks reset
    """
    if not invalid_tasks:
        return 0

    content = tasks_md_path.read_text(encoding="utf-8")
    reset_count = 0

    for task in invalid_tasks:
        # Find and replace [x] with [-] for this task
        # Match the task title to ensure we're updating the right task
        pattern = re.compile(
            rf"^(\s*-\s+)\[x\](\s+.*{re.escape(task.title[:30])}.*?)$",
            re.MULTILINE,
        )

        match = pattern.search(content)
        if match:
            # Replace [x] with [-]
            new_content = pattern.sub(r"\1[-]\2", content, count=1)
            if new_content != content:
                content = new_content
                reset_count += 1

    if reset_count > 0:
        tasks_md_path.write_text(content, encoding="utf-8")

    return reset_count


def run_validation(
    spec_name: str,
    spec_path: Path,
    project_path: Path,
    tasks_filename: str = "tasks.md",
) -> ValidationResult:
    """Run validation check on spec tasks.

    Args:
        spec_name: Name of the spec
        spec_path: Path to spec directory
        project_path: Path to project root
        tasks_filename: Name of tasks file

    Returns:
        ValidationResult with findings
    """
    tasks_md_path = spec_path / tasks_filename

    # Validate completed tasks
    validations = validate_completed_tasks(tasks_md_path, project_path)

    # Find invalid tasks (completed but missing implementation)
    invalid_tasks = [v for v in validations if not v.is_valid]

    # Reset invalid tasks to in-progress
    tasks_reset = reset_invalid_tasks(tasks_md_path, invalid_tasks)

    return ValidationResult(
        spec_name=spec_name,
        tasks_checked=len(validations),
        tasks_reset=tasks_reset,
        validations=validations,
    )


def main() -> int:
    """CLI entry point for validation check.

    Usage:
        python validation_check.py <spec_name> <spec_path> <project_path>

    Returns:
        Exit code (0 = all valid, 1 = tasks reset)
    """
    if len(sys.argv) < 4:
        print(
            "Usage: validation_check.py <spec_name> <spec_path> <project_path>",
            file=sys.stderr,
        )
        return 1

    spec_name = sys.argv[1]
    spec_path = Path(sys.argv[2])
    project_path = Path(sys.argv[3])

    result = run_validation(spec_name, spec_path, project_path)

    # Print summary
    print(result.summary())

    # Print details for invalid tasks
    invalid = [v for v in result.validations if not v.is_valid]
    if invalid:
        print(f"\n❌ Invalid tasks reset to in-progress:\n")
        for task in invalid:
            print(f"  {task.task_id}: {task.title}")
            for issue in task.issues:
                print(f"    - {issue}")

    # Output JSON for runner
    output = {
        "spec_name": result.spec_name,
        "tasks_checked": result.tasks_checked,
        "tasks_reset": result.tasks_reset,
        "invalid_tasks": [
            {
                "task_id": v.task_id,
                "title": v.title,
                "issues": v.issues,
                "files": v.files_to_check,
            }
            for v in invalid
        ],
    }
    print(f"\n{json.dumps(output, indent=2)}")

    return 1 if result.tasks_reset > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
