"""Tests for StatePoller file system monitoring."""

from __future__ import annotations

import queue
import time
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

from spec_workflow_runner.tui.models import StateUpdate
from spec_workflow_runner.tui.poller import StatePoller

if TYPE_CHECKING:
    from pytest import TempPathFactory


@pytest.fixture
def temp_project(tmp_path_factory: TempPathFactory) -> Path:
    """Create a temporary project structure for testing."""
    project = tmp_path_factory.mktemp("project")
    spec_workflow = project / ".spec-workflow"
    specs = spec_workflow / "specs"
    spec1 = specs / "spec1"
    spec1_logs = spec1 / "Implementation Logs"

    # Create directories
    spec1_logs.mkdir(parents=True)

    # Create files
    (spec1 / "tasks.md").write_text("# Tasks\n- [ ] Task 1\n")
    (spec1_logs / "log1.log").write_text("Log entry 1\n")

    return project


@pytest.fixture
def update_queue() -> queue.Queue[StateUpdate]:
    """Create an update queue for testing."""
    return queue.Queue()


@pytest.fixture
def state_file(tmp_path: Path) -> Path:
    """Create a state file path."""
    return tmp_path / "runner_state.json"


class TestStatePollerInit:
    """Tests for StatePoller initialization."""

    def test_initialization(
        self,
        temp_project: Path,
        update_queue: queue.Queue[StateUpdate],
        state_file: Path,
    ) -> None:
        """StatePoller should initialize with correct parameters."""
        poller = StatePoller(
            projects=[temp_project],
            spec_workflow_dir=".spec-workflow",
            specs_subdir="specs",
            tasks_filename="tasks.md",
            log_dir_name="Implementation Logs",
            state_file=state_file,
            update_queue=update_queue,
            refresh_seconds=1.0,
        )

        assert poller.projects == [temp_project]
        assert poller.spec_workflow_dir == ".spec-workflow"
        assert poller.specs_subdir == "specs"
        assert poller.tasks_filename == "tasks.md"
        assert poller.log_dir_name == "Implementation Logs"
        assert poller.state_file == state_file
        assert poller.update_queue is update_queue
        assert poller.refresh_seconds == 1.0

    def test_default_refresh_seconds(
        self,
        temp_project: Path,
        update_queue: queue.Queue[StateUpdate],
        state_file: Path,
    ) -> None:
        """Default refresh interval should be 2.0 seconds."""
        poller = StatePoller(
            projects=[temp_project],
            spec_workflow_dir=".spec-workflow",
            specs_subdir="specs",
            tasks_filename="tasks.md",
            log_dir_name="Implementation Logs",
            state_file=state_file,
            update_queue=update_queue,
        )

        assert poller.refresh_seconds == 2.0


class TestGetMtime:
    """Tests for _get_mtime helper."""

    def test_existing_file(
        self, tmp_path: Path, update_queue: queue.Queue[StateUpdate], state_file: Path
    ) -> None:
        """Should return mtime for existing file."""
        file = tmp_path / "test.txt"
        file.write_text("content")

        poller = StatePoller(
            projects=[tmp_path],
            spec_workflow_dir=".spec-workflow",
            specs_subdir="specs",
            tasks_filename="tasks.md",
            log_dir_name="logs",
            state_file=state_file,
            update_queue=update_queue,
        )

        mtime = poller._get_mtime(file)
        assert mtime is not None
        assert isinstance(mtime, float)
        assert mtime > 0

    def test_nonexistent_file(
        self, tmp_path: Path, update_queue: queue.Queue[StateUpdate], state_file: Path
    ) -> None:
        """Should return None for nonexistent file."""
        file = tmp_path / "nonexistent.txt"

        poller = StatePoller(
            projects=[tmp_path],
            spec_workflow_dir=".spec-workflow",
            specs_subdir="specs",
            tasks_filename="tasks.md",
            log_dir_name="logs",
            state_file=state_file,
            update_queue=update_queue,
        )

        mtime = poller._get_mtime(file)
        assert mtime is None


