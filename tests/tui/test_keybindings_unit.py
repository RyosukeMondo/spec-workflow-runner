"""Unit tests for KeybindingHandler."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from spec_workflow_runner.tui.keybindings import KeybindingHandler
from spec_workflow_runner.tui.models import (
    AppState,
    ProjectState,
    RunnerState,
    RunnerStatus,
    SpecState,
)


@pytest.fixture
def mock_config() -> Mock:
    """Create mock config."""
    config = Mock()
    config.repos_root = Path("/repos")
    config.cache_dir = Path("/cache")
    config.codex_command = ("codex", "e")
    return config


@pytest.fixture
def mock_runner_manager() -> Mock:
    """Create mock runner manager."""
    return Mock()


@pytest.fixture
def app_state() -> AppState:
    """Create app state with sample data."""
    project1 = ProjectState(
        path=Path("/repos/project1"),
        name="project1",
        specs=[
            SpecState(
                name="spec1",
                path=Path("/repos/project1/.spec-workflow/specs/spec1"),
                total_tasks=10,
                completed_tasks=5,
                in_progress_tasks=2,
                pending_tasks=3,
            ),
            SpecState(
                name="spec2",
                path=Path("/repos/project1/.spec-workflow/specs/spec2"),
                total_tasks=5,
                completed_tasks=5,
                in_progress_tasks=0,
                pending_tasks=0,
            ),
        ],
    )
    project2 = ProjectState(
        path=Path("/repos/project2"),
        name="project2",
        specs=[],
    )

    state = AppState()
    state.projects = [project1, project2]
    return state


class TestHelpPanel:
    """Tests for help panel toggle."""

    def test_help_toggle_shows_panel(
        self, app_state: AppState, mock_runner_manager: Mock, mock_config: Mock
    ) -> None:
        """Help command should toggle panel visibility."""
        handler = KeybindingHandler(app_state, mock_runner_manager, mock_config)

        assert app_state.help_panel_visible is False

        handled, message = handler.handle_key("?")

        assert handled is True
        assert "visible" in message.lower()
        assert app_state.help_panel_visible is True

    def test_help_toggle_hides_panel(
        self, app_state: AppState, mock_runner_manager: Mock, mock_config: Mock
    ) -> None:
        """Help command should toggle panel off."""
        handler = KeybindingHandler(app_state, mock_runner_manager, mock_config)
        app_state.help_panel_visible = True

        handled, message = handler.handle_key("?")

        assert handled is True
        assert "hidden" in message.lower()
        assert app_state.help_panel_visible is False


class TestConfigCommand:
    """Tests for config command."""

    def test_config_shows_repos_and_cache(
        self, app_state: AppState, mock_runner_manager: Mock, mock_config: Mock
    ) -> None:
        """Config command should show configuration info."""
        handler = KeybindingHandler(app_state, mock_runner_manager, mock_config)

        handled, message = handler.handle_key("c")

        assert handled is True
        assert "/repos" in message
        assert "/cache" in message


class TestStartRunner:
    """Tests for start runner functionality."""

    def test_start_runner_with_no_selection(
        self, app_state: AppState, mock_runner_manager: Mock, mock_config: Mock
    ) -> None:
        """Start runner should fail with no selection."""
        handler = KeybindingHandler(app_state, mock_runner_manager, mock_config)

        handled, message = handler.handle_key("s")

        assert handled is True
        assert "Error" in message
        assert "No spec selected" in message

    def test_start_runner_with_completed_spec(
        self, app_state: AppState, mock_runner_manager: Mock, mock_config: Mock
    ) -> None:
        """Start runner should fail for completed spec."""
        app_state.selected_project_index = 0
        app_state.selected_spec_index = 1  # spec2 is complete

        handler = KeybindingHandler(app_state, mock_runner_manager, mock_config)

        handled, message = handler.handle_key("s")

        assert handled is True
        assert "Error" in message
        assert "No unfinished tasks" in message

    def test_start_runner_with_active_runner(
        self, app_state: AppState, mock_runner_manager: Mock, mock_config: Mock
    ) -> None:
        """Start runner should fail if already running."""
        app_state.selected_project_index = 0
        app_state.selected_spec_index = 0

        # Add running runner
        app_state.projects[0].specs[0].runner = RunnerState(
            runner_id="123",
            project_path=Path("/repos/project1"),
            spec_name="spec1",
            provider="Codex",
            model="gpt-5.1-codex",
            pid=12345,
            status=RunnerStatus.RUNNING,
            started_at=Mock(),
            baseline_commit="abc123",
        )

        handler = KeybindingHandler(app_state, mock_runner_manager, mock_config)

        handled, message = handler.handle_key("s")

        assert handled is True
        assert "Error" in message
        assert "already active" in message

    def test_start_runner_success(
        self, app_state: AppState, mock_runner_manager: Mock, mock_config: Mock
    ) -> None:
        """Start runner should succeed with valid spec."""
        app_state.selected_project_index = 0
        app_state.selected_spec_index = 0

        with patch("spec_workflow_runner.providers.CodexProvider") as mock_codex:
            mock_provider = Mock()
            mock_codex.return_value = mock_provider
            mock_codex.SUPPORTED_MODELS = ("gpt-5.1-codex-max",)

            handler = KeybindingHandler(app_state, mock_runner_manager, mock_config)

            handled, message = handler.handle_key("s")

            assert handled is True
            assert "Started runner" in message
            mock_runner_manager.start_runner.assert_called_once()

    def test_start_runner_handles_exception(
        self, app_state: AppState, mock_runner_manager: Mock, mock_config: Mock
    ) -> None:
        """Start runner should handle exceptions gracefully."""
        app_state.selected_project_index = 0
        app_state.selected_spec_index = 0

        with patch("spec_workflow_runner.providers.CodexProvider") as mock_codex:
            mock_provider = Mock()
            mock_codex.return_value = mock_provider
            mock_codex.SUPPORTED_MODELS = ("gpt-5.1-codex-max",)

            mock_runner_manager.start_runner.side_effect = RuntimeError("Test error")

            handler = KeybindingHandler(app_state, mock_runner_manager, mock_config)

            handled, message = handler.handle_key("s")

            assert handled is True
            assert "Error starting runner" in message


class TestRestartRunner:
    """Tests for restart runner functionality."""

    def test_restart_with_no_selection(
        self, app_state: AppState, mock_runner_manager: Mock, mock_config: Mock
    ) -> None:
        """Restart should fail with no selection."""
        handler = KeybindingHandler(app_state, mock_runner_manager, mock_config)

        handled, message = handler.handle_key("r")

        assert handled is True
        assert "Error" in message
        assert "No spec selected" in message

    def test_restart_with_no_active_runner(
        self, app_state: AppState, mock_runner_manager: Mock, mock_config: Mock
    ) -> None:
        """Restart should fail with no active runner."""
        app_state.selected_project_index = 0
        app_state.selected_spec_index = 0

        handler = KeybindingHandler(app_state, mock_runner_manager, mock_config)

        handled, message = handler.handle_key("r")

        assert handled is True
        assert "Error" in message
        assert "No runner active" in message

    def test_restart_runner_success(
        self, app_state: AppState, mock_runner_manager: Mock, mock_config: Mock
    ) -> None:
        """Restart should stop and start runner."""
        app_state.selected_project_index = 0
        app_state.selected_spec_index = 0

        # Add running runner
        app_state.projects[0].specs[0].runner = RunnerState(
            runner_id="123",
            project_path=Path("/repos/project1"),
            spec_name="spec1",
            provider="Codex",
            model="gpt-5.1-codex",
            pid=12345,
            status=RunnerStatus.RUNNING,
            started_at=Mock(),
            baseline_commit="abc123",
        )

        with patch("spec_workflow_runner.providers.CodexProvider") as mock_codex:
            mock_provider = Mock()
            mock_codex.return_value = mock_provider
            mock_codex.SUPPORTED_MODELS = ("gpt-5.1-codex-max",)

            handler = KeybindingHandler(app_state, mock_runner_manager, mock_config)

            handled, message = handler.handle_key("r")

            assert handled is True
            assert "Restarted runner" in message
            mock_runner_manager.stop_runner.assert_called_once_with("123")
            mock_runner_manager.start_runner.assert_called_once()

    def test_restart_runner_handles_exception(
        self, app_state: AppState, mock_runner_manager: Mock, mock_config: Mock
    ) -> None:
        """Restart should handle exceptions gracefully."""
        app_state.selected_project_index = 0
        app_state.selected_spec_index = 0

        # Add running runner
        app_state.projects[0].specs[0].runner = RunnerState(
            runner_id="123",
            project_path=Path("/repos/project1"),
            spec_name="spec1",
            provider="Codex",
            model="gpt-5.1-codex",
            pid=12345,
            status=RunnerStatus.RUNNING,
            started_at=Mock(),
            baseline_commit="abc123",
        )

        mock_runner_manager.stop_runner.side_effect = RuntimeError("Test error")

        handler = KeybindingHandler(app_state, mock_runner_manager, mock_config)

        handled, message = handler.handle_key("r")

        assert handled is True
        assert "Error restarting runner" in message


class TestSelectHandler:
    """Tests for select/enter handler."""

    def test_select_with_no_projects(self, mock_runner_manager: Mock, mock_config: Mock) -> None:
        """Select with no projects should handle gracefully."""
        app_state = AppState()
        handler = KeybindingHandler(app_state, mock_runner_manager, mock_config)

        handled, message = handler.handle_key("\n")

        assert handled is True

    def test_select_expands_to_first_spec(
        self, app_state: AppState, mock_runner_manager: Mock, mock_config: Mock
    ) -> None:
        """Select on project should expand to first spec."""
        app_state.selected_project_index = 0
        app_state.selected_spec_index = None

        handler = KeybindingHandler(app_state, mock_runner_manager, mock_config)

        handled, message = handler.handle_key("\n")

        assert handled is True
        assert app_state.selected_spec_index == 0
        assert "spec1" in message

    def test_select_on_project_with_no_specs(
        self, app_state: AppState, mock_runner_manager: Mock, mock_config: Mock
    ) -> None:
        """Select on project with no specs."""
        app_state.selected_project_index = 1  # project2 has no specs
        app_state.selected_spec_index = None

        handler = KeybindingHandler(app_state, mock_runner_manager, mock_config)

        handled, message = handler.handle_key("\n")

        assert handled is True
        assert "No specs in project" in message

    def test_select_on_already_selected_spec(
        self, app_state: AppState, mock_runner_manager: Mock, mock_config: Mock
    ) -> None:
        """Select on already selected spec."""
        app_state.selected_project_index = 0
        app_state.selected_spec_index = 0

        handler = KeybindingHandler(app_state, mock_runner_manager, mock_config)

        handled, message = handler.handle_key("\n")

        assert handled is True
        assert "spec1" in message


class TestFilterMode:
    """Tests for filter mode."""

    def test_filter_mode_activation(
        self, app_state: AppState, mock_runner_manager: Mock, mock_config: Mock
    ) -> None:
        """Filter mode should activate."""
        handler = KeybindingHandler(app_state, mock_runner_manager, mock_config)

        handled, message = handler.handle_key("/")

        assert handled is True
        assert app_state.filter_mode is True
        assert "Filter mode" in message


class TestJumpHandlers:
    """Tests for jump to top/bottom."""

    def test_jump_top_with_no_projects(self, mock_runner_manager: Mock, mock_config: Mock) -> None:
        """Jump top with no projects."""
        app_state = AppState()
        handler = KeybindingHandler(app_state, mock_runner_manager, mock_config)

        handled, message = handler.handle_key("g")

        assert handled is True

    def test_jump_bottom_selects_last_spec(
        self, app_state: AppState, mock_runner_manager: Mock, mock_config: Mock
    ) -> None:
        """Jump bottom should select last project."""
        handler = KeybindingHandler(app_state, mock_runner_manager, mock_config)

        handled, message = handler.handle_key("G")

        assert handled is True
        assert app_state.selected_project_index == 1  # Last project (project2)
        assert app_state.selected_spec_index is None  # No specs in project2

    def test_jump_bottom_with_project_no_specs(
        self, app_state: AppState, mock_runner_manager: Mock, mock_config: Mock
    ) -> None:
        """Jump bottom to project with no specs."""
        # Make project1 have no specs
        app_state.projects[0].specs = []

        handler = KeybindingHandler(app_state, mock_runner_manager, mock_config)

        handled, message = handler.handle_key("G")

        assert handled is True
        assert app_state.selected_spec_index is None


class TestUnassignedKeys:
    """Tests for unassigned key feedback."""

    def test_unassigned_printable_key(
        self, app_state: AppState, mock_runner_manager: Mock, mock_config: Mock
    ) -> None:
        """Unassigned printable key should show feedback."""
        handler = KeybindingHandler(app_state, mock_runner_manager, mock_config)

        handled, message = handler.handle_key("z")

        assert handled is True
        assert message is not None
        assert "not assigned" in message
        assert "z" in message

    def test_unassigned_left_arrow(
        self, app_state: AppState, mock_runner_manager: Mock, mock_config: Mock
    ) -> None:
        """Left arrow key should show not assigned."""
        handler = KeybindingHandler(app_state, mock_runner_manager, mock_config)

        handled, message = handler.handle_key("left")

        assert handled is True
        assert message is not None
        assert "not assigned" in message
        assert "left" in message

    def test_unassigned_right_arrow(
        self, app_state: AppState, mock_runner_manager: Mock, mock_config: Mock
    ) -> None:
        """Right arrow key should show not assigned."""
        handler = KeybindingHandler(app_state, mock_runner_manager, mock_config)

        handled, message = handler.handle_key("right")

        assert handled is True
        assert message is not None
        assert "not assigned" in message
        assert "right" in message

    def test_assigned_arrow_keys_work(
        self, app_state: AppState, mock_runner_manager: Mock, mock_config: Mock
    ) -> None:
        """Arrow keys up and down should be assigned."""
        handler = KeybindingHandler(app_state, mock_runner_manager, mock_config)

        # Test up arrow
        handled, message = handler.handle_key("up")
        assert handled is True
        # Should not say "not assigned"
        if message:
            assert "not assigned" not in message

        # Test down arrow
        handled, message = handler.handle_key("down")
        assert handled is True
        # Should not say "not assigned"
        if message:
            assert "not assigned" not in message

    def test_vim_keys_work(
        self, app_state: AppState, mock_runner_manager: Mock, mock_config: Mock
    ) -> None:
        """Vim-style j/k keys should be assigned."""
        handler = KeybindingHandler(app_state, mock_runner_manager, mock_config)

        # Test k (up)
        handled, message = handler.handle_key("k")
        assert handled is True
        if message:
            assert "not assigned" not in message

        # Test j (down)
        handled, message = handler.handle_key("j")
        assert handled is True
        if message:
            assert "not assigned" not in message
