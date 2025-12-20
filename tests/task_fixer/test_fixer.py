"""Tests for TaskFixer orchestrator module."""

from __future__ import annotations

import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, Mock, patch

import pytest

from spec_workflow_runner.providers import Provider, ProviderCommand
from spec_workflow_runner.task_fixer.diff_generator import DiffGenerator, DiffResult
from spec_workflow_runner.task_fixer.file_writer import FileWriter, WriteResult
from spec_workflow_runner.task_fixer.fixer import FixResult, TaskFixer
from spec_workflow_runner.task_fixer.prompt_builder import PromptBuilder, PromptContext
from spec_workflow_runner.task_fixer.validator import (
    IssueType,
    TaskValidator,
    ValidationIssue,
    ValidationResult,
)


@pytest.fixture
def temp_dir() -> TemporaryDirectory:
    """Create a temporary directory for test files."""
    return TemporaryDirectory()


@pytest.fixture
def mock_provider() -> Mock:
    """Create a mock Provider."""
    provider = Mock(spec=Provider)
    provider.build_command.return_value = ProviderCommand(
        executable="claude",
        args=("--model", "sonnet", "fix this"),
    )
    return provider


@pytest.fixture
def mock_validator() -> Mock:
    """Create a mock TaskValidator."""
    return Mock(spec=TaskValidator)


@pytest.fixture
def mock_prompt_builder() -> Mock:
    """Create a mock PromptBuilder."""
    builder = Mock(spec=PromptBuilder)
    builder.build_prompt.return_value = "Fix this tasks.md file"
    return builder


@pytest.fixture
def mock_diff_generator() -> Mock:
    """Create a mock DiffGenerator."""
    generator = Mock(spec=DiffGenerator)
    generator.generate_diff.return_value = DiffResult(
        diff_text="- old\n+ new",
        has_changes=True,
        lines_added=1,
        lines_removed=1,
        lines_modified=0,
    )
    return generator


@pytest.fixture
def mock_file_writer() -> Mock:
    """Create a mock FileWriter."""
    return Mock(spec=FileWriter)


@pytest.fixture
def task_fixer(
    mock_provider: Mock,
    mock_validator: Mock,
    mock_prompt_builder: Mock,
    mock_diff_generator: Mock,
    mock_file_writer: Mock,
) -> TaskFixer:
    """Create a TaskFixer instance with mocked dependencies."""
    return TaskFixer(
        provider=mock_provider,
        validator=mock_validator,
        prompt_builder=mock_prompt_builder,
        diff_generator=mock_diff_generator,
        file_writer=mock_file_writer,
        subprocess_timeout=30,
    )


def test_fix_tasks_file_already_valid(
    task_fixer: TaskFixer,
    mock_validator: Mock,
    temp_dir: TemporaryDirectory,
) -> None:
    """Test that fix_tasks_file returns early when file is already valid."""
    # Arrange
    test_file = Path(temp_dir.name) / "tasks.md"
    test_file.write_text("# Tasks\n- [ ] 1. Task", encoding="utf-8")
    project_path = Path(temp_dir.name)

    valid_result = ValidationResult(
        is_valid=True,
        issues=(),
    )
    mock_validator.validate_file.return_value = valid_result

    # Act
    result = task_fixer.fix_tasks_file(test_file, project_path)

    # Assert
    assert result.success is True
    assert result.original_validation == valid_result
    assert result.fixed_validation is None
    assert result.diff_result is None
    assert result.write_result is None
    assert result.fixed_content is None
    assert result.has_changes is False
    mock_validator.validate_file.assert_called_once_with(test_file)


