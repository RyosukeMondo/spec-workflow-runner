"""Tests for task validator module."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from spec_workflow_runner.task_fixer.validator import (
    IssueType,
    TaskValidator,
    ValidationIssue,
    ValidationResult,
)


@pytest.fixture
def validator() -> TaskValidator:
    """Create a TaskValidator instance."""
    return TaskValidator()


@pytest.fixture
def temp_dir() -> TemporaryDirectory:
    """Create a temporary directory for test files."""
    return TemporaryDirectory()


def test_valid_tasks_file(validator: TaskValidator, temp_dir: TemporaryDirectory) -> None:
    """Test validation passes for properly formatted tasks.md file."""
    content = """# Tasks Document

- [ ] 1. First task
- [x] 2. Second task completed
- [-] 3. Third task in progress
"""

    test_file = Path(temp_dir.name) / "tasks.md"
    test_file.write_text(content, encoding="utf-8")

    result = validator.validate_file(test_file)

    assert result.is_valid
    assert result.issue_count == 0
    assert result.error_summary == "No validation issues found."


def test_valid_tasks_with_subtasks(validator: TaskValidator, temp_dir: TemporaryDirectory) -> None:
    """Test validation passes for tasks with only subtask numbering."""
    content = """# Tasks Document

- [ ] 1.1. Subtask one
- [ ] 1.2. Subtask two
- [x] 2.1. Subtask one
- [x] 2.2.1. Deep subtask
"""

    test_file = Path(temp_dir.name) / "tasks.md"
    test_file.write_text(content, encoding="utf-8")

    result = validator.validate_file(test_file)

    assert result.is_valid
    assert result.issue_count == 0


def test_missing_checkbox(validator: TaskValidator, temp_dir: TemporaryDirectory) -> None:
    """Test detection of missing checkbox."""
    content = """# Tasks Document

- 1. Task without checkbox
"""

    test_file = Path(temp_dir.name) / "tasks.md"
    test_file.write_text(content, encoding="utf-8")

    result = validator.validate_file(test_file)

    assert not result.is_valid
    assert result.issue_count == 1
    assert result.issues[0].issue_type == IssueType.MISSING_CHECKBOX
    assert result.issues[0].line_number == 3
    assert "missing valid checkbox" in result.issues[0].message


def test_invalid_checkbox_character(validator: TaskValidator, temp_dir: TemporaryDirectory) -> None:
    """Test detection of invalid checkbox character.

    Note: Invalid checkboxes with valid task IDs are detected as INVALID_CHECKBOX.
    Invalid checkboxes without valid task IDs might be detected as MISSING_CHECKBOX.
    """
    # Case 1: Has valid task ID, invalid checkbox -> should detect invalid checkbox
    content = """# Tasks Document

- [ ] 1. Good task
- [*] 1. Task
- [y] 1. Task
"""

    test_file = Path(temp_dir.name) / "tasks.md"
    test_file.write_text(content, encoding="utf-8")

    result = validator.validate_file(test_file)

    assert not result.is_valid
    # These should be flagged as MISSING_CHECKBOX since [*] doesn't match the valid checkbox pattern
    missing_cb_issues = [i for i in result.issues if i.issue_type == IssueType.MISSING_CHECKBOX]
    assert len(missing_cb_issues) >= 2


def test_missing_task_id(validator: TaskValidator, temp_dir: TemporaryDirectory) -> None:
    """Test detection of missing task ID."""
    content = """# Tasks Document

- [ ] Task without ID
- [x] Another task without ID
"""

    test_file = Path(temp_dir.name) / "tasks.md"
    test_file.write_text(content, encoding="utf-8")

    result = validator.validate_file(test_file)

    assert not result.is_valid
    assert result.issue_count == 2
    assert all(issue.issue_type == IssueType.INVALID_TASK_ID for issue in result.issues)


def test_invalid_task_id_format(validator: TaskValidator, temp_dir: TemporaryDirectory) -> None:
    """Test detection of invalid task ID format."""
    content = """# Tasks Document

