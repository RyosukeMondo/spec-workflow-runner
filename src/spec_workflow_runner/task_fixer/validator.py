"""Task validation module for detecting format issues in tasks.md files."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class IssueType(Enum):
    """Types of validation issues."""

    MISSING_CHECKBOX = "missing_checkbox"
    INVALID_CHECKBOX = "invalid_checkbox"
    INVALID_TASK_ID = "invalid_task_id"
    INCONSISTENT_NUMBERING = "inconsistent_numbering"
    DUPLICATE_TASK_ID = "duplicate_task_id"
    MISSING_TITLE = "missing_title"
    PARSE_ERROR = "parse_error"


@dataclass(frozen=True)
class ValidationIssue:
    """Represents a single validation issue in a tasks.md file."""

    issue_type: IssueType
    line_number: int
    line_content: str
    message: str


@dataclass(frozen=True)
class ValidationResult:
    """Result of validating a tasks.md file."""

    is_valid: bool
    issues: tuple[ValidationIssue, ...] = field(default_factory=tuple)

    @property
    def issue_count(self) -> int:
        """Get total number of issues."""
        return len(self.issues)

    @property
    def error_summary(self) -> str:
        """Get human-readable summary of errors."""
        if self.is_valid:
            return "No validation issues found."

        summary_lines = [f"Found {self.issue_count} issue(s):"]
        for issue in self.issues:
            summary_lines.append(
                f"  Line {issue.line_number}: {issue.issue_type.value} - {issue.message}"
            )
        return "\n".join(summary_lines)


class TaskValidator:
    """Validates tasks.md files for format compliance."""

    # Pattern for valid task line: - [ ] 1. Task title or - [x] 4.2 Task title
    TASK_PATTERN = re.compile(r"^-\s+\[([ x\-])\]\s+(\d+(?:\.\d+)*)\.\s+(.+)$")

    def validate_file(self, file_path: Path) -> ValidationResult:
        """Validate a tasks.md file for format issues.

        Args:
            file_path: Path to the tasks.md file to validate

        Returns:
            ValidationResult with validation status and any issues found
        """
        if not file_path.exists():
            issue = ValidationIssue(
                issue_type=IssueType.PARSE_ERROR,
                line_number=0,
                line_content="",
                message=f"File not found: {file_path}",
            )
            return ValidationResult(is_valid=False, issues=(issue,))

        try:
            content = file_path.read_text(encoding="utf-8")
            lines = content.splitlines()

            issues: list[ValidationIssue] = []
            seen_task_ids: set[str] = set()
            expected_next_id: str | None = None

            for line_num, line in enumerate(lines, start=1):
                # Skip empty lines and comments
                if not line.strip() or line.strip().startswith("#"):
                    continue

                # Check if this looks like it should be a task line
                # (starts with "- " but might be malformed)
                if line.strip().startswith("- ") and not line.strip().startswith("  -"):
                    self._validate_task_line(
                        line, line_num, issues, seen_task_ids, expected_next_id
                    )

                    # Update expected next ID if this was a valid task
                    match = self.TASK_PATTERN.match(line)
                    if match:
                        task_id = match.group(2)
                        expected_next_id = self._calculate_next_id(task_id)

            is_valid = len(issues) == 0
            return ValidationResult(is_valid=is_valid, issues=tuple(issues))

        except Exception as err:
            issue = ValidationIssue(
                issue_type=IssueType.PARSE_ERROR,
                line_number=0,
                line_content="",
                message=f"Error reading file: {err}",
            )
            return ValidationResult(is_valid=False, issues=(issue,))

    def _validate_task_line(
        self,
        line: str,
        line_num: int,
        issues: list[ValidationIssue],
        seen_task_ids: set[str],
        expected_next_id: str | None,
    ) -> None:
        """Validate a single task line.

        Args:
            line: The line content
            line_num: Line number in file
            issues: List to append issues to
            seen_task_ids: Set of already seen task IDs
            expected_next_id: Expected next task ID for sequence validation
        """
        match = self.TASK_PATTERN.match(line)

        if not match:
            # Check specific issues
            if not re.search(r"\[[ x\-]\]", line):
                issues.append(
                    ValidationIssue(
                        issue_type=IssueType.MISSING_CHECKBOX,
                        line_number=line_num,
                        line_content=line,
                        message="Task line missing valid checkbox [ ], [x], or [-]",
                    )
                )
            elif not re.search(r"\d+(?:\.\d+)*\.", line):
                issues.append(
                    ValidationIssue(
                        issue_type=IssueType.INVALID_TASK_ID,
                        line_number=line_num,
                        line_content=line,
                        message="Task line missing valid task ID (e.g., '1.' or '4.2.')",
                    )
                )
            else:
                # Check for invalid checkbox characters
                checkbox_match = re.search(r"\[(.)\]", line)
                if checkbox_match and checkbox_match.group(1) not in " x-":
                    issues.append(
                        ValidationIssue(
                            issue_type=IssueType.INVALID_CHECKBOX,
                            line_number=line_num,
                            line_content=line,
                            message=f"Invalid checkbox character: [{checkbox_match.group(1)}]",
                        )
                    )
                else:
                    # Generic parse error
                    issues.append(
                        ValidationIssue(
                            issue_type=IssueType.PARSE_ERROR,
                            line_number=line_num,
                            line_content=line,
                            message="Task line does not match expected format",
                        )
                    )
            return

        # Valid match - extract components
        task_id = match.group(2)
        task_title = match.group(3)

        # Check for duplicate task IDs
        if task_id in seen_task_ids:
            issues.append(
                ValidationIssue(
                    issue_type=IssueType.DUPLICATE_TASK_ID,
                    line_number=line_num,
                    line_content=line,
                    message=f"Duplicate task ID: {task_id}",
                )
            )
        else:
            seen_task_ids.add(task_id)

        # Check for missing title
        if not task_title.strip():
            issues.append(
                ValidationIssue(
                    issue_type=IssueType.MISSING_TITLE,
                    line_number=line_num,
                    line_content=line,
                    message="Task has no title",
                )
            )

        # Check for inconsistent numbering (only for top-level tasks)
        if expected_next_id and "." not in task_id:
            if task_id != expected_next_id:
                issues.append(
                    ValidationIssue(
                        issue_type=IssueType.INCONSISTENT_NUMBERING,
                        line_number=line_num,
                        line_content=line,
                        message=f"Expected task ID {expected_next_id}, found {task_id}",
                    )
                )

    def _calculate_next_id(self, current_id: str) -> str:
        """Calculate the next expected task ID.

        Args:
            current_id: Current task ID (e.g., "1", "4.2", "4.2.1")

        Returns:
            Next expected task ID (e.g., "2", "4.3", "4.2.2")
        """
        parts = current_id.split(".")

        # Only track top-level task sequence
        if len(parts) == 1:
            return str(int(parts[0]) + 1)

        # For subtasks, we don't enforce strict sequence
        return current_id