class TestCheckFileChanged:
    """Tests for _check_file_changed method."""

    def test_first_check_returns_true(
        self, tmp_path: Path, update_queue: queue.Queue[StateUpdate], state_file: Path
    ) -> None:
        """First check of a file should return True."""
        file = tmp_path / "test.txt"
        file.write_text("content")

        poller = StatePoller(
            projects=[tmp_path],
            spec_workflow_dir=".spec-workflow",
            specs_subdir="specs",
            tasks_filename="tasks.md",
            log_dir_name="logs",
            state_file=state_file,
            update_queue=update_queue,
        )

        assert poller._check_file_changed(file) is True

    def test_unchanged_file_returns_false(
        self, tmp_path: Path, update_queue: queue.Queue[StateUpdate], state_file: Path
    ) -> None:
        """Unchanged file should return False on second check."""
        file = tmp_path / "test.txt"
        file.write_text("content")

        poller = StatePoller(
            projects=[tmp_path],
            spec_workflow_dir=".spec-workflow",
            specs_subdir="specs",
            tasks_filename="tasks.md",
            log_dir_name="logs",
            state_file=state_file,
            update_queue=update_queue,
        )

        # First check
        poller._check_file_changed(file)
        # Second check without modification
        assert poller._check_file_changed(file) is False

    def test_modified_file_returns_true(
        self, tmp_path: Path, update_queue: queue.Queue[StateUpdate], state_file: Path
    ) -> None:
        """Modified file should return True."""
        file = tmp_path / "test.txt"
        file.write_text("content")

        poller = StatePoller(
            projects=[tmp_path],
            spec_workflow_dir=".spec-workflow",
            specs_subdir="specs",
            tasks_filename="tasks.md",
            log_dir_name="logs",
            state_file=state_file,
            update_queue=update_queue,
        )

        # First check
        poller._check_file_changed(file)

        # Modify file
        time.sleep(0.01)  # Ensure mtime changes
        file.write_text("new content")

        # Second check
        assert poller._check_file_changed(file) is True

    def test_nonexistent_file_returns_false(
        self, tmp_path: Path, update_queue: queue.Queue[StateUpdate], state_file: Path
    ) -> None:
        """Nonexistent file should return False."""
        file = tmp_path / "nonexistent.txt"

        poller = StatePoller(
            projects=[tmp_path],
            spec_workflow_dir=".spec-workflow",
            specs_subdir="specs",
            tasks_filename="tasks.md",
            log_dir_name="logs",
            state_file=state_file,
            update_queue=update_queue,
        )

        assert poller._check_file_changed(file) is False


