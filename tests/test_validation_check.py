"""Tests for validation_check module."""

from pathlib import Path

import pytest

from spec_workflow_runner.validation_check import (
    check_implementation_exists,
    extract_files_from_task,
    reset_invalid_tasks,
    run_validation,
    validate_completed_tasks,
)


@pytest.fixture
def project_with_files(tmp_path: Path) -> Path:
    """Create a project with some implementation files."""
    # Create production files
    (tmp_path / "lib" / "repositories").mkdir(parents=True)
    (tmp_path / "lib" / "repositories" / "subscription_repository.dart").write_text(
        "class SubscriptionRepository {}"
    )

    # Create test files
    (tmp_path / "test" / "unit").mkdir(parents=True)
    (tmp_path / "test" / "unit" / "subscription_test.dart").write_text(
        "test('subscription', () {});"
    )

    # Create mock files
    (tmp_path / "test" / "mocks").mkdir(parents=True)
    (tmp_path / "test" / "mocks" / "mock_repository.dart").write_text("class MockRepository {}")

    return tmp_path


@pytest.fixture
def tasks_md_with_completed(tmp_path: Path) -> Path:
    """Create tasks.md with completed tasks."""
    tasks_file = tmp_path / "tasks.md"
    tasks_file.write_text("""# Tasks

## Tasks

- [x] 1. Implement subscription repository
  - **Files**:
    - lib/repositories/subscription_repository.dart
    - test/unit/subscription_test.dart

- [x] 2. Mock-only implementation
  - **Files**:
    - test/mocks/mock_repository.dart
    - lib/repositories/user_repository.dart

- [ ] 3. Pending task
""")
    return tasks_file


def test_extract_files_from_task():
    """Test extracting file paths from task text."""
    task_text = """
- **Files**:
  - lib/repositories/subscription_repository.dart
  - test/unit/subscription_test.dart
- **Description**: Some description with `lib/models/subscription.dart` in backticks
"""

    files = extract_files_from_task(task_text)

    assert "lib/repositories/subscription_repository.dart" in files
    assert "test/unit/subscription_test.dart" in files
    assert "lib/models/subscription.dart" in files


def test_check_implementation_exists_valid(project_with_files: Path):
    """Test checking valid implementation (production + tests)."""
    files = [
        "lib/repositories/subscription_repository.dart",
        "test/unit/subscription_test.dart",
    ]

    has_impl, issues = check_implementation_exists(project_with_files, files)

    assert has_impl is True
    assert len(issues) == 0


def test_check_implementation_exists_missing(project_with_files: Path):
    """Test checking missing implementation."""
    files = [
        "lib/repositories/user_repository.dart",  # Doesn't exist
        "test/unit/user_test.dart",
    ]

    has_impl, issues = check_implementation_exists(project_with_files, files)

    assert has_impl is False
    assert any("Missing implementation" in issue for issue in issues)


def test_check_implementation_exists_mocks_only(project_with_files: Path):
    """Test detecting mocks-only situation."""
    files = [
        "test/mocks/mock_repository.dart",
        "lib/repositories/payment_repository.dart",  # Doesn't exist
    ]

    has_impl, issues = check_implementation_exists(project_with_files, files)

    assert has_impl is False
    assert any("Only test/mock files exist" in issue for issue in issues)


def test_validate_completed_tasks_valid(tasks_md_with_completed: Path, project_with_files: Path):
    """Test validating completed tasks with valid implementation."""
    validations = validate_completed_tasks(tasks_md_with_completed, project_with_files)

    # First task should be valid
    valid_task = next(v for v in validations if "subscription repository" in v.title.lower())
    assert valid_task.is_valid


def test_validate_completed_tasks_invalid(tasks_md_with_completed: Path, project_with_files: Path):
    """Test validating completed tasks with missing implementation."""
    validations = validate_completed_tasks(tasks_md_with_completed, project_with_files)

    # Second task should be invalid (user_repository.dart doesn't exist)
    invalid_task = next(v for v in validations if "Mock-only" in v.title)
    assert not invalid_task.is_valid
    assert any("Missing implementation" in issue for issue in invalid_task.issues)


def test_reset_invalid_tasks(tmp_path: Path):
    """Test resetting invalid tasks to in-progress."""
    tasks_file = tmp_path / "tasks.md"
    tasks_file.write_text("""# Tasks

## Tasks

- [x] 1. Task to reset
- [x] 2. Another task to reset
- [ ] 3. Pending task
""")

    from spec_workflow_runner.validation_check import TaskValidation

    invalid_tasks = [
        TaskValidation(
            task_id="1",
            title="1. Task to reset",
            status="completed",
            issues=["Missing implementation"],
            files_to_check=[],
        ),
    ]

    reset_count = reset_invalid_tasks(tasks_file, invalid_tasks)

    assert reset_count == 1

    content = tasks_file.read_text()
    assert "- [-] 1. Task to reset" in content
    assert "- [x] 2. Another task to reset" in content  # Not reset


def test_run_validation(tmp_path: Path, project_with_files: Path):
    """Test running full validation."""
    spec_path = tmp_path / "spec"
    spec_path.mkdir()

    tasks_file = spec_path / "tasks.md"
    tasks_file.write_text("""# Tasks

## Tasks

- [x] 1. Valid task
  - **Files**: lib/repositories/subscription_repository.dart

- [x] 2. Invalid task
  - **Files**: lib/missing_file.dart
""")

    result = run_validation(
        spec_name="test",
        spec_path=spec_path,
        project_path=project_with_files,
    )

    assert result.tasks_checked == 2
    assert result.tasks_reset == 1  # One task should be reset
