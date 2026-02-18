"""Tests for completion_verify module."""

from pathlib import Path

import pytest

from spec_workflow_runner.completion_verify import (
    check_files_exist,
    extract_acceptance_criteria,
    extract_files_from_task_section,
    update_verified_tasks,
    verify_in_progress_tasks,
)


@pytest.fixture
def project_with_changes(tmp_path: Path) -> Path:
    """Create a project with some modified files."""
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

    # Initialize git repo (needed for verification)
    import subprocess

    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )

    return tmp_path


@pytest.fixture
def tasks_md_in_progress(tmp_path: Path) -> Path:
    """Create tasks.md with in-progress tasks."""
    tasks_file = tmp_path / "tasks.md"
    tasks_file.write_text("""# Tasks

## Tasks

- [-] 1. Implement repository
  - **File**: lib/repositories/subscription_repository.dart
  - **Acceptance**:
    - [x] Production code exists
    - [x] Tests written
    - [x] Repository pattern followed

- [-] 2. Incomplete task
  - **File**: lib/missing_file.dart
  - **Acceptance**:
    - [ ] File created
    - [ ] Tests written

- [ ] 3. Pending task
""")
    return tasks_file


def test_extract_acceptance_criteria():
    """Test extracting acceptance criteria from task."""
    task_text = """
- **Acceptance**:
  - [x] Production code exists
  - [x] Tests written
  - [ ] Documentation updated
"""

    criteria = extract_acceptance_criteria(task_text)

    assert criteria is not None
    assert len(criteria.criteria) == 3
    assert criteria.checked == [True, True, False]
    assert not criteria.all_met
    assert criteria.completion_rate == pytest.approx(66.67, rel=0.01)


def test_extract_acceptance_criteria_all_met():
    """Test acceptance criteria when all are met."""
    task_text = """
- **Acceptance Criteria**:
  - [x] Production code exists
  - [x] Tests written
"""

    criteria = extract_acceptance_criteria(task_text)

    assert criteria is not None
    assert criteria.all_met


def test_extract_files_from_task_section():
    """Test extracting files from task section."""
    task_text = """
- **File**: lib/repositories/subscription_repository.dart
- **Description**: Implementation with `lib/models/subscription.dart`
"""

    files = extract_files_from_task_section(task_text)

    assert "lib/repositories/subscription_repository.dart" in files
    assert "lib/models/subscription.dart" in files


def test_check_files_exist_all_present(project_with_changes: Path):
    """Test checking files when all exist."""
    files = [
        "lib/repositories/subscription_repository.dart",
        "test/unit/subscription_test.dart",
    ]

    all_exist, missing = check_files_exist(project_with_changes, files)

    assert all_exist is True
    assert len(missing) == 0


def test_check_files_exist_some_missing(project_with_changes: Path):
    """Test checking files when some are missing."""
    files = [
        "lib/repositories/subscription_repository.dart",
        "lib/missing_file.dart",
    ]

    all_exist, missing = check_files_exist(project_with_changes, files)

    assert all_exist is False
    assert "lib/missing_file.dart" in missing


def test_verify_in_progress_tasks_valid(tasks_md_in_progress: Path, project_with_changes: Path):
    """Test verifying in-progress tasks with valid implementation."""
    import subprocess

    # Stage some files to simulate modified files
    subprocess.run(
        ["git", "add", "-A"],
        cwd=project_with_changes,
        check=True,
        capture_output=True,
    )

    verifications = verify_in_progress_tasks(tasks_md_in_progress, project_with_changes)

    # First task should verify successfully
    valid_task = next(v for v in verifications if "repository" in v.title.lower())
    assert valid_task.verification_passed
    assert valid_task.should_mark_complete


def test_verify_in_progress_tasks_invalid(tasks_md_in_progress: Path, project_with_changes: Path):
    """Test verifying in-progress tasks with missing implementation."""
    import subprocess

    # Stage some files
    subprocess.run(
        ["git", "add", "-A"],
        cwd=project_with_changes,
        check=True,
        capture_output=True,
    )

    verifications = verify_in_progress_tasks(tasks_md_in_progress, project_with_changes)

    # Second task should fail verification
    invalid_task = next(v for v in verifications if "Incomplete" in v.title)
    assert not invalid_task.verification_passed
    assert not invalid_task.should_mark_complete
    # Check for missing files or no files specified
    assert any("Missing files" in issue or "No files" in issue for issue in invalid_task.issues)


def test_update_verified_tasks(tmp_path: Path):
    """Test updating tasks.md with verified completions."""
    tasks_file = tmp_path / "tasks.md"
    tasks_file.write_text("""# Tasks

## Tasks

- [-] 1. Task to complete
- [-] 2. Task to keep in progress
""")

    from spec_workflow_runner.completion_verify import TaskVerification

    verified_tasks = [
        TaskVerification(
            task_id="1",
            title="1. Task to complete",
            current_status="in_progress",
            files_modified=["lib/file.dart"],
            acceptance=None,
            verification_passed=True,
            issues=[],
        ),
    ]

    completed_count = update_verified_tasks(tasks_file, verified_tasks)

    assert completed_count == 1

    content = tasks_file.read_text()
    assert "- [x] 1. Task to complete" in content
    assert "- [-] 2. Task to keep in progress" in content