def test_fix_tasks_file_read_error(
    task_fixer: TaskFixer,
    mock_validator: Mock,
    temp_dir: TemporaryDirectory,
) -> None:
    """Test that fix_tasks_file handles file read errors."""
    # Arrange
    test_file = Path(temp_dir.name) / "nonexistent.md"
    project_path = Path(temp_dir.name)

    invalid_result = ValidationResult(
        is_valid=False,
        issues=(ValidationIssue(IssueType.MISSING_CHECKBOX, 1, "- Broken task", "Missing checkbox"),),
    )
    mock_validator.validate_file.return_value = invalid_result

    # Act
    result = task_fixer.fix_tasks_file(test_file, project_path)

    # Assert
    assert result.success is False
    assert result.error_message is not None
    assert "Failed to read file" in result.error_message
    assert result.original_validation == invalid_result
    assert result.fixed_validation is None


def test_fix_tasks_file_prompt_build_error(
    task_fixer: TaskFixer,
    mock_validator: Mock,
    mock_prompt_builder: Mock,
    temp_dir: TemporaryDirectory,
) -> None:
    """Test that fix_tasks_file handles prompt building errors."""
    # Arrange
    test_file = Path(temp_dir.name) / "tasks.md"
    test_file.write_text("# Tasks\nBroken task", encoding="utf-8")
    project_path = Path(temp_dir.name)

    invalid_result = ValidationResult(
        is_valid=False,
        issues=(ValidationIssue(IssueType.MISSING_CHECKBOX, 1, "- Broken task", "Missing checkbox"),),
    )
    mock_validator.validate_file.return_value = invalid_result
    mock_prompt_builder.build_prompt.side_effect = ValueError("Template not found")

    # Act
    result = task_fixer.fix_tasks_file(test_file, project_path)

    # Assert
    assert result.success is False
    assert result.error_message is not None
    assert "Failed to build prompt" in result.error_message
    assert "Template not found" in result.error_message


def test_fix_tasks_file_claude_command_failure(
    task_fixer: TaskFixer,
    mock_validator: Mock,
    mock_provider: Mock,
    temp_dir: TemporaryDirectory,
) -> None:
    """Test that fix_tasks_file handles Claude command failures."""
    # Arrange
    test_file = Path(temp_dir.name) / "tasks.md"
    test_file.write_text("# Tasks\nBroken task", encoding="utf-8")
    project_path = Path(temp_dir.name)

    invalid_result = ValidationResult(
        is_valid=False,
        issues=(ValidationIssue(IssueType.MISSING_CHECKBOX, 1, "- Broken task", "Missing checkbox"),),
    )
    mock_validator.validate_file.return_value = invalid_result

    # Mock subprocess to return failure
    with patch("spec_workflow_runner.task_fixer.fixer.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=1,
            stderr="Claude error: invalid prompt",
        )

        # Act
        result = task_fixer.fix_tasks_file(test_file, project_path)

    # Assert
    assert result.success is False
    assert result.error_message is not None
    assert "Claude command failed" in result.error_message
    assert "Claude error" in result.error_message


def test_fix_tasks_file_claude_timeout(
    task_fixer: TaskFixer,
    mock_validator: Mock,
    temp_dir: TemporaryDirectory,
) -> None:
    """Test that fix_tasks_file handles Claude command timeouts."""
    # Arrange
    test_file = Path(temp_dir.name) / "tasks.md"
    test_file.write_text("# Tasks\nBroken task", encoding="utf-8")
    project_path = Path(temp_dir.name)

    invalid_result = ValidationResult(
        is_valid=False,
        issues=(ValidationIssue(IssueType.MISSING_CHECKBOX, 1, "- Broken task", "Missing checkbox"),),
    )
    mock_validator.validate_file.return_value = invalid_result

    # Mock subprocess to raise TimeoutExpired
    with patch("spec_workflow_runner.task_fixer.fixer.subprocess.run") as mock_run:
        mock_run.side_effect = subprocess.TimeoutExpired(
            cmd="claude",
            timeout=30,
        )

        # Act
        result = task_fixer.fix_tasks_file(test_file, project_path)

    # Assert
    assert result.success is False
    assert result.error_message is not None
    assert "timed out after 30s" in result.error_message