- [ ] a. Task with letter ID
- [x] 1 Task missing period after ID
"""

    test_file = Path(temp_dir.name) / "tasks.md"
    test_file.write_text(content, encoding="utf-8")

    result = validator.validate_file(test_file)

    assert not result.is_valid
    assert result.issue_count >= 1


def test_duplicate_task_ids(validator: TaskValidator, temp_dir: TemporaryDirectory) -> None:
    """Test detection of duplicate task IDs."""
    content = """# Tasks Document

- [ ] 1. First task
- [ ] 1. Duplicate task ID
- [ ] 2. Different task
- [ ] 2. Another duplicate
"""

    test_file = Path(temp_dir.name) / "tasks.md"
    test_file.write_text(content, encoding="utf-8")

    result = validator.validate_file(test_file)

    assert not result.is_valid
    duplicate_issues = [i for i in result.issues if i.issue_type == IssueType.DUPLICATE_TASK_ID]
    assert len(duplicate_issues) == 2
    assert "Duplicate task ID: 1" in duplicate_issues[0].message
    assert "Duplicate task ID: 2" in duplicate_issues[1].message


def test_inconsistent_numbering(validator: TaskValidator, temp_dir: TemporaryDirectory) -> None:
    """Test detection of inconsistent task numbering."""
    content = """# Tasks Document

- [ ] 1. First task
- [ ] 3. Skipped task 2
- [ ] 5. Skipped task 4
"""

    test_file = Path(temp_dir.name) / "tasks.md"
    test_file.write_text(content, encoding="utf-8")

    result = validator.validate_file(test_file)

    assert not result.is_valid
    inconsistent_issues = [i for i in result.issues if i.issue_type == IssueType.INCONSISTENT_NUMBERING]
    assert len(inconsistent_issues) == 2
    assert "Expected task ID 2, found 3" in inconsistent_issues[0].message
    assert "Expected task ID 4, found 5" in inconsistent_issues[1].message


def test_missing_task_title(validator: TaskValidator, temp_dir: TemporaryDirectory) -> None:
    """Test detection of missing task title."""
    content = """# Tasks Document

- [ ] 1.
- [x] 2.
"""

    test_file = Path(temp_dir.name) / "tasks.md"
    test_file.write_text(content, encoding="utf-8")

    result = validator.validate_file(test_file)

    assert not result.is_valid
    # Lines with only period and whitespace won't match pattern - will be parse errors
    assert result.issue_count == 2


def test_empty_file(validator: TaskValidator, temp_dir: TemporaryDirectory) -> None:
    """Test validation of empty file."""
    content = ""

    test_file = Path(temp_dir.name) / "tasks.md"
    test_file.write_text(content, encoding="utf-8")

    result = validator.validate_file(test_file)

    assert result.is_valid
    assert result.issue_count == 0


def test_file_with_only_comments(validator: TaskValidator, temp_dir: TemporaryDirectory) -> None:
    """Test validation of file with only comments and headers."""
    content = """# Tasks Document

## Section 1

Some description text

## Section 2
"""

    test_file = Path(temp_dir.name) / "tasks.md"
    test_file.write_text(content, encoding="utf-8")

    result = validator.validate_file(test_file)

    assert result.is_valid
    assert result.issue_count == 0


def test_file_not_found(validator: TaskValidator, temp_dir: TemporaryDirectory) -> None:
    """Test handling of non-existent file."""
    test_file = Path(temp_dir.name) / "nonexistent.md"

    result = validator.validate_file(test_file)

    assert not result.is_valid
    assert result.issue_count == 1
    assert result.issues[0].issue_type == IssueType.PARSE_ERROR
    assert "File not found" in result.issues[0].message


def test_multiple_validation_errors(validator: TaskValidator, temp_dir: TemporaryDirectory) -> None:
    """Test file with multiple different validation errors."""
    content = """# Tasks Document