class TestPollCycle:
    """Tests for _poll_cycle method."""

    def test_detects_state_file_change(
        self,
        temp_project: Path,
        update_queue: queue.Queue[StateUpdate],
        state_file: Path,
    ) -> None:
        """Should detect changes to state file."""
        state_file.write_text("{}")

        poller = StatePoller(
            projects=[temp_project],
            spec_workflow_dir=".spec-workflow",
            specs_subdir="specs",
            tasks_filename="tasks.md",
            log_dir_name="Implementation Logs",
            state_file=state_file,
            update_queue=update_queue,
        )

        poller._poll_cycle()

        # Should have queued a runner_state update
        assert not update_queue.empty()
        update = update_queue.get_nowait()
        assert update.update_type == "runner_state"

    def test_detects_tasks_file_change(
        self,
        temp_project: Path,
        update_queue: queue.Queue[StateUpdate],
        state_file: Path,
    ) -> None:
        """Should detect changes to tasks.md."""
        poller = StatePoller(
            projects=[temp_project],
            spec_workflow_dir=".spec-workflow",
            specs_subdir="specs",
            tasks_filename="tasks.md",
            log_dir_name="Implementation Logs",
            state_file=state_file,
            update_queue=update_queue,
        )

        poller._poll_cycle()

        # Should have queued a tasks update
        updates = []
        while not update_queue.empty():
            updates.append(update_queue.get_nowait())

        tasks_updates = [u for u in updates if u.update_type == "tasks"]
        assert len(tasks_updates) > 0
        assert tasks_updates[0].spec == "spec1"

    def test_detects_log_file_change(
        self,
        temp_project: Path,
        update_queue: queue.Queue[StateUpdate],
        state_file: Path,
    ) -> None:
        """Should detect changes to log files."""
        poller = StatePoller(
            projects=[temp_project],
            spec_workflow_dir=".spec-workflow",
            specs_subdir="specs",
            tasks_filename="tasks.md",
            log_dir_name="Implementation Logs",
            state_file=state_file,
            update_queue=update_queue,
        )

        poller._poll_cycle()

        # Should have queued a logs update
        updates = []
        while not update_queue.empty():
            updates.append(update_queue.get_nowait())

        logs_updates = [u for u in updates if u.update_type == "logs"]
        assert len(logs_updates) > 0
        assert logs_updates[0].spec == "spec1"

    def test_handles_missing_specs_directory(
        self,
        tmp_path: Path,
        update_queue: queue.Queue[StateUpdate],
        state_file: Path,
    ) -> None:
        """Should handle missing specs directory gracefully."""
        project = tmp_path / "empty_project"
        project.mkdir()

        poller = StatePoller(
            projects=[project],
            spec_workflow_dir=".spec-workflow",
            specs_subdir="specs",
            tasks_filename="tasks.md",
            log_dir_name="logs",
            state_file=state_file,
            update_queue=update_queue,
        )

        # Should not raise exception
        poller._poll_cycle()

    def test_handles_oserror_listing_specs(
        self,
        temp_project: Path,
        update_queue: queue.Queue[StateUpdate],
        state_file: Path,
    ) -> None:
        """Should handle OSError when listing specs."""
        poller = StatePoller(
            projects=[temp_project],
            spec_workflow_dir=".spec-workflow",
            specs_subdir="specs",
            tasks_filename="tasks.md",
            log_dir_name="logs",
            state_file=state_file,
            update_queue=update_queue,
        )

        temp_project / ".spec-workflow" / "specs"

        # Mock iterdir to raise OSError
        with patch.object(Path, "iterdir", side_effect=OSError("Permission denied")):
            # Should not raise, just log warning
            poller._poll_cycle()

    def test_handles_queue_full_for_state(
        self,
        temp_project: Path,
        state_file: Path,
    ) -> None:
        """Should handle full queue for state updates."""
        # Create a queue with maxsize=1
        small_queue: queue.Queue[StateUpdate] = queue.Queue(maxsize=1)
        state_file.write_text("{}")

        poller = StatePoller(
            projects=[temp_project],
            spec_workflow_dir=".spec-workflow",
            specs_subdir="specs",
            tasks_filename="tasks.md",
            log_dir_name="logs",
            state_file=state_file,
            update_queue=small_queue,
        )

        # Fill the queue
        small_queue.put(StateUpdate("proj", None, "dummy", None))

        # Should not raise, just log warning
        poller._poll_cycle()

    def test_handles_queue_full_for_tasks(
        self,
        temp_project: Path,
        state_file: Path,
    ) -> None:
        """Should handle full queue for tasks updates."""
        small_queue: queue.Queue[StateUpdate] = queue.Queue(maxsize=1)

        poller = StatePoller(
            projects=[temp_project],
            spec_workflow_dir=".spec-workflow",
            specs_subdir="specs",
            tasks_filename="tasks.md",
            log_dir_name="logs",
            state_file=state_file,
            update_queue=small_queue,
        )

        # Fill the queue
        small_queue.put(StateUpdate("proj", None, "dummy", None))

        # Should not raise, just log warning
        poller._poll_cycle()

    def test_handles_queue_full_for_logs(
        self,
        temp_project: Path,
        state_file: Path,
    ) -> None:
        """Should handle full queue for logs updates."""
        small_queue: queue.Queue[StateUpdate] = queue.Queue(maxsize=1)

        poller = StatePoller(
            projects=[temp_project],
            spec_workflow_dir=".spec-workflow",
            specs_subdir="specs",
            tasks_filename="tasks.md",
            log_dir_name="Implementation Logs",
            state_file=state_file,
            update_queue=small_queue,
        )

        # Fill the queue
        small_queue.put(StateUpdate("proj", None, "dummy", None))

        # Should not raise, just log warning
        poller._poll_cycle()

    def test_selects_latest_log_file(
        self,
        temp_project: Path,
        update_queue: queue.Queue[StateUpdate],
        state_file: Path,
    ) -> None:
        """Should select the most recently modified log file."""
        spec_logs = temp_project / ".spec-workflow" / "specs" / "spec1" / "Implementation Logs"

        # Create multiple log files
        log1 = spec_logs / "old.log"
        log2 = spec_logs / "new.log"

        log1.write_text("old")
        time.sleep(0.01)
        log2.write_text("new")

        poller = StatePoller(
            projects=[temp_project],
            spec_workflow_dir=".spec-workflow",
            specs_subdir="specs",
            tasks_filename="tasks.md",
            log_dir_name="Implementation Logs",
            state_file=state_file,
            update_queue=update_queue,
        )

        poller._poll_cycle()

        # Get logs updates
        updates = []
        while not update_queue.empty():
            updates.append(update_queue.get_nowait())

        logs_updates = [u for u in updates if u.update_type == "logs"]
        assert len(logs_updates) > 0
        # Should have selected the newer log file
        assert "new.log" in str(logs_updates[0].data)