def test_fix_tasks_file_claude_execution_error(
    task_fixer: TaskFixer,
    mock_validator: Mock,
    temp_dir: TemporaryDirectory,
) -> None:
    """Test that fix_tasks_file handles Claude execution errors."""
    # Arrange
    test_file = Path(temp_dir.name) / "tasks.md"
    test_file.write_text("# Tasks\nBroken task", encoding="utf-8")
    project_path = Path(temp_dir.name)

    invalid_result = ValidationResult(
        is_valid=False,
        issues=(ValidationIssue(IssueType.MISSING_CHECKBOX, 1, "- Broken task", "Missing checkbox"),),
    )
    mock_validator.validate_file.return_value = invalid_result

    # Mock subprocess to raise exception
    with patch("spec_workflow_runner.task_fixer.fixer.subprocess.run") as mock_run:
        mock_run.side_effect = OSError("Command not found")

        # Act
        result = task_fixer.fix_tasks_file(test_file, project_path)

    # Assert
    assert result.success is False
    assert result.error_message is not None
    assert "Failed to execute Claude" in result.error_message
    assert "Command not found" in result.error_message


def test_fix_tasks_file_validation_error(
    task_fixer: TaskFixer,
    mock_validator: Mock,
    temp_dir: TemporaryDirectory,
) -> None:
    """Test that fix_tasks_file handles validation errors on fixed content."""
    # Arrange
    test_file = Path(temp_dir.name) / "tasks.md"
    test_file.write_text("# Tasks\nBroken task", encoding="utf-8")
    project_path = Path(temp_dir.name)

    invalid_result = ValidationResult(
        is_valid=False,
        issues=(ValidationIssue(IssueType.MISSING_CHECKBOX, 1, "- Broken task", "Missing checkbox"),),
    )

    # First call returns invalid, second call raises error
    mock_validator.validate_file.side_effect = [
        invalid_result,
        ValueError("Invalid file format"),
    ]

    # Mock subprocess to return fixed content
    with patch("spec_workflow_runner.task_fixer.fixer.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="# Tasks\n- [ ] 1. Fixed task",
        )

        # Act
        result = task_fixer.fix_tasks_file(test_file, project_path)

    # Assert
    assert result.success is False
    assert result.error_message is not None
    assert "Failed to validate fixed content" in result.error_message
    assert "Invalid file format" in result.error_message


def test_fix_tasks_file_success_flow(
    task_fixer: TaskFixer,
    mock_validator: Mock,
    mock_provider: Mock,
    mock_prompt_builder: Mock,
    mock_diff_generator: Mock,
    temp_dir: TemporaryDirectory,
) -> None:
    """Test successful fix flow from validation to diff generation."""
    # Arrange
    test_file = Path(temp_dir.name) / "tasks.md"
    malformed_content = "# Tasks\nBroken task"
    fixed_content = "# Tasks\n- [ ] 1. Fixed task"
    test_file.write_text(malformed_content, encoding="utf-8")
    project_path = Path(temp_dir.name)

    # Setup validation results
    invalid_result = ValidationResult(
        is_valid=False,
        issues=(ValidationIssue(IssueType.MISSING_CHECKBOX, 1, "- Broken task", "Missing checkbox"),),
    )

    valid_result = ValidationResult(
        is_valid=True,
        issues=(),
    )

    # First call returns invalid (original), second returns valid (fixed)
    mock_validator.validate_file.side_effect = [invalid_result, valid_result]

    # Setup mock subprocess
    with patch("spec_workflow_runner.task_fixer.fixer.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=fixed_content,
        )

        # Act
        result = task_fixer.fix_tasks_file(test_file, project_path)

    # Assert
    assert result.success is True
    assert result.original_validation == invalid_result
    assert result.fixed_validation == valid_result
    assert result.fixed_content == fixed_content
    assert result.diff_result is not None
    assert result.has_changes is True
    assert result.error_message is None

    # Verify orchestration flow
    assert mock_validator.validate_file.call_count == 2
    mock_prompt_builder.build_prompt.assert_called_once()
    mock_provider.build_command.assert_called_once()
    mock_diff_generator.generate_diff.assert_called_once_with(
        original_content=malformed_content,
        fixed_content=fixed_content,
        original_label=str(test_file),
        fixed_label=f"{test_file} (fixed)",
    )