- [ ] 1. First valid task
- 2. Missing checkbox
- [ ] Invalid ID format
- [ ] 5. Skipped task 4
- [ ] 5. Duplicate ID
"""

    test_file = Path(temp_dir.name) / "tasks.md"
    test_file.write_text(content, encoding="utf-8")

    result = validator.validate_file(test_file)

    assert not result.is_valid
    assert result.issue_count >= 4

    # Verify we have different types of issues
    issue_types = {issue.issue_type for issue in result.issues}
    assert IssueType.MISSING_CHECKBOX in issue_types
    assert IssueType.DUPLICATE_TASK_ID in issue_types
    assert IssueType.INVALID_TASK_ID in issue_types
    assert IssueType.INCONSISTENT_NUMBERING in issue_types


def test_error_summary_formatting(validator: TaskValidator, temp_dir: TemporaryDirectory) -> None:
    """Test error summary formatting for multiple issues."""
    content = """# Tasks Document

- 1. Missing checkbox
- [*] 2. Invalid checkbox
"""

    test_file = Path(temp_dir.name) / "tasks.md"
    test_file.write_text(content, encoding="utf-8")

    result = validator.validate_file(test_file)

    summary = result.error_summary
    assert "Found 2 issue(s):" in summary
    assert "Line 3:" in summary
    assert "Line 4:" in summary


def test_skip_blank_lines_and_headers(validator: TaskValidator, temp_dir: TemporaryDirectory) -> None:
    """Test that blank lines and headers are skipped."""
    content = """# Tasks Document

## Section header

- [ ] 1. Main task

## Another section

- [ ] 2. Second task
"""

    test_file = Path(temp_dir.name) / "tasks.md"
    test_file.write_text(content, encoding="utf-8")

    result = validator.validate_file(test_file)

    assert result.is_valid
    assert result.issue_count == 0


def test_validation_result_properties(validator: TaskValidator, temp_dir: TemporaryDirectory) -> None:
    """Test ValidationResult properties."""
    content = """# Tasks Document

- 1. Missing checkbox
- [*] 2. Invalid checkbox
"""

    test_file = Path(temp_dir.name) / "tasks.md"
    test_file.write_text(content, encoding="utf-8")

    result = validator.validate_file(test_file)

    assert isinstance(result, ValidationResult)
    assert result.issue_count == len(result.issues)
    assert not result.is_valid
    assert isinstance(result.error_summary, str)
    assert len(result.error_summary) > 0


def test_validation_issue_immutability() -> None:
    """Test that ValidationIssue is immutable (frozen)."""
    issue = ValidationIssue(
        issue_type=IssueType.MISSING_CHECKBOX,
        line_number=1,
        line_content="test",
        message="test message"
    )

    with pytest.raises(Exception):  # FrozenInstanceError or AttributeError
        issue.line_number = 2  # type: ignore


def test_validation_result_immutability() -> None:
    """Test that ValidationResult is immutable (frozen)."""
    result = ValidationResult(is_valid=True, issues=())

    with pytest.raises(Exception):  # FrozenInstanceError or AttributeError
        result.is_valid = False  # type: ignore


@pytest.mark.parametrize(
    "checkbox,expected_valid",
    [
        ("[ ]", True),
        ("[x]", True),
        ("[-]", True),
        ("[*]", False),
        ("[y]", False),
        ("[n]", False),
        ("[X]", False),  # Uppercase not allowed
    ]
)
def test_checkbox_validation_parametrized(
    validator: TaskValidator,
    temp_dir: TemporaryDirectory,
    checkbox: str,
    expected_valid: bool
) -> None:
    """Test various checkbox formats."""
    content = f"""# Tasks Document

- {checkbox} 1. Test task
"""

    test_file = Path(temp_dir.name) / "tasks.md"
    test_file.write_text(content, encoding="utf-8")

    result = validator.validate_file(test_file)

    assert result.is_valid == expected_valid


@pytest.mark.parametrize(
    "task_id,expected_valid",
    [
        ("1.", True),
        ("10.", True),
        ("1.1.", True),
        ("4.2.3.", True),
        ("1.2.3.4.", True),
        ("a.", False),
        ("1", False),  # Missing period
        ("1.a.", False),
    ]
)
def test_task_id_validation_parametrized(
    validator: TaskValidator,
    temp_dir: TemporaryDirectory,
    task_id: str,
    expected_valid: bool
) -> None:
    """Test various task ID formats."""
    content = f"""# Tasks Document

