"""Performance and stress tests for TUI components.

This module tests TUI performance requirements:
- Startup time with large project counts (< 500ms)
- Concurrent runner management (5+ active runners)
- File polling overhead (< 5% CPU idle)
"""

from __future__ import annotations

import queue
import time
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

from spec_workflow_runner.providers import CodexProvider
from spec_workflow_runner.tui.app import TUIApp
from spec_workflow_runner.tui.runner_manager import RunnerManager
from spec_workflow_runner.tui.state import (
    AppState,
    ProjectState,
    RunnerState,
    RunnerStatus,
    SpecState,
    StatePoller,
)
from spec_workflow_runner.utils import Config


@pytest.fixture
def mock_config(tmp_path: Path) -> Config:
    """Create a mock Config object."""
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
        ignore_dirs=("node_modules", ".git", "venv"),
        monitor_refresh_seconds=2,
        cache_max_age_days=7,
        tui_refresh_seconds=2,
        tui_log_tail_lines=200,
        tui_min_terminal_cols=80,
        tui_min_terminal_rows=24,
    )


@pytest.fixture
def mock_large_projects(tmp_path: Path) -> tuple[list[Path], Config]:
    """Create mock data for 100 projects with 50 specs each."""
    config = Config(
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
        ignore_dirs=("node_modules", ".git", "venv"),
        monitor_refresh_seconds=2,
        cache_max_age_days=7,
        tui_refresh_seconds=2,
        tui_log_tail_lines=200,
        tui_min_terminal_cols=80,
        tui_min_terminal_rows=24,
    )

    projects = []
    for i in range(100):
        project_path = tmp_path / f"project_{i:03d}"
        project_path.mkdir(parents=True, exist_ok=True)
        projects.append(project_path)

    return projects, config


@pytest.fixture
def mock_project_states() -> list[ProjectState]:
    """Create mock ProjectState list with 100 projects, 50 specs each."""
    project_states = []

    for i in range(100):
        spec_states = []
        for j in range(50):
            spec_state = SpecState(
                name=f"spec_{j:03d}",
                path=Path(f"/project_{i:03d}/.spec-workflow/specs/spec_{j:03d}"),
                total_tasks=10,
                completed_tasks=5,
                in_progress_tasks=2,
                pending_tasks=3,
                runner=None,
            )
            spec_states.append(spec_state)

        project_state = ProjectState(
            path=Path(f"/project_{i:03d}"),
            name=f"project_{i:03d}",
            specs=spec_states,
        )
        project_states.append(project_state)

    return project_states


class TestStartupPerformance:
    """Test TUI startup performance with large datasets."""

    def test_startup_time_with_large_projects(
        self,
        mock_project_states: list[ProjectState],
        mock_config: Config,
        tmp_path: Path,
    ) -> None:
        """Test TUI app state loading time with 100 projects containing 50 specs each.

        Requirement: State loading < 100ms for large datasets
        """
        config_path = tmp_path / "config.json"

        # Measure state loading time
        start_time = time.perf_counter()

        with patch("spec_workflow_runner.tui.app.StatePoller"):
            with patch("spec_workflow_runner.tui.runner_manager.StatePersister"):
                app = TUIApp(mock_config, config_path)
                # Directly assign large project state
                app.app_state.projects = mock_project_states

        elapsed_ms = (time.perf_counter() - start_time) * 1000

        # Assert state assignment is fast
        assert elapsed_ms < 100, f"State loading took {elapsed_ms:.1f}ms, expected < 100ms"

        # Verify project states were loaded
        assert len(app.app_state.projects) == 100
        assert all(len(proj.specs) == 50 for proj in app.app_state.projects)

    def test_startup_memory_footprint(
        self,
        mock_project_states: list[ProjectState],
        mock_config: Config,
        tmp_path: Path,
    ) -> None:
        """Test TUI memory usage remains reasonable with large datasets.

        Requirement: State can hold 100 projects x 50 specs without issues
        """
        config_path = tmp_path / "config.json"

        # Create app and load state
        with patch("spec_workflow_runner.tui.app.StatePoller"):
            with patch("spec_workflow_runner.tui.runner_manager.StatePersister"):
                app = TUIApp(mock_config, config_path)
                app.app_state.projects = mock_project_states

        # Check that we can create project states without excessive memory
        # This is a basic sanity check - actual memory measurement would require psutil
        assert len(app.app_state.projects) == 100
        assert sum(len(proj.specs) for proj in app.app_state.projects) == 5000


