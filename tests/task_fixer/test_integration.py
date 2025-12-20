"""Integration tests for CLI and TUI task auto-fix functionality."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

from spec_workflow_runner.task_fixer import FixResult
from spec_workflow_runner.task_fixer.diff_generator import DiffResult
from spec_workflow_runner.task_fixer.validator import ValidationResult
from spec_workflow_runner.tui.keybindings import KeybindingHandler
from spec_workflow_runner.tui.models import AppState, ProjectState, SpecState


@pytest.fixture
def fixture_dir() -> Path:
    """Get path to test fixtures directory."""
    return Path(__file__).parent / "fixtures"


@pytest.fixture
def malformed_tasks_content(fixture_dir: Path) -> str:
    """Load malformed tasks.md content."""
    return (fixture_dir / "malformed_tasks.md").read_text()


@pytest.fixture
def valid_tasks_content(fixture_dir: Path) -> str:
    """Load valid tasks.md content."""
    return (fixture_dir / "valid_tasks.md").read_text()


@pytest.fixture
def mock_config() -> Mock:
    """Create mock config for tests."""
    config = Mock()
    config.repos_root = Path("/repos")
    config.cache_dir = Path("/cache")
    config.codex_command = ["codex", "e"]
    return config


@pytest.fixture
def app_state_with_spec() -> AppState:
    """Create app state with a selected spec."""
    spec = SpecState(
        name="test-spec",
        path=Path("/repos/project/.spec-workflow/specs/test-spec"),
        total_tasks=10,
        completed_tasks=5,
        in_progress_tasks=2,
        pending_tasks=3,
    )
    project = ProjectState(
        path=Path("/repos/project"),
        name="project",
        specs=[spec],
    )
    state = AppState()
    state.projects = [project]
    state.selected_project_index = 0
    state.selected_spec_index = 0
    return state


class TestCLIIntegration:
    """Integration tests for CLI --fix flag."""

    @patch("spec_workflow_runner.tui.cli.load_config")
    @patch("spec_workflow_runner.tui.cli.discover_specs")
    @patch("spec_workflow_runner.tui.cli.create_task_fixer")
    @patch("builtins.input")
    def test_cli_fix_success_with_changes(
        self,
        mock_input: Mock,
        mock_create_fixer: Mock,
        mock_discover: Mock,
        mock_load_config: Mock,
        tmp_path: Path,
        malformed_tasks_content: str,
    ) -> None:
        """Test CLI --fix with successful fix and user confirmation."""
        # Setup
        from spec_workflow_runner.tui.cli import _handle_fix_command

        spec_path = tmp_path / "specs" / "test-spec"
        spec_path.mkdir(parents=True)
        tasks_file = spec_path / "tasks.md"
        tasks_file.write_text(malformed_tasks_content)

        # Mock config and specs
        config = Mock()
        mock_load_config.return_value = config
        mock_discover.return_value = [("test-spec", spec_path)]

        # Mock fixer to return success with changes
        mock_fixer = Mock()
        fix_result = FixResult(
            success=True,
            has_changes=True,
            fixed_content="# Fixed content",
            validation_result=ValidationResult(is_valid=True, issues=[]),
            diff_result=DiffResult(
                has_changes=True,
                diff_text="diff output",
                changes_summary={"added": 5, "removed": 3, "modified": 2},
            ),
            error_message=None,
        )
        mock_fixer.fix_tasks_file.return_value = fix_result

        # Mock apply_fix to succeed
        from spec_workflow_runner.task_fixer.file_writer import WriteResult
        write_result = WriteResult(
            success=True,
            backup_path=tasks_file.with_suffix(".md.backup"),
            error_message=None,
        )
        mock_fixer.apply_fix.return_value = write_result

        mock_create_fixer.return_value = mock_fixer

        # User confirms
        mock_input.return_value = "y"

        # Execute
        exit_code = _handle_fix_command("test-spec", tmp_path / "config.json")

        # Verify
        assert exit_code == 0
        mock_fixer.fix_tasks_file.assert_called_once()
        mock_fixer.apply_fix.assert_called_once()

    @patch("spec_workflow_runner.tui.cli.load_config")
    @patch("spec_workflow_runner.tui.cli.discover_specs")
    @patch("spec_workflow_runner.tui.cli.create_task_fixer")
    @patch("builtins.input")
    def test_cli_fix_user_cancels(
        self,
        mock_input: Mock,
        mock_create_fixer: Mock,
        mock_discover: Mock,
        mock_load_config: Mock,
        tmp_path: Path,
        malformed_tasks_content: str,
    ) -> None:
        """Test CLI --fix when user cancels the operation."""
        # Setup
        from spec_workflow_runner.tui.cli import _handle_fix_command

        spec_path = tmp_path / "specs" / "test-spec"
        spec_path.mkdir(parents=True)
        tasks_file = spec_path / "tasks.md"
        tasks_file.write_text(malformed_tasks_content)

        config = Mock()
        mock_load_config.return_value = config
        mock_discover.return_value = [("test-spec", spec_path)]

        mock_fixer = Mock()
        fix_result = FixResult(
            success=True,
            has_changes=True,
            fixed_content="# Fixed content",
            validation_result=ValidationResult(is_valid=True, issues=[]),
            diff_result=DiffResult(
                has_changes=True,
                diff_text="diff output",
                changes_summary={"added": 5, "removed": 3, "modified": 2},
            ),
            error_message=None,
        )
        mock_fixer.fix_tasks_file.return_value = fix_result
        mock_create_fixer.return_value = mock_fixer

        # User declines
        mock_input.return_value = "n"

        # Execute
        exit_code = _handle_fix_command("test-spec", tmp_path / "config.json")

        # Verify - should exit 0 but not apply
        assert exit_code == 0
        mock_fixer.fix_tasks_file.assert_called_once()
        mock_fixer.apply_fix.assert_not_called()

    @patch("spec_workflow_runner.tui.cli.load_config")
    @patch("spec_workflow_runner.tui.cli.discover_specs")
    @patch("spec_workflow_runner.tui.cli.create_task_fixer")
    def test_cli_fix_no_changes_needed(
        self,
        mock_create_fixer: Mock,
        mock_discover: Mock,
        mock_load_config: Mock,
        tmp_path: Path,
        valid_tasks_content: str,
    ) -> None:
        """Test CLI --fix when file is already valid."""
        # Setup
        from spec_workflow_runner.tui.cli import _handle_fix_command

        spec_path = tmp_path / "specs" / "test-spec"
        spec_path.mkdir(parents=True)
        tasks_file = spec_path / "tasks.md"
        tasks_file.write_text(valid_tasks_content)

        config = Mock()
        mock_load_config.return_value = config
        mock_discover.return_value = [("test-spec", spec_path)]

        mock_fixer = Mock()
        fix_result = FixResult(
            success=True,
            has_changes=False,
            fixed_content=valid_tasks_content,
            validation_result=ValidationResult(is_valid=True, issues=[]),
            diff_result=None,
            error_message=None,
        )
        mock_fixer.fix_tasks_file.return_value = fix_result
        mock_create_fixer.return_value = mock_fixer

        # Execute
        exit_code = _handle_fix_command("test-spec", tmp_path / "config.json")

        # Verify
        assert exit_code == 0
        mock_fixer.fix_tasks_file.assert_called_once()
        mock_fixer.apply_fix.assert_not_called()

    @patch("spec_workflow_runner.tui.cli.load_config")
    @patch("spec_workflow_runner.tui.cli.discover_specs")
    def test_cli_fix_spec_not_found(
        self,
        mock_discover: Mock,
        mock_load_config: Mock,
        tmp_path: Path,
    ) -> None:
        """Test CLI --fix with invalid spec name."""
        # Setup
        from spec_workflow_runner.tui.cli import _handle_fix_command

        config = Mock()
        mock_load_config.return_value = config
        mock_discover.return_value = [("other-spec", tmp_path / "other-spec")]

        # Execute
        exit_code = _handle_fix_command("nonexistent-spec", tmp_path / "config.json")

        # Verify - should return error code
        assert exit_code == 1

    @patch("spec_workflow_runner.tui.cli.load_config")
    @patch("spec_workflow_runner.tui.cli.discover_specs")
    def test_cli_fix_tasks_file_missing(
        self,
        mock_discover: Mock,
        mock_load_config: Mock,
        tmp_path: Path,
    ) -> None:
        """Test CLI --fix when tasks.md doesn't exist."""
        # Setup
        from spec_workflow_runner.tui.cli import _handle_fix_command

        spec_path = tmp_path / "specs" / "test-spec"
        spec_path.mkdir(parents=True)
        # Don't create tasks.md

        config = Mock()
        mock_load_config.return_value = config
        mock_discover.return_value = [("test-spec", spec_path)]

        # Execute
        exit_code = _handle_fix_command("test-spec", tmp_path / "config.json")

        # Verify
        assert exit_code == 1

    @patch("spec_workflow_runner.tui.cli.load_config")
    @patch("spec_workflow_runner.tui.cli.discover_specs")
    @patch("spec_workflow_runner.tui.cli.create_task_fixer")
    def test_cli_fix_error_during_fix(
        self,
        mock_create_fixer: Mock,
        mock_discover: Mock,
        mock_load_config: Mock,
        tmp_path: Path,
        malformed_tasks_content: str,
    ) -> None:
        """Test CLI --fix when fix operation fails."""
        # Setup
        from spec_workflow_runner.tui.cli import _handle_fix_command

        spec_path = tmp_path / "specs" / "test-spec"
        spec_path.mkdir(parents=True)
        tasks_file = spec_path / "tasks.md"
        tasks_file.write_text(malformed_tasks_content)

        config = Mock()
        mock_load_config.return_value = config
        mock_discover.return_value = [("test-spec", spec_path)]

        mock_fixer = Mock()
        fix_result = FixResult(
            success=False,
            has_changes=False,
            fixed_content=None,
            validation_result=None,
            diff_result=None,
            error_message="Claude API error",
        )
        mock_fixer.fix_tasks_file.return_value = fix_result
        mock_create_fixer.return_value = mock_fixer

        # Execute
        exit_code = _handle_fix_command("test-spec", tmp_path / "config.json")

        # Verify
        assert exit_code == 1