class TestStartStop:
    """Tests for start and stop methods."""

    def test_start_creates_thread(
        self,
        temp_project: Path,
        update_queue: queue.Queue[StateUpdate],
        state_file: Path,
    ) -> None:
        """Start should create and start a background thread."""
        poller = StatePoller(
            projects=[temp_project],
            spec_workflow_dir=".spec-workflow",
            specs_subdir="specs",
            tasks_filename="tasks.md",
            log_dir_name="logs",
            state_file=state_file,
            update_queue=update_queue,
            refresh_seconds=0.1,
        )

        poller.start()

        assert poller._thread is not None
        assert poller._thread.is_alive()

        poller.stop()

    def test_start_twice_logs_warning(
        self,
        temp_project: Path,
        update_queue: queue.Queue[StateUpdate],
        state_file: Path,
    ) -> None:
        """Starting twice should log warning and not create new thread."""
        poller = StatePoller(
            projects=[temp_project],
            spec_workflow_dir=".spec-workflow",
            specs_subdir="specs",
            tasks_filename="tasks.md",
            log_dir_name="logs",
            state_file=state_file,
            update_queue=update_queue,
            refresh_seconds=0.1,
        )

        poller.start()
        first_thread = poller._thread

        # Start again
        poller.start()

        # Should still be the same thread
        assert poller._thread is first_thread

        poller.stop()

    def test_stop_terminates_thread(
        self,
        temp_project: Path,
        update_queue: queue.Queue[StateUpdate],
        state_file: Path,
    ) -> None:
        """Stop should terminate the background thread."""
        poller = StatePoller(
            projects=[temp_project],
            spec_workflow_dir=".spec-workflow",
            specs_subdir="specs",
            tasks_filename="tasks.md",
            log_dir_name="logs",
            state_file=state_file,
            update_queue=update_queue,
            refresh_seconds=0.1,
        )

        poller.start()
        poller.stop()

        # Thread should be stopped
        assert poller._thread is None or not poller._thread.is_alive()

    def test_stop_without_start(
        self,
        temp_project: Path,
        update_queue: queue.Queue[StateUpdate],
        state_file: Path,
    ) -> None:
        """Stop without start should not raise."""
        poller = StatePoller(
            projects=[temp_project],
            spec_workflow_dir=".spec-workflow",
            specs_subdir="specs",
            tasks_filename="tasks.md",
            log_dir_name="logs",
            state_file=state_file,
            update_queue=update_queue,
        )

        # Should not raise
        poller.stop()

    def test_poll_loop_runs_continuously(
        self,
        temp_project: Path,
        update_queue: queue.Queue[StateUpdate],
        state_file: Path,
    ) -> None:
        """Poll loop should run continuously until stopped."""
        poller = StatePoller(
            projects=[temp_project],
            spec_workflow_dir=".spec-workflow",
            specs_subdir="specs",
            tasks_filename="tasks.md",
            log_dir_name="logs",
            state_file=state_file,
            update_queue=update_queue,
            refresh_seconds=0.05,  # Fast refresh for testing
        )

        poller.start()

        # Let it run for a bit
        time.sleep(0.2)

        # Check that poll count increased
        assert poller._poll_count > 0

        poller.stop()

    def test_poll_loop_handles_exceptions(
        self,
        temp_project: Path,
        update_queue: queue.Queue[StateUpdate],
        state_file: Path,
    ) -> None:
        """Poll loop should handle exceptions and continue running."""
        poller = StatePoller(
            projects=[temp_project],
            spec_workflow_dir=".spec-workflow",
            specs_subdir="specs",
            tasks_filename="tasks.md",
            log_dir_name="logs",
            state_file=state_file,
            update_queue=update_queue,
            refresh_seconds=0.05,
        )

        # Mock _poll_cycle to raise exception once
        original_poll_cycle = poller._poll_cycle
        call_count = 0

        def mock_poll_cycle() -> None:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("Test exception")
            original_poll_cycle()

        poller._poll_cycle = mock_poll_cycle  # type: ignore

        poller.start()
        time.sleep(0.2)

        # Should have recovered and continued polling
        assert call_count > 1

        poller.stop()