def test_fix_tasks_file_prompt_context_structure(
    task_fixer: TaskFixer,
    mock_validator: Mock,
    mock_prompt_builder: Mock,
    temp_dir: TemporaryDirectory,
) -> None:
    """Test that PromptContext is built correctly with validation results."""
    # Arrange
    test_file = Path(temp_dir.name) / "tasks.md"
    malformed_content = "# Tasks\nBroken task"
    test_file.write_text(malformed_content, encoding="utf-8")
    project_path = Path(temp_dir.name)

    invalid_result = ValidationResult(
        is_valid=False,
        issues=(ValidationIssue(IssueType.MISSING_CHECKBOX, 1, "- Broken task", "Missing checkbox"),),
    )
    mock_validator.validate_file.return_value = invalid_result

    # Mock subprocess to return fixed content
    with patch("spec_workflow_runner.task_fixer.fixer.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="# Tasks\n- [ ] 1. Fixed task",
        )

        # Act
        task_fixer.fix_tasks_file(test_file, project_path)

    # Assert - verify PromptContext was built with correct structure
    mock_prompt_builder.build_prompt.assert_called_once()
    call_args = mock_prompt_builder.build_prompt.call_args[0][0]
    assert isinstance(call_args, PromptContext)
    assert call_args.malformed_content == malformed_content
    assert call_args.validation_result == invalid_result


def test_fix_tasks_file_temp_file_cleanup(
    task_fixer: TaskFixer,
    mock_validator: Mock,
    temp_dir: TemporaryDirectory,
) -> None:
    """Test that temporary validation file is cleaned up."""
    # Arrange
    test_file = Path(temp_dir.name) / "tasks.md"
    test_file.write_text("# Tasks\nBroken task", encoding="utf-8")
    project_path = Path(temp_dir.name)
    temp_validation_file = test_file.parent / f".{test_file.name}.tmp_validation"

    invalid_result = ValidationResult(
        is_valid=False,
        issues=(ValidationIssue(IssueType.MISSING_CHECKBOX, 1, "- Broken task", "Missing checkbox"),),
    )

    valid_result = ValidationResult(
        is_valid=True,
        issues=(),
    )

    mock_validator.validate_file.side_effect = [invalid_result, valid_result]

    # Mock subprocess
    with patch("spec_workflow_runner.task_fixer.fixer.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="# Tasks\n- [ ] 1. Fixed task",
        )

        # Act
        task_fixer.fix_tasks_file(test_file, project_path)

    # Assert - temp file should be cleaned up
    assert not temp_validation_file.exists()


def test_fix_tasks_file_subprocess_timeout_value(
    mock_validator: Mock,
    mock_provider: Mock,
    mock_prompt_builder: Mock,
    mock_diff_generator: Mock,
    mock_file_writer: Mock,
    temp_dir: TemporaryDirectory,
) -> None:
    """Test that subprocess timeout is passed correctly."""
    # Arrange
    custom_timeout = 60
    task_fixer = TaskFixer(
        provider=mock_provider,
        validator=mock_validator,
        prompt_builder=mock_prompt_builder,
        diff_generator=mock_diff_generator,
        file_writer=mock_file_writer,
        subprocess_timeout=custom_timeout,
    )

    test_file = Path(temp_dir.name) / "tasks.md"
    test_file.write_text("# Tasks\nBroken task", encoding="utf-8")
    project_path = Path(temp_dir.name)

    invalid_result = ValidationResult(
        is_valid=False,
        issues=(ValidationIssue(IssueType.MISSING_CHECKBOX, 1, "- Broken task", "Missing checkbox"),),
    )
    mock_validator.validate_file.return_value = invalid_result

    # Mock subprocess
    with patch("spec_workflow_runner.task_fixer.fixer.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="# Tasks\n- [ ] 1. Fixed task",
        )

        # Act
        task_fixer.fix_tasks_file(test_file, project_path)

        # Assert
        mock_run.assert_called_once()
        call_kwargs = mock_run.call_args[1]
        assert call_kwargs["timeout"] == custom_timeout


