"""Tests for progress_count module."""

from pathlib import Path

import pytest

from spec_workflow_runner.progress_count import (
    TaskProgress,
    count_tasks,
    validate_format,
)


@pytest.fixture
def valid_tasks_md(tmp_path: Path) -> Path:
    """Create a valid tasks.md file."""
    tasks_file = tmp_path / "tasks.md"
    tasks_file.write_text(
        """# Tasks Document

## Tasks

- [ ] 1. First task
- [-] 2. Second task in progress
- [x] 3. Completed task
- [ ] 4.1 Subtask pending
"""
    )
    return tasks_file


@pytest.fixture
def invalid_heading_tasks_md(tmp_path: Path) -> Path:
    """Create an invalid tasks.md with heading format."""
    tasks_file = tmp_path / "tasks.md"
    tasks_file.write_text(
        """# Tasks Document

## Tasks

#### Task VF-1.1: First task
- **Status**: Pending

#### Task VF-1.2: Second task
- **Status**: Completed
"""
    )
    return tasks_file


@pytest.fixture
def empty_tasks_md(tmp_path: Path) -> Path:
    """Create an empty tasks.md file."""
    tasks_file = tmp_path / "tasks.md"
    tasks_file.write_text("# Tasks Document\n\n## Tasks\n\nNo tasks yet.\n")
    return tasks_file


def test_task_progress_properties() -> None:
    """Test TaskProgress calculated properties."""
    progress = TaskProgress(pending=5, in_progress=2, completed=3)

    assert progress.total == 10
    assert progress.percentage == 30.0
    assert progress.summary() == "3/10 completed (2 in progress, 5 pending)"


def test_task_progress_to_dict() -> None:
    """Test TaskProgress JSON serialization."""
    progress = TaskProgress(pending=5, in_progress=2, completed=3)
    data = progress.to_dict()

    assert data == {
        "pending": 5,
        "in_progress": 2,
        "completed": 3,
        "total": 10,
        "percentage": 30.0,
    }


def test_count_tasks_valid_file(valid_tasks_md: Path) -> None:
    """Test counting tasks from valid tasks.md."""
    progress = count_tasks(valid_tasks_md)

    assert progress.pending == 2
    assert progress.in_progress == 1
    assert progress.completed == 1
    assert progress.total == 4


def test_count_tasks_file_not_found() -> None:
    """Test counting tasks from non-existent file."""
    with pytest.raises(FileNotFoundError):
        count_tasks(Path("/nonexistent/tasks.md"))


def test_count_tasks_empty_file(empty_tasks_md: Path) -> None:
    """Test counting tasks from empty tasks.md."""
    with pytest.raises(ValueError, match="No checkbox tasks found"):
        count_tasks(empty_tasks_md)


def test_validate_format_valid(valid_tasks_md: Path) -> None:
    """Test validation of valid tasks.md."""
    errors = validate_format(valid_tasks_md)
    assert errors == []


def test_validate_format_heading_format(invalid_heading_tasks_md: Path) -> None:
    """Test validation detects heading format."""
    errors = validate_format(invalid_heading_tasks_md)

    assert len(errors) > 0
    assert any("Heading-based tasks" in error for error in errors)


def test_validate_format_file_not_found() -> None:
    """Test validation of non-existent file."""
    errors = validate_format(Path("/nonexistent/tasks.md"))

    assert len(errors) == 1
    assert "File not found" in errors[0]


def test_validate_format_missing_tasks_section(tmp_path: Path) -> None:
    """Test validation detects missing Tasks section."""
    tasks_file = tmp_path / "tasks.md"
    tasks_file.write_text("# Tasks Document\n\nSome content but no tasks section.\n")

    errors = validate_format(tasks_file)

    assert len(errors) > 0
    assert any("Missing '## Tasks' section" in error for error in errors)


def test_count_tasks_with_whitespace_variations(tmp_path: Path) -> None:
    """Test counting tasks with various whitespace patterns."""
    tasks_file = tmp_path / "tasks.md"
    tasks_file.write_text(
        """## Tasks

  - [ ] 1. Task with leading spaces
-  [ ]  2. Task with extra spaces
   - [x]   3.   Task with lots of spaces
- [-] 4. Normal task
"""
    )

    progress = count_tasks(tasks_file)

    assert progress.pending == 2
    assert progress.in_progress == 1
    assert progress.completed == 1
    assert progress.total == 4


def test_count_tasks_stops_at_next_section(tmp_path: Path) -> None:
    """Test that counting stops at next ## section."""
    tasks_file = tmp_path / "tasks.md"
    tasks_file.write_text(
        """# Tasks Document

## Tasks

- [ ] 1. First task
- [x] 2. Second task

## Task Validation Checklist

- [ ] This should not be counted
- [ ] Neither should this
"""
    )

    progress = count_tasks(tasks_file)

    # Should only count the 2 tasks in Tasks section
    assert progress.total == 2
    assert progress.pending == 1
    assert progress.completed == 1