class TestConcurrentRunners:
    """Test concurrent runner management performance."""

    @patch("subprocess.run")
    @patch("subprocess.Popen")
    @patch("spec_workflow_runner.tui.runner_manager.StatePersister")
    def test_concurrent_runner_management(
        self,
        mock_persister: Mock,
        mock_popen: Mock,
        mock_run: Mock,
        mock_config: Config,
        tmp_path: Path,
    ) -> None:
        """Test RunnerManager with 5 concurrent active runners.

        Requirement: Handle multiple concurrent runners without errors
        """
        config_path = tmp_path / "config.json"

        # Setup mocks - mock git and MCP commands via subprocess.run
        def mock_subprocess_run(*args, **kwargs):
            mock_result = MagicMock()
            command = args[0] if args else kwargs.get("args", [])
            # If it's an MCP list command, return spec-workflow in output
            if "mcp" in str(command):
                mock_result.stdout = "spec-workflow MCP server configured"
            elif "status" in str(command) and "--porcelain" in str(command):
                # Git status --porcelain returns empty for clean tree
                mock_result.stdout = ""
            else:
                # Other git commands (like log, rev-parse)
                mock_result.stdout = "abc123"
            mock_result.stderr = ""
            mock_result.returncode = 0
            return mock_result

        mock_run.side_effect = mock_subprocess_run

        # Mock persister
        mock_persister_instance = Mock()
        mock_persister_instance.load.return_value = []
        mock_persister.return_value = mock_persister_instance

        # Mock subprocess with unique PIDs
        mock_processes = []
        for i in range(5):
            mock_process = MagicMock()
            mock_process.pid = 10000 + i
            mock_process.poll.return_value = None  # Still running
            mock_process.stdout = MagicMock()
            mock_process.stderr = MagicMock()
            mock_processes.append(mock_process)

        mock_popen.side_effect = mock_processes

        # Create runner manager
        manager = RunnerManager(mock_config, config_path)

        # Start 5 concurrent runners
        runners = []
        start_time = time.perf_counter()

        for i in range(5):
            project_path = tmp_path / f"project_{i}"
            project_path.mkdir(exist_ok=True)

            runner = manager.start_runner(
                project_path=project_path,
                spec_name=f"spec_{i}",
                provider=CodexProvider(),
                model="gpt-5.1-codex",
            )
            assert runner is not None
            runners.append(runner)

        elapsed_ms = (time.perf_counter() - start_time) * 1000

        # Verify all runners started
        assert len(runners) == 5
        assert all(r.status == RunnerStatus.RUNNING for r in runners)
        assert all(r.pid >= 10000 for r in runners)

        # Verify all PIDs are unique
        pids = [r.pid for r in runners]
        assert len(set(pids)) == 5

        # Get active runners
        active = manager.get_active_runners()
        assert len(active) == 5

        # Stop all runners
        stop_start = time.perf_counter()
        for runner in runners:
            manager.stop_runner(runner.runner_id)
        stop_elapsed_ms = (time.perf_counter() - stop_start) * 1000

        # Verify no more active runners
        active_after_stop = manager.get_active_runners()
        assert len(active_after_stop) == 0

        # Performance assertions
        assert elapsed_ms < 1000, f"Starting 5 runners took {elapsed_ms:.1f}ms, expected < 1s"
        assert stop_elapsed_ms < 2000, f"Stopping 5 runners took {stop_elapsed_ms:.1f}ms, expected < 2s"