def test_apply_fix_delegates_to_file_writer(
    task_fixer: TaskFixer,
    mock_file_writer: Mock,
    temp_dir: TemporaryDirectory,
) -> None:
    """Test that apply_fix delegates to FileWriter correctly."""
    # Arrange
    test_file = Path(temp_dir.name) / "tasks.md"
    fixed_content = "# Tasks\n- [ ] 1. Fixed task"

    expected_result = WriteResult(
        success=True,
        file_path=test_file,
        backup_path=test_file.with_suffix(".md.backup"),
    )
    mock_file_writer.write_with_backup.return_value = expected_result

    # Act
    result = task_fixer.apply_fix(test_file, fixed_content)

    # Assert
    assert result == expected_result
    mock_file_writer.write_with_backup.assert_called_once_with(test_file, fixed_content)


def test_fix_result_has_changes_property() -> None:
    """Test FixResult.has_changes property logic."""
    # Test with no diff result
    result = FixResult(
        success=True,
        original_validation=Mock(),
        fixed_validation=None,
        diff_result=None,
        write_result=None,
    )
    assert result.has_changes is False

    # Test with diff result but no changes
    result = FixResult(
        success=True,
        original_validation=Mock(),
        fixed_validation=None,
        diff_result=DiffResult(
            diff_text="",
            has_changes=False,
            lines_added=0,
            lines_removed=0,
            lines_modified=0,
        ),
        write_result=None,
    )
    assert result.has_changes is False

    # Test with diff result and changes
    result = FixResult(
        success=True,
        original_validation=Mock(),
        fixed_validation=None,
        diff_result=DiffResult(
            diff_text="- old\n+ new",
            has_changes=True,
            lines_added=1,
            lines_removed=1,
            lines_modified=0,
        ),
        write_result=None,
    )
    assert result.has_changes is True


def test_dependency_injection_all_components_used(
    task_fixer: TaskFixer,
    mock_validator: Mock,
    mock_provider: Mock,
    mock_prompt_builder: Mock,
    mock_diff_generator: Mock,
    temp_dir: TemporaryDirectory,
) -> None:
    """Test that all injected dependencies are used in the fix flow."""
    # Arrange
    test_file = Path(temp_dir.name) / "tasks.md"
    test_file.write_text("# Tasks\nBroken task", encoding="utf-8")
    project_path = Path(temp_dir.name)

    invalid_result = ValidationResult(
        is_valid=False,
        issues=(ValidationIssue(IssueType.MISSING_CHECKBOX, 1, "- Broken task", "Missing checkbox"),),
    )

    valid_result = ValidationResult(
        is_valid=True,
        issues=(),
    )

    mock_validator.validate_file.side_effect = [invalid_result, valid_result]

    with patch("spec_workflow_runner.task_fixer.fixer.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="# Tasks\n- [ ] 1. Fixed task",
        )

        # Act
        task_fixer.fix_tasks_file(test_file, project_path)

    # Assert all dependencies were used
    assert mock_validator.validate_file.called
    assert mock_prompt_builder.build_prompt.called
    assert mock_provider.build_command.called
    assert mock_diff_generator.generate_diff.called