class TestTUIIntegration:
    """Integration tests for TUI F keybinding."""

    @patch("spec_workflow_runner.tui.keybindings.create_task_fixer")
    @patch("spec_workflow_runner.tui.keybindings.create_provider")
    def test_tui_fix_success(
        self,
        mock_create_provider: Mock,
        mock_create_fixer: Mock,
        app_state_with_spec: AppState,
        mock_config: Mock,
        tmp_path: Path,
        malformed_tasks_content: str,
    ) -> None:
        """Test TUI F key triggers fix successfully."""
        # Setup
        project = app_state_with_spec.selected_project
        spec = app_state_with_spec.selected_spec

        # Create tasks.md file
        tasks_file = project.path / ".spec-workflow" / "specs" / spec.name / "tasks.md"
        tasks_file.parent.mkdir(parents=True, exist_ok=True)
        tasks_file.write_text(malformed_tasks_content)

        # Mock provider
        mock_provider = Mock()
        mock_create_provider.return_value = mock_provider

        # Mock fixer
        mock_fixer = Mock()
        fix_result = FixResult(
            success=True,
            has_changes=True,
            fixed_content="# Fixed content",
            validation_result=ValidationResult(is_valid=True, issues=[]),
            diff_result=DiffResult(
                has_changes=True,
                diff_text="diff output",
                changes_summary={"added": 5, "removed": 3, "modified": 2},
            ),
            error_message=None,
        )
        mock_fixer.fix_tasks_file.return_value = fix_result

        from spec_workflow_runner.task_fixer.file_writer import WriteResult
        write_result = WriteResult(
            success=True,
            backup_path=tasks_file.with_suffix(".md.backup"),
            error_message=None,
        )
        mock_fixer.apply_fix.return_value = write_result
        mock_create_fixer.return_value = mock_fixer

        # Execute
        mock_runner_manager = Mock()
        handler = KeybindingHandler(app_state_with_spec, mock_runner_manager, mock_config)
        handled, message = handler.handle_key("F")

        # Verify
        assert handled is True
        assert message is not None
        assert "Fixed" in message or "added" in message
        mock_fixer.fix_tasks_file.assert_called_once()
        mock_fixer.apply_fix.assert_called_once()

    @patch("spec_workflow_runner.tui.keybindings.create_task_fixer")
    @patch("spec_workflow_runner.tui.keybindings.create_provider")
    def test_tui_fix_no_changes(
        self,
        mock_create_provider: Mock,
        mock_create_fixer: Mock,
        app_state_with_spec: AppState,
        mock_config: Mock,
        tmp_path: Path,
        valid_tasks_content: str,
    ) -> None:
        """Test TUI F key when no changes needed."""
        # Setup
        project = app_state_with_spec.selected_project
        spec = app_state_with_spec.selected_spec

        tasks_file = project.path / ".spec-workflow" / "specs" / spec.name / "tasks.md"
        tasks_file.parent.mkdir(parents=True, exist_ok=True)
        tasks_file.write_text(valid_tasks_content)

        mock_provider = Mock()
        mock_create_provider.return_value = mock_provider

        mock_fixer = Mock()
        fix_result = FixResult(
            success=True,
            has_changes=False,
            fixed_content=valid_tasks_content,
            validation_result=ValidationResult(is_valid=True, issues=[]),
            diff_result=None,
            error_message=None,
        )
        mock_fixer.fix_tasks_file.return_value = fix_result
        mock_create_fixer.return_value = mock_fixer

        # Execute
        mock_runner_manager = Mock()
        handler = KeybindingHandler(app_state_with_spec, mock_runner_manager, mock_config)
        handled, message = handler.handle_key("F")

        # Verify
        assert handled is True
        assert message is not None
        assert "No changes" in message
        mock_fixer.fix_tasks_file.assert_called_once()
        mock_fixer.apply_fix.assert_not_called()

    def test_tui_fix_no_spec_selected(
        self,
        mock_config: Mock,
    ) -> None:
        """Test TUI F key with no spec selected."""
        # Setup - empty app state
        app_state = AppState()
        app_state.projects = []

        mock_runner_manager = Mock()
        handler = KeybindingHandler(app_state, mock_runner_manager, mock_config)

        # Execute
        handled, message = handler.handle_key("F")

        # Verify
        assert handled is True
        assert message is not None
        assert "Error" in message
        assert "No spec selected" in message

    @patch("spec_workflow_runner.tui.keybindings.create_provider")
    def test_tui_fix_tasks_file_not_found(
        self,
        mock_create_provider: Mock,
        app_state_with_spec: AppState,
        mock_config: Mock,
    ) -> None:
        """Test TUI F key when tasks.md doesn't exist."""
        # Setup - don't create tasks.md file
        mock_provider = Mock()
        mock_create_provider.return_value = mock_provider

        # Execute
        mock_runner_manager = Mock()
        handler = KeybindingHandler(app_state_with_spec, mock_runner_manager, mock_config)
        handled, message = handler.handle_key("F")

        # Verify
        assert handled is True
        assert message is not None
        assert "Error" in message
        assert "not found" in message

    @patch("spec_workflow_runner.tui.keybindings.create_task_fixer")
    @patch("spec_workflow_runner.tui.keybindings.create_provider")
    def test_tui_fix_error_during_fix(
        self,
        mock_create_provider: Mock,
        mock_create_fixer: Mock,
        app_state_with_spec: AppState,
        mock_config: Mock,
        tmp_path: Path,
        malformed_tasks_content: str,
    ) -> None:
        """Test TUI F key when fix operation fails."""
        # Setup
        project = app_state_with_spec.selected_project
        spec = app_state_with_spec.selected_spec

        tasks_file = project.path / ".spec-workflow" / "specs" / spec.name / "tasks.md"
        tasks_file.parent.mkdir(parents=True, exist_ok=True)
        tasks_file.write_text(malformed_tasks_content)

        mock_provider = Mock()
        mock_create_provider.return_value = mock_provider

        mock_fixer = Mock()
        fix_result = FixResult(
            success=False,
            has_changes=False,
            fixed_content=None,
            validation_result=None,
            diff_result=None,
            error_message="Validation failed",
        )
        mock_fixer.fix_tasks_file.return_value = fix_result
        mock_create_fixer.return_value = mock_fixer

        # Execute
        mock_runner_manager = Mock()
        handler = KeybindingHandler(app_state_with_spec, mock_runner_manager, mock_config)
        handled, message = handler.handle_key("F")

        # Verify
        assert handled is True
        assert message is not None
        assert "Error" in message
        assert "Validation failed" in message

    @patch("spec_workflow_runner.tui.keybindings.create_task_fixer")
    @patch("spec_workflow_runner.tui.keybindings.create_provider")
    def test_tui_fix_write_error(
        self,
        mock_create_provider: Mock,
        mock_create_fixer: Mock,
        app_state_with_spec: AppState,
        mock_config: Mock,
        tmp_path: Path,
        malformed_tasks_content: str,
    ) -> None:
        """Test TUI F key when write operation fails."""
        # Setup
        project = app_state_with_spec.selected_project
        spec = app_state_with_spec.selected_spec

        tasks_file = project.path / ".spec-workflow" / "specs" / spec.name / "tasks.md"
        tasks_file.parent.mkdir(parents=True, exist_ok=True)
        tasks_file.write_text(malformed_tasks_content)

        mock_provider = Mock()
        mock_create_provider.return_value = mock_provider

        mock_fixer = Mock()
        fix_result = FixResult(
            success=True,
            has_changes=True,
            fixed_content="# Fixed content",
            validation_result=ValidationResult(is_valid=True, issues=[]),
            diff_result=DiffResult(
                has_changes=True,
                diff_text="diff output",
                changes_summary={"added": 5, "removed": 3, "modified": 2},
            ),
            error_message=None,
        )
        mock_fixer.fix_tasks_file.return_value = fix_result

        from spec_workflow_runner.task_fixer.file_writer import WriteResult
        write_result = WriteResult(
            success=False,
            backup_path=None,
            error_message="Permission denied",
        )
        mock_fixer.apply_fix.return_value = write_result
        mock_create_fixer.return_value = mock_fixer

        # Execute
        mock_runner_manager = Mock()
        handler = KeybindingHandler(app_state_with_spec, mock_runner_manager, mock_config)
        handled, message = handler.handle_key("F")

        # Verify
        assert handled is True
        assert message is not None
        assert "Error writing" in message
        assert "Permission denied" in message