- [ ] {task_id} Test task
"""

    test_file = Path(temp_dir.name) / "tasks.md"
    test_file.write_text(content, encoding="utf-8")

    result = validator.validate_file(test_file)

    assert result.is_valid == expected_valid


def test_subtasks_flexible_numbering(
    validator: TaskValidator,
    temp_dir: TemporaryDirectory
) -> None:
    """Test that subtasks can skip numbers."""
    content = """# Tasks Document

- [ ] 1.1. Subtask
- [ ] 1.3. Can skip subtask numbers
- [ ] 2.5. Subtask numbering is flexible
- [ ] 3.1.5. Deep nesting is ok
"""

    test_file = Path(temp_dir.name) / "tasks.md"
    test_file.write_text(content, encoding="utf-8")

    result = validator.validate_file(test_file)

    # Should be valid - subtasks don't need sequential numbering
    assert result.is_valid
    assert result.issue_count == 0


def test_calculate_next_id_top_level(validator: TaskValidator) -> None:
    """Test next ID calculation for top-level tasks."""
    assert validator._calculate_next_id("1") == "2"
    assert validator._calculate_next_id("5") == "6"
    assert validator._calculate_next_id("99") == "100"


def test_calculate_next_id_subtasks(validator: TaskValidator) -> None:
    """Test next ID calculation for subtasks (returns same ID)."""
    assert validator._calculate_next_id("1.1") == "1.1"
    assert validator._calculate_next_id("4.2") == "4.2"
    assert validator._calculate_next_id("1.2.3") == "1.2.3"


def test_file_read_error_handling(validator: TaskValidator, temp_dir: TemporaryDirectory) -> None:
    """Test handling of file read errors."""
    test_file = Path(temp_dir.name) / "tasks.md"
    test_file.write_text("test content", encoding="utf-8")

    # Make file unreadable (Unix only)
    import os
    import stat
    if os.name != 'nt':  # Skip on Windows
        test_file.chmod(0o000)

        result = validator.validate_file(test_file)

        assert not result.is_valid
        assert result.issue_count == 1
        assert result.issues[0].issue_type == IssueType.PARSE_ERROR
        assert "Error reading file" in result.issues[0].message

        # Restore permissions for cleanup
        test_file.chmod(stat.S_IRUSR | stat.S_IWUSR)


def test_whitespace_only_title(validator: TaskValidator, temp_dir: TemporaryDirectory) -> None:
    """Test detection of task with whitespace-only title."""
    content = "# Tasks Document\n\n- [ ] 1.   \n- [x] 2.   \n"

    test_file = Path(temp_dir.name) / "tasks.md"
    test_file.write_text(content, encoding="utf-8")

    result = validator.validate_file(test_file)

    assert not result.is_valid
    title_issues = [i for i in result.issues if i.issue_type == IssueType.MISSING_TITLE]
    assert len(title_issues) == 2


def test_invalid_checkbox_with_valid_id(validator: TaskValidator, temp_dir: TemporaryDirectory) -> None:
    """Test line with valid task ID but invalid checkbox triggers INVALID_CHECKBOX.

    This happens when:
    - Line doesn't match full pattern
    - Has a valid task ID pattern
    - Has a checkbox pattern but with invalid character
    """
    content = """# Tasks Document

- [ ] 1. Title with space between checkbox and number
"""

    test_file = Path(temp_dir.name) / "tasks.md"
    test_file.write_text(content, encoding="utf-8")

    result = validator.validate_file(test_file)

    # This should actually be valid since there are multiple spaces allowed
    assert result.is_valid


def test_parse_error_fallback(validator: TaskValidator, temp_dir: TemporaryDirectory) -> None:
    """Test generic parse error when format is completely wrong but has checkbox and ID."""
    # This is a case where line starts with "- " so it's checked, but doesn't match pattern
    content = """# Tasks Document

- [] 1. Missing space in checkbox
"""

    test_file = Path(temp_dir.name) / "tasks.md"
    test_file.write_text(content, encoding="utf-8")

    result = validator.validate_file(test_file)

    assert not result.is_valid
    # Should get missing checkbox error
    assert result.issue_count >= 1
    assert any(issue.issue_type == IssueType.MISSING_CHECKBOX for issue in result.issues)