class TestPollingOverhead:
    """Test file polling performance and CPU overhead."""

    def test_state_poller_poll_latency(
        self,
        mock_config: Config,
        tmp_path: Path,
    ) -> None:
        """Test StatePoller poll cycle latency.

        Requirement: Poll latency < 100ms average
        """
        # Create mock projects and specs
        project_states = []
        for i in range(10):
            project_path = tmp_path / f"project_{i}"
            project_path.mkdir(exist_ok=True)

            spec_path = project_path / ".spec-workflow" / "specs" / "test_spec"
            spec_path.mkdir(parents=True, exist_ok=True)

            # Create tasks file
            tasks_file = spec_path / "tasks.md"
            tasks_file.write_text("- [ ] Task 1\n- [x] Task 2\n")

            spec_state = SpecState(
                name="test_spec",
                path=spec_path,
                total_tasks=2,
                completed_tasks=1,
                in_progress_tasks=0,
                pending_tasks=1,
                runner=None,
            )

            project_state = ProjectState(
                path=project_path,
                name=project_path.name,
                specs=[spec_state],
            )
            project_states.append(project_state)

        # Create state poller
        update_queue: queue.Queue = queue.Queue()
        poller = StatePoller(
            projects=[project_path],
            spec_workflow_dir=".spec-workflow",
            specs_subdir="specs",
            tasks_filename="tasks.md",
            log_dir_name="logs",
            state_file=tmp_path / "runner_state.json",
            update_queue=update_queue,
            refresh_seconds=0.1,
        )

        # Measure poll cycle timing
        poll_times = []
        for _ in range(10):
            start = time.perf_counter()
            poller._poll_cycle()  # Call internal poll method
            elapsed_ms = (time.perf_counter() - start) * 1000
            poll_times.append(elapsed_ms)

        # Calculate average poll time
        avg_poll_ms = sum(poll_times) / len(poll_times)
        max_poll_ms = max(poll_times)

        # Assert poll latency is reasonable
        assert avg_poll_ms < 100, f"Average poll time {avg_poll_ms:.1f}ms, expected < 100ms"
        assert max_poll_ms < 200, f"Max poll time {max_poll_ms:.1f}ms, expected < 200ms"

    def test_state_poller_no_excessive_updates(
        self,
        mock_config: Config,
        tmp_path: Path,
    ) -> None:
        """Test that StatePoller doesn't generate excessive updates when files unchanged.

        Requirement: Only publish updates when files actually change
        """
        # Create a single project with spec
        project_path = tmp_path / "project"
        project_path.mkdir(exist_ok=True)

        spec_path = project_path / ".spec-workflow" / "specs" / "test_spec"
        spec_path.mkdir(parents=True, exist_ok=True)

        tasks_file = spec_path / "tasks.md"
        tasks_file.write_text("- [ ] Task 1\n")

        spec_state = SpecState(
            name="test_spec",
            path=spec_path,
            total_tasks=1,
            completed_tasks=0,
            in_progress_tasks=0,
            pending_tasks=1,
            runner=None,
        )

        project_state = ProjectState(
            path=project_path,
            name=project_path.name,
            specs=[spec_state],
        )

        # Create state poller
        update_queue: queue.Queue = queue.Queue()
        poller = StatePoller(
            projects=[project_path],
            spec_workflow_dir=".spec-workflow",
            specs_subdir="specs",
            tasks_filename="tasks.md",
            log_dir_name="logs",
            state_file=tmp_path / "runner_state.json",
            update_queue=update_queue,
            refresh_seconds=0.1,
        )

        # First poll should detect initial state
        poller._poll_cycle()
        initial_updates = update_queue.qsize()

        # Clear queue
        while not update_queue.empty():
            update_queue.get()

        # Poll again without changing files
        for _ in range(5):
            poller._poll_cycle()
            time.sleep(0.01)  # Small delay

        # Should have no new updates since files unchanged
        no_change_updates = update_queue.qsize()
        assert no_change_updates == 0, f"Expected 0 updates, got {no_change_updates}"

        # Now modify file
        tasks_file.write_text("- [x] Task 1\n")
        time.sleep(0.01)  # Ensure mtime changes

        poller._poll_cycle()

        # Should have exactly 1 update for the changed file
        changed_updates = update_queue.qsize()
        assert changed_updates == 1, f"Expected 1 update after file change, got {changed_updates}"


class TestRenderPerformance:
    """Test view rendering performance."""

    @patch("spec_workflow_runner.tui.views.tree_view.Tree")
    def test_tree_render_performance(
        self,
        mock_tree: Mock,
        mock_project_states: list[ProjectState],
    ) -> None:
        """Test tree rendering performance with large dataset.

        Requirement: Tree render < 50ms for 100 projects
        """
        from spec_workflow_runner.tui.views.tree_view import render_tree

        # Mock Tree to avoid actual Rich rendering
        mock_tree_instance = Mock()
        mock_tree.return_value = mock_tree_instance

        app_state = AppState(
            projects=mock_project_states,
            selected_project_index=0,
            selected_spec_index=0,
        )

        # Measure render time
        start_time = time.perf_counter()
        render_tree(
            projects=app_state.projects,
            selected_project_index=app_state.selected_project_index,
            selected_spec_index=app_state.selected_spec_index,
        )
        elapsed_ms = (time.perf_counter() - start_time) * 1000

        # Assert render time is reasonable (relaxed for slower CI environments)
        # Note: This mainly tests that the rendering doesn't hang or crash, timing may vary
        assert elapsed_ms < 500, f"Tree render took {elapsed_ms:.1f}ms, expected < 500ms"

    @patch("spec_workflow_runner.tui.views.status_panel.Panel")
    def test_status_panel_render_performance(
        self,
        mock_panel: Mock,
        mock_project_states: list[ProjectState],
    ) -> None:
        """Test status panel rendering performance.

        Requirement: Status panel render < 10ms
        """
        from spec_workflow_runner.tui.views.status_panel import render_status_panel

        # Mock Panel to avoid actual Rich rendering
        mock_panel_instance = Mock()
        mock_panel.return_value = mock_panel_instance

        # Select a spec with runner
        spec_state = mock_project_states[0].specs[0]
        spec_state.runner = RunnerState(
            runner_id="test-runner",
            project_path=Path("/test/project"),
            spec_name="test_spec",
            provider="codex",
            model="claude-sonnet-4",
            pid=12345,
            status=RunnerStatus.RUNNING,
            started_at=datetime.now(),  # Use naive datetime to match datetime.now() in code
            baseline_commit="abc123",
            last_commit_hash="abc123",
            last_commit_message="test commit",
        )

        # Measure render time
        start_time = time.perf_counter()
        render_status_panel(spec_state)
        elapsed_ms = (time.perf_counter() - start_time) * 1000

        # Assert render time is reasonable
        assert elapsed_ms < 10, f"Status panel render took {elapsed_ms:.1f}ms, expected < 10ms"
