"""Integration tests for complete TUI workflows.

This module tests end-to-end workflows including:
- Launch TUI, navigate tree, start/stop runners
- State transitions and UI updates
- Error scenarios and recovery
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from spec_workflow_runner.tui.app import TUIApp
from spec_workflow_runner.tui.keybindings import KeybindingHandler
from spec_workflow_runner.tui.runner_manager import RunnerManager
from spec_workflow_runner.tui.state import (
    AppState,
    ProjectState,
    RunnerState,
    RunnerStatus,
    SpecState,
    StateUpdate,
)
from spec_workflow_runner.utils import Config, TaskStats


@pytest.fixture
def mock_config(tmp_path) -> Config:
    """Create a mock config for testing."""
    return Config(
        repos_root=tmp_path / "repos",
        cache_dir=tmp_path / "cache",
        spec_workflow_dir_name=".spec-workflow",
        specs_subdir="specs",
        tasks_filename="tasks.md",
        log_dir_name="Implementation Logs",
        codex_command=["claude", "--skip-permissions"],
        prompt_template="Work on spec: {spec_name}",
        no_commit_limit=10,
        log_file_template="{spec_name}_{timestamp}.log",
        ignore_dirs=("node_modules", ".git", "__pycache__"),
        monitor_refresh_seconds=5,
        cache_max_age_days=7,
        tui_refresh_seconds=2,
        tui_log_tail_lines=200,
        tui_min_terminal_cols=80,
        tui_min_terminal_rows=24,
    )


@pytest.fixture
def mock_config_path() -> Path:
    """Create a mock config path."""
    return Path("/home/user/config.json")


@pytest.fixture
def sample_projects() -> list[ProjectState]:
    """Create sample projects for testing."""
    spec1 = SpecState(
        name="feature-auth",
        path=Path("/home/user/repos/project1/.spec-workflow/specs/feature-auth"),
        total_tasks=10,
        completed_tasks=5,
        in_progress_tasks=2,
        pending_tasks=3,
        runner=None,
    )
    spec2 = SpecState(
        name="feature-api",
        path=Path("/home/user/repos/project1/.spec-workflow/specs/feature-api"),
        total_tasks=15,
        completed_tasks=15,
        in_progress_tasks=0,
        pending_tasks=0,
        runner=None,
    )
    spec3 = SpecState(
        name="feature-ui",
        path=Path("/home/user/repos/project2/.spec-workflow/specs/feature-ui"),
        total_tasks=8,
        completed_tasks=0,
        in_progress_tasks=1,
        pending_tasks=7,
        runner=None,
    )

    project1 = ProjectState(
        path=Path("/home/user/repos/project1"),
        name="project1",
        specs=[spec1, spec2],
    )
    project2 = ProjectState(
        path=Path("/home/user/repos/project2"),
        name="project2",
        specs=[spec3],
    )

    return [project1, project2]


@pytest.fixture
def sample_runner() -> RunnerState:
    """Create a sample runner state."""
    return RunnerState(
        runner_id="test-runner-1",
        project_path=Path("/home/user/repos/project1"),
        spec_name="feature-auth",
        provider="anthropic",
        model="claude-opus-4",
        pid=12345,
        status=RunnerStatus.RUNNING,
        started_at=datetime(2024, 1, 1, 12, 0, 0),
        baseline_commit="abc123",
        last_commit_hash="def456",
        last_commit_message="feat: add authentication",
    )


class TestTUIAppInitialization:
    """Test TUI app initialization."""

    def test_app_initialization(self, mock_config, mock_config_path):
        """Test TUIApp initializes with correct state."""
        with patch("spec_workflow_runner.tui.app.get_terminal_size", return_value=(100, 30)):
            app = TUIApp(mock_config, mock_config_path)

            assert app.config == mock_config
            assert app.config_path == mock_config_path
            assert isinstance(app.app_state, AppState)
            assert app.should_quit is False
            assert isinstance(app.runner_manager, RunnerManager)
            assert isinstance(app.keybinding_handler, KeybindingHandler)
            assert app.terminal_width == 100
            assert app.terminal_height == 30

    def test_app_initializes_with_small_terminal(self, mock_config, mock_config_path):
        """Test TUI handles small terminal on initialization."""
        with patch("spec_workflow_runner.tui.app.get_terminal_size", return_value=(60, 20)):
            app = TUIApp(mock_config, mock_config_path)

            assert app.terminal_width == 60
            assert app.terminal_height == 20


class TestNavigationWorkflow:
    """Test navigation workflows."""

    def test_navigate_down_through_tree(self, mock_config, mock_config_path, sample_projects):
        """Test navigating down through project/spec tree."""
        with patch("spec_workflow_runner.tui.app.get_terminal_size", return_value=(100, 30)):
            app = TUIApp(mock_config, mock_config_path)
            app.app_state.projects = sample_projects

            # Initially nothing selected
            assert app.app_state.selected_project_index is None
            assert app.app_state.selected_spec_index is None

            # Move down - should select first project
            handled, msg = app.keybinding_handler.handle_key("down")
            assert handled is True
            assert app.app_state.selected_project_index == 0
            assert app.app_state.selected_spec_index is None

            # Move down again - should select first spec
            handled, msg = app.keybinding_handler.handle_key("down")
            assert handled is True
            assert app.app_state.selected_project_index == 0
            assert app.app_state.selected_spec_index == 0

            # Move down - should select second spec
            handled, msg = app.keybinding_handler.handle_key("down")
            assert handled is True
            assert app.app_state.selected_project_index == 0
            assert app.app_state.selected_spec_index == 1

            # Move down - should move to second project
            handled, msg = app.keybinding_handler.handle_key("down")
            assert handled is True
            assert app.app_state.selected_project_index == 1
            assert app.app_state.selected_spec_index is None

    def test_navigate_up_through_tree(self, mock_config, mock_config_path, sample_projects):
        """Test navigating up through project/spec tree."""
        with patch("spec_workflow_runner.tui.app.get_terminal_size", return_value=(100, 30)):
            app = TUIApp(mock_config, mock_config_path)
            app.app_state.projects = sample_projects

            # Start from second project's first spec
            app.app_state.selected_project_index = 1
            app.app_state.selected_spec_index = 0

            # Move up - should go to project level
            handled, msg = app.keybinding_handler.handle_key("up")
            assert handled is True
            assert app.app_state.selected_project_index == 1
            assert app.app_state.selected_spec_index is None

            # Move up - should go to first project's last spec
            handled, msg = app.keybinding_handler.handle_key("up")
            assert handled is True
            assert app.app_state.selected_project_index == 0
            assert app.app_state.selected_spec_index == 1

    def test_jump_to_top(self, mock_config, mock_config_path, sample_projects):
        """Test jumping to top of tree."""
        with patch("spec_workflow_runner.tui.app.get_terminal_size", return_value=(100, 30)):
            app = TUIApp(mock_config, mock_config_path)
            app.app_state.projects = sample_projects
            app.app_state.selected_project_index = 1
            app.app_state.selected_spec_index = 0

            # Jump to top
            handled, msg = app.keybinding_handler.handle_key("g")
            assert handled is True
            assert app.app_state.selected_project_index == 0
            assert app.app_state.selected_spec_index is None
            assert "Jumped to top" in msg

    def test_jump_to_bottom(self, mock_config, mock_config_path, sample_projects):
        """Test jumping to bottom of tree."""
        with patch("spec_workflow_runner.tui.app.get_terminal_size", return_value=(100, 30)):
            app = TUIApp(mock_config, mock_config_path)
            app.app_state.projects = sample_projects
            app.app_state.selected_project_index = 0
            app.app_state.selected_spec_index = None

            # Jump to bottom
            handled, msg = app.keybinding_handler.handle_key("G")
            assert handled is True
            assert app.app_state.selected_project_index == 1
            assert app.app_state.selected_spec_index == 0
            assert "Jumped to bottom" in msg


class TestRunnerControlWorkflow:
    """Test runner control workflows."""

    @patch("spec_workflow_runner.tui.runner_manager.subprocess.Popen")
    @patch("spec_workflow_runner.tui.runner_manager.check_clean_working_tree")
    @patch("spec_workflow_runner.tui.runner_manager.check_mcp_server_exists")
    @patch("spec_workflow_runner.tui.runner_manager.get_current_commit")
    def test_stop_runner_workflow(
        self,
        mock_get_commit,
        mock_check_mcp,
        mock_check_git,
        mock_popen,
        mock_config,
        mock_config_path,
        sample_projects,
        sample_runner,
    ):
        """Test stopping a runner through TUI."""
        with patch("spec_workflow_runner.tui.app.get_terminal_size", return_value=(100, 30)):
            # Mock os.kill to simulate process exists
            with patch("os.kill") as mock_kill:
                # Make os.kill succeed (process exists) for PID checks (signal 0)
                # and for SIGTERM (signal 15)
                mock_kill.return_value = None

                app = TUIApp(mock_config, mock_config_path)
                app.app_state.projects = sample_projects

                # Create mock process and add to runner manager
                mock_process = Mock()
                mock_process.pid = sample_runner.pid
                # Initially running, then return exit code after poll
                poll_calls = [None, 0]  # First call: still running, second call: exited
                mock_process.poll.side_effect = poll_calls

                # Attach runner to first spec and add process to runner manager
                sample_projects[0].specs[0].runner = sample_runner
                app.runner_manager.runners[sample_runner.runner_id] = sample_runner
                app.runner_manager.processes[sample_runner.runner_id] = mock_process

                # Select the spec with runner
                app.app_state.selected_project_index = 0
                app.app_state.selected_spec_index = 0

                # Mock the persister to avoid JSON serialization issues
                with patch.object(app.runner_manager.persister, "save") as mock_save:
                    # Stop the runner
                    handled, msg = app.keybinding_handler.handle_key("x")
                    assert handled is True
                    assert "Stopped runner" in msg
                    # Verify state was persisted
                    assert mock_save.called
                    # Verify runner status changed (can be STOPPED or CRASHED depending on timing)
                    updated_runner = app.runner_manager.runners.get(sample_runner.runner_id)
                    assert updated_runner is not None
                    assert updated_runner.status in (RunnerStatus.STOPPED, RunnerStatus.CRASHED)

    def test_start_runner_requires_unfinished_tasks(
        self, mock_config, mock_config_path, sample_projects
    ):
        """Test that starting runner requires unfinished tasks."""
        with patch("spec_workflow_runner.tui.app.get_terminal_size", return_value=(100, 30)):
            app = TUIApp(mock_config, mock_config_path)
            app.app_state.projects = sample_projects

            # Select spec with all tasks completed
            app.app_state.selected_project_index = 0
            app.app_state.selected_spec_index = 1  # feature-api with 15/15 tasks

            # Try to start runner
            handled, msg = app.keybinding_handler.handle_key("s")
            assert handled is True
            assert "Error" in msg
            assert "No unfinished tasks" in msg

    def test_start_runner_requires_selection(self, mock_config, mock_config_path, sample_projects):
        """Test that starting runner requires spec selection."""
        with patch("spec_workflow_runner.tui.app.get_terminal_size", return_value=(100, 30)):
            app = TUIApp(mock_config, mock_config_path)
            app.app_state.projects = sample_projects

            # No spec selected
            app.app_state.selected_project_index = None
            app.app_state.selected_spec_index = None

            # Try to start runner
            handled, msg = app.keybinding_handler.handle_key("s")
            assert handled is True
            assert "Error" in msg
            assert "No spec selected" in msg

    def test_cannot_start_runner_twice(
        self, mock_config, mock_config_path, sample_projects, sample_runner
    ):
        """Test that cannot start runner if already running."""
        with patch("spec_workflow_runner.tui.app.get_terminal_size", return_value=(100, 30)):
            app = TUIApp(mock_config, mock_config_path)
            app.app_state.projects = sample_projects

            # Attach runner to first spec
            sample_projects[0].specs[0].runner = sample_runner

            # Select the spec
            app.app_state.selected_project_index = 0
            app.app_state.selected_spec_index = 0

            # Try to start runner
            handled, msg = app.keybinding_handler.handle_key("s")
            assert handled is True
            assert "Error" in msg
            assert "already active" in msg


class TestViewControlWorkflow:
    """Test view control workflows."""

    def test_toggle_log_panel(self, mock_config, mock_config_path, sample_projects):
        """Test toggling log panel visibility."""
        with patch("spec_workflow_runner.tui.app.get_terminal_size", return_value=(100, 30)):
            app = TUIApp(mock_config, mock_config_path)
            app.app_state.projects = sample_projects

            # Initially visible
            assert app.app_state.log_panel_visible is True

            # Toggle off
            handled, msg = app.keybinding_handler.handle_key("l")
            assert handled is True
            assert app.app_state.log_panel_visible is False
            assert "hidden" in msg

            # Toggle on
            handled, msg = app.keybinding_handler.handle_key("l")
            assert handled is True
            assert app.app_state.log_panel_visible is True
            assert "visible" in msg

    def test_reenable_autoscroll(self, mock_config, mock_config_path):
        """Test re-enabling auto-scroll."""
        with patch("spec_workflow_runner.tui.app.get_terminal_size", return_value=(100, 30)):
            app = TUIApp(mock_config, mock_config_path)

            # Disable auto-scroll
            app.app_state.log_auto_scroll = False

            # Re-enable
            handled, msg = app.keybinding_handler.handle_key("L")
            assert handled is True
            assert app.app_state.log_auto_scroll is True
            assert "Auto-scroll enabled" in msg

    def test_toggle_unfinished_only(self, mock_config, mock_config_path):
        """Test toggling unfinished-only view."""
        with patch("spec_workflow_runner.tui.app.get_terminal_size", return_value=(100, 30)):
            app = TUIApp(mock_config, mock_config_path)

            # Initially off
            assert app.app_state.show_unfinished_only is False

            # Toggle on
            handled, msg = app.keybinding_handler.handle_key("u")
            assert handled is True
            assert app.app_state.show_unfinished_only is True
            assert "enabled" in msg

            # Toggle off
            handled, msg = app.keybinding_handler.handle_key("u")
            assert handled is True
            assert app.app_state.show_unfinished_only is False
            assert "disabled" in msg


class TestStatePollerIntegration:
    """Test StatePoller integration with TUI."""

    def test_state_updates_processed(self, mock_config, mock_config_path, sample_projects):
        """Test that state updates from poller are processed."""
        with patch("spec_workflow_runner.tui.app.get_terminal_size", return_value=(100, 30)):
            app = TUIApp(mock_config, mock_config_path)
            app.app_state.projects = sample_projects

            # Create state update for runner state change
            update = StateUpdate(
                project="",
                spec=None,
                update_type="runner_state",
                data=None,
            )

            # Put update in queue
            app.update_queue.put(update)

            # Process updates
            with patch.object(app, "_sync_runner_states") as mock_sync:
                app._process_state_updates()
                mock_sync.assert_called_once()

    def test_tasks_update_processed(self, mock_config, mock_config_path, sample_projects):
        """Test that task updates are processed."""
        with patch("spec_workflow_runner.tui.app.get_terminal_size", return_value=(100, 30)):
            app = TUIApp(mock_config, mock_config_path)
            app.app_state.projects = sample_projects

            # Mock read_task_stats to return updated stats
            mock_stats = TaskStats(done=7, in_progress=1, pending=2)

            # Mock Path.exists to return True for tasks file
            with patch("spec_workflow_runner.tui.app.read_task_stats", return_value=mock_stats):
                with patch.object(Path, "exists", return_value=True):
                    # Create state update for tasks change
                    update = StateUpdate(
                        project="project1",
                        spec="feature-auth",
                        update_type="tasks",
                        data=None,
                    )

                    # Put update in queue
                    app.update_queue.put(update)

                    # Process updates
                    app._process_state_updates()

                    # Verify spec was updated
                    spec = sample_projects[0].specs[0]
                    assert spec.completed_tasks == 7
                    assert spec.in_progress_tasks == 1
                    assert spec.pending_tasks == 2


class TestErrorHandling:
    """Test error handling and recovery."""

    def test_terminal_too_small_warning(self, mock_config, mock_config_path):
        """Test warning when terminal is too small."""
        with patch("spec_workflow_runner.tui.app.get_terminal_size", return_value=(60, 20)):
            app = TUIApp(mock_config, mock_config_path)

            # Check terminal size
            is_ok = app._check_terminal_size()
            assert is_ok is False

    def test_missing_spec_selection_error(self, mock_config, mock_config_path):
        """Test error messages when no spec is selected."""
        with patch("spec_workflow_runner.tui.app.get_terminal_size", return_value=(100, 30)):
            app = TUIApp(mock_config, mock_config_path)

            # Try to stop runner without selection
            handled, msg = app.keybinding_handler.handle_key("x")
            assert handled is True
            assert "Error" in msg
            assert "No spec selected" in msg

    def test_show_all_active_with_no_runners(self, mock_config, mock_config_path, sample_projects):
        """Test showing active runners when none exist."""
        with patch("spec_workflow_runner.tui.app.get_terminal_size", return_value=(100, 30)):
            app = TUIApp(mock_config, mock_config_path)
            app.app_state.projects = sample_projects

            # Show all active runners
            handled, msg = app.keybinding_handler.handle_key("a")
            assert handled is True
            assert "No active runners" in msg

    def test_show_all_active_with_runners(
        self, mock_config, mock_config_path, sample_projects, sample_runner
    ):
        """Test showing active runners when they exist."""
        with patch("spec_workflow_runner.tui.app.get_terminal_size", return_value=(100, 30)):
            app = TUIApp(mock_config, mock_config_path)
            app.app_state.projects = sample_projects

            # Add active runner
            app.runner_manager.runners[sample_runner.runner_id] = sample_runner

            # Show all active runners
            handled, msg = app.keybinding_handler.handle_key("a")
            assert handled is True
            assert "1 active runner" in msg
            assert "feature-auth" in msg


class TestQuitWorkflow:
    """Test quit/shutdown workflows."""

    def test_quit_command(self, mock_config, mock_config_path):
        """Test quit command sets should_quit flag."""
        with patch("spec_workflow_runner.tui.app.get_terminal_size", return_value=(100, 30)):
            app = TUIApp(mock_config, mock_config_path)

            # Press q to quit
            handled, msg = app.keybinding_handler.handle_key("q")
            assert handled is True
            assert msg == "quit"

    def test_shutdown_stops_poller(self, mock_config, mock_config_path):
        """Test shutdown stops state poller."""
        with patch("spec_workflow_runner.tui.app.get_terminal_size", return_value=(100, 30)):
            app = TUIApp(mock_config, mock_config_path)

            # Create mock poller
            mock_poller = Mock()
            app.state_poller = mock_poller

            # Shutdown
            app.shutdown(stop_all=False, timeout=10)

            # Verify poller was stopped
            mock_poller.stop.assert_called_once()

    def test_shutdown_calls_runner_manager(self, mock_config, mock_config_path):
        """Test shutdown calls runner manager shutdown."""
        with patch("spec_workflow_runner.tui.app.get_terminal_size", return_value=(100, 30)):
            app = TUIApp(mock_config, mock_config_path)

            # Mock runner manager shutdown
            with patch.object(app.runner_manager, "shutdown") as mock_shutdown:
                app.shutdown(stop_all=True, timeout=5)
                mock_shutdown.assert_called_once_with(stop_all=True, timeout=5)


class TestCompleteWorkflow:
    """Test complete end-to-end workflows."""

    @patch("spec_workflow_runner.tui.app.discover_projects")
    @patch("spec_workflow_runner.tui.app.discover_specs")
    @patch("spec_workflow_runner.tui.app.read_task_stats")
    def test_launch_navigate_view_status(
        self,
        mock_read_stats,
        mock_discover_specs,
        mock_discover_projects,
        mock_config,
        mock_config_path,
    ):
        """Test complete workflow: launch -> navigate -> view status."""
        # Setup mocks
        project_path = Path("/home/user/repos/project1")
        mock_discover_projects.return_value = [project_path]
        mock_discover_specs.return_value = [
            ("feature-auth", Path("/home/user/repos/project1/.spec-workflow/specs/feature-auth"))
        ]
        mock_read_stats.return_value = TaskStats(done=5, in_progress=2, pending=3)

        with patch("spec_workflow_runner.tui.app.get_terminal_size", return_value=(100, 30)):
            app = TUIApp(mock_config, mock_config_path)

            # Mock Path.exists to return True for tasks file
            with patch.object(Path, "exists", return_value=True):
                # Load initial state
                app._load_initial_state()

                # Verify projects loaded
                assert len(app.app_state.projects) == 1
                assert app.app_state.projects[0].name == "project1"
                assert len(app.app_state.projects[0].specs) == 1

                # Navigate to spec
                app.keybinding_handler.handle_key("down")  # Select project
                app.keybinding_handler.handle_key(" ")  # Expand project (collapsed by default)
                app.keybinding_handler.handle_key("down")  # Select spec

                # Verify selection
                assert app.app_state.selected_project_index == 0
                assert app.app_state.selected_spec_index == 0
                assert app.app_state.selected_spec is not None
                assert app.app_state.selected_spec.name == "feature-auth"

    @patch("spec_workflow_runner.tui.app.discover_projects")
    @patch("spec_workflow_runner.tui.app.discover_specs")
    @patch("spec_workflow_runner.tui.app.read_task_stats")
    def test_empty_project_list(
        self,
        mock_read_stats,
        mock_discover_specs,
        mock_discover_projects,
        mock_config,
        mock_config_path,
    ):
        """Test TUI handles empty project list gracefully."""
        # Setup mocks - no projects
        mock_discover_projects.return_value = []

        with patch("spec_workflow_runner.tui.app.get_terminal_size", return_value=(100, 30)):
            app = TUIApp(mock_config, mock_config_path)

            # Load initial state
            app._load_initial_state()

            # Verify empty projects
            assert len(app.app_state.projects) == 0

            # Try navigation - should not crash
            handled, msg = app.keybinding_handler.handle_key("down")
            assert handled is True

            # Try to start runner - should fail gracefully
            handled, msg = app.keybinding_handler.handle_key("s")
            assert handled is True
            assert "Error" in msg


class TestMetaCommands:
    """Test meta commands."""

    def test_help_command(self, mock_config, mock_config_path):
        """Test help command."""
        with patch("spec_workflow_runner.tui.app.get_terminal_size", return_value=(100, 30)):
            app = TUIApp(mock_config, mock_config_path)

            handled, msg = app.keybinding_handler.handle_key("?")
            assert handled is True
            assert msg is not None

    def test_config_command(self, mock_config, mock_config_path):
        """Test config command."""
        with patch("spec_workflow_runner.tui.app.get_terminal_size", return_value=(100, 30)):
            app = TUIApp(mock_config, mock_config_path)

            handled, msg = app.keybinding_handler.handle_key("c")
            assert handled is True
            assert msg is not None

    def test_unhandled_key(self, mock_config, mock_config_path):
        """Test unhandled key returns False."""
        with patch("spec_workflow_runner.tui.app.get_terminal_size", return_value=(100, 30)):
            app = TUIApp(mock_config, mock_config_path)

            handled, msg = app.keybinding_handler.handle_key("z")
            assert handled is False
            assert msg is None
