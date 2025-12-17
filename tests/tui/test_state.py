"""Unit tests for TUI state models and persistence."""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, mock_open, patch

import pytest

from spec_workflow_runner.tui.state import (
    AppState,
    ProjectState,
    RunnerState,
    RunnerStatus,
    SpecState,
    StatePersister,
)


class TestRunnerStatus:
    """Tests for RunnerStatus enum."""

    def test_all_status_values(self):
        """Test all runner status enum values exist."""
        assert RunnerStatus.RUNNING.value == "running"
        assert RunnerStatus.STOPPED.value == "stopped"
        assert RunnerStatus.CRASHED.value == "crashed"
        assert RunnerStatus.COMPLETED.value == "completed"

    def test_from_string(self):
        """Test creating RunnerStatus from string value."""
        assert RunnerStatus("running") == RunnerStatus.RUNNING
        assert RunnerStatus("stopped") == RunnerStatus.STOPPED
        assert RunnerStatus("crashed") == RunnerStatus.CRASHED
        assert RunnerStatus("completed") == RunnerStatus.COMPLETED


class TestProjectState:
    """Tests for ProjectState dataclass."""

    def test_initialization(self):
        """Test ProjectState initialization with correct field types."""
        project = ProjectState(
            path=Path("/home/user/project"), name="my-project", specs=[]
        )

        assert isinstance(project.path, Path)
        assert project.path == Path("/home/user/project")
        assert project.name == "my-project"
        assert isinstance(project.specs, list)
        assert len(project.specs) == 0

    def test_default_specs(self):
        """Test ProjectState has empty specs list by default."""
        project = ProjectState(path=Path("/home/user/project"), name="my-project")

        assert project.specs == []

    def test_with_specs(self):
        """Test ProjectState with specs."""
        spec = SpecState(
            name="test-spec",
            path=Path("/home/user/project/.spec-workflow/specs/test-spec"),
            total_tasks=10,
            completed_tasks=5,
            in_progress_tasks=2,
            pending_tasks=3,
        )
        project = ProjectState(
            path=Path("/home/user/project"), name="my-project", specs=[spec]
        )

        assert len(project.specs) == 1
        assert project.specs[0] == spec

    def test_repr(self):
        """Test ProjectState string representation."""
        project = ProjectState(
            path=Path("/home/user/project"), name="my-project", specs=[]
        )

        repr_str = repr(project)
        assert "my-project" in repr_str
        assert "specs=0" in repr_str


class TestSpecState:
    """Tests for SpecState dataclass."""

    def test_initialization(self):
        """Test SpecState initialization with correct field types."""
        spec = SpecState(
            name="test-spec",
            path=Path("/home/user/project/.spec-workflow/specs/test-spec"),
            total_tasks=10,
            completed_tasks=5,
            in_progress_tasks=2,
            pending_tasks=3,
        )

        assert spec.name == "test-spec"
        assert isinstance(spec.path, Path)
        assert spec.total_tasks == 10
        assert spec.completed_tasks == 5
        assert spec.in_progress_tasks == 2
        assert spec.pending_tasks == 3
        assert spec.runner is None

    def test_is_complete_true(self):
        """Test is_complete property when all tasks are done."""
        spec = SpecState(
            name="test-spec",
            path=Path("/spec"),
            total_tasks=10,
            completed_tasks=10,
            in_progress_tasks=0,
            pending_tasks=0,
        )

        assert spec.is_complete is True

    def test_is_complete_false(self):
        """Test is_complete property when tasks remain."""
        spec = SpecState(
            name="test-spec",
            path=Path("/spec"),
            total_tasks=10,
            completed_tasks=5,
            in_progress_tasks=2,
            pending_tasks=3,
        )

        assert spec.is_complete is False

    def test_is_complete_zero_tasks(self):
        """Test is_complete returns False when no tasks."""
        spec = SpecState(
            name="test-spec",
            path=Path("/spec"),
            total_tasks=0,
            completed_tasks=0,
            in_progress_tasks=0,
            pending_tasks=0,
        )

        assert spec.is_complete is False

    def test_has_unfinished_tasks_true(self):
        """Test has_unfinished_tasks when tasks are pending."""
        spec = SpecState(
            name="test-spec",
            path=Path("/spec"),
            total_tasks=10,
            completed_tasks=5,
            in_progress_tasks=2,
            pending_tasks=3,
        )

        assert spec.has_unfinished_tasks is True

    def test_has_unfinished_tasks_false(self):
        """Test has_unfinished_tasks when all tasks complete."""
        spec = SpecState(
            name="test-spec",
            path=Path("/spec"),
            total_tasks=10,
            completed_tasks=10,
            in_progress_tasks=0,
            pending_tasks=0,
        )

        assert spec.has_unfinished_tasks is False

    def test_has_unfinished_tasks_zero_tasks(self):
        """Test has_unfinished_tasks returns False when no tasks."""
        spec = SpecState(
            name="test-spec",
            path=Path("/spec"),
            total_tasks=0,
            completed_tasks=0,
            in_progress_tasks=0,
            pending_tasks=0,
        )

        assert spec.has_unfinished_tasks is False

    def test_with_runner(self):
        """Test SpecState with attached runner."""
        runner = RunnerState(
            runner_id="test-123",
            project_path=Path("/project"),
            spec_name="test-spec",
            provider="codex",
            model="gpt-4",
            pid=12345,
            status=RunnerStatus.RUNNING,
            started_at=datetime.now(),
            baseline_commit="abc123",
        )
        spec = SpecState(
            name="test-spec",
            path=Path("/spec"),
            total_tasks=10,
            completed_tasks=5,
            in_progress_tasks=2,
            pending_tasks=3,
            runner=runner,
        )

        assert spec.runner == runner
        assert spec.runner.status == RunnerStatus.RUNNING

    def test_repr(self):
        """Test SpecState string representation."""
        spec = SpecState(
            name="test-spec",
            path=Path("/spec"),
            total_tasks=10,
            completed_tasks=5,
            in_progress_tasks=2,
            pending_tasks=3,
        )

        repr_str = repr(spec)
        assert "test-spec" in repr_str
        assert "5/10" in repr_str


class TestRunnerState:
    """Tests for RunnerState dataclass and serialization."""

    def test_initialization(self):
        """Test RunnerState initialization with correct field types."""
        started_at = datetime.now()
        runner = RunnerState(
            runner_id="test-123",
            project_path=Path("/home/user/project"),
            spec_name="test-spec",
            provider="codex",
            model="gpt-4",
            pid=12345,
            status=RunnerStatus.RUNNING,
            started_at=started_at,
            baseline_commit="abc123def456",
        )

        assert runner.runner_id == "test-123"
        assert isinstance(runner.project_path, Path)
        assert runner.project_path == Path("/home/user/project")
        assert runner.spec_name == "test-spec"
        assert runner.provider == "codex"
        assert runner.model == "gpt-4"
        assert runner.pid == 12345
        assert runner.status == RunnerStatus.RUNNING
        assert isinstance(runner.started_at, datetime)
        assert runner.started_at == started_at
        assert runner.baseline_commit == "abc123def456"
        assert runner.last_commit_hash is None
        assert runner.last_commit_message is None
        assert runner.exit_code is None

    def test_initialization_with_optional_fields(self):
        """Test RunnerState with optional fields populated."""
        runner = RunnerState(
            runner_id="test-123",
            project_path=Path("/project"),
            spec_name="test-spec",
            provider="codex",
            model="gpt-4",
            pid=12345,
            status=RunnerStatus.COMPLETED,
            started_at=datetime.now(),
            baseline_commit="abc123",
            last_commit_hash="def456",
            last_commit_message="feat: add new feature",
            exit_code=0,
        )

        assert runner.last_commit_hash == "def456"
        assert runner.last_commit_message == "feat: add new feature"
        assert runner.exit_code == 0

    def test_to_dict(self):
        """Test RunnerState serialization to dict."""
        started_at = datetime(2025, 12, 17, 14, 30, 0)
        runner = RunnerState(
            runner_id="test-123",
            project_path=Path("/home/user/project"),
            spec_name="test-spec",
            provider="codex",
            model="gpt-4",
            pid=12345,
            status=RunnerStatus.RUNNING,
            started_at=started_at,
            baseline_commit="abc123",
            last_commit_hash="def456",
            last_commit_message="feat: test",
            exit_code=0,
        )

        data = runner.to_dict()

        assert isinstance(data, dict)
        assert data["runner_id"] == "test-123"
        assert data["project_path"] == "/home/user/project"
        assert data["spec_name"] == "test-spec"
        assert data["provider"] == "codex"
        assert data["model"] == "gpt-4"
        assert data["pid"] == 12345
        assert data["status"] == "running"
        assert data["started_at"] == "2025-12-17T14:30:00"
        assert data["baseline_commit"] == "abc123"
        assert data["last_commit_hash"] == "def456"
        assert data["last_commit_message"] == "feat: test"
        assert data["exit_code"] == 0

    def test_to_dict_with_none_fields(self):
        """Test RunnerState serialization with None optional fields."""
        runner = RunnerState(
            runner_id="test-123",
            project_path=Path("/project"),
            spec_name="test-spec",
            provider="codex",
            model="gpt-4",
            pid=12345,
            status=RunnerStatus.RUNNING,
            started_at=datetime(2025, 12, 17, 14, 30, 0),
            baseline_commit="abc123",
        )

        data = runner.to_dict()

        assert data["last_commit_hash"] is None
        assert data["last_commit_message"] is None
        assert data["exit_code"] is None

    def test_from_dict(self):
        """Test RunnerState deserialization from dict."""
        data = {
            "runner_id": "test-123",
            "project_path": "/home/user/project",
            "spec_name": "test-spec",
            "provider": "codex",
            "model": "gpt-4",
            "pid": 12345,
            "status": "running",
            "started_at": "2025-12-17T14:30:00",
            "baseline_commit": "abc123",
            "last_commit_hash": "def456",
            "last_commit_message": "feat: test",
            "exit_code": 0,
        }

        runner = RunnerState.from_dict(data)

        assert runner.runner_id == "test-123"
        assert isinstance(runner.project_path, Path)
        assert runner.project_path == Path("/home/user/project")
        assert runner.spec_name == "test-spec"
        assert runner.provider == "codex"
        assert runner.model == "gpt-4"
        assert runner.pid == 12345
        assert runner.status == RunnerStatus.RUNNING
        assert isinstance(runner.started_at, datetime)
        assert runner.started_at == datetime(2025, 12, 17, 14, 30, 0)
        assert runner.baseline_commit == "abc123"
        assert runner.last_commit_hash == "def456"
        assert runner.last_commit_message == "feat: test"
        assert runner.exit_code == 0

    def test_from_dict_without_optional_fields(self):
        """Test RunnerState deserialization without optional fields."""
        data = {
            "runner_id": "test-123",
            "project_path": "/project",
            "spec_name": "test-spec",
            "provider": "codex",
            "model": "gpt-4",
            "pid": 12345,
            "status": "running",
            "started_at": "2025-12-17T14:30:00",
            "baseline_commit": "abc123",
        }

        runner = RunnerState.from_dict(data)

        assert runner.last_commit_hash is None
        assert runner.last_commit_message is None
        assert runner.exit_code is None

    def test_serialization_round_trip(self):
        """Test serialization and deserialization round-trip."""
        original = RunnerState(
            runner_id="test-123",
            project_path=Path("/home/user/project"),
            spec_name="test-spec",
            provider="codex",
            model="gpt-4",
            pid=12345,
            status=RunnerStatus.RUNNING,
            started_at=datetime(2025, 12, 17, 14, 30, 0),
            baseline_commit="abc123",
            last_commit_hash="def456",
            last_commit_message="feat: test",
            exit_code=0,
        )

        # Serialize and deserialize
        data = original.to_dict()
        restored = RunnerState.from_dict(data)

        # Compare all fields
        assert restored.runner_id == original.runner_id
        assert restored.project_path == original.project_path
        assert restored.spec_name == original.spec_name
        assert restored.provider == original.provider
        assert restored.model == original.model
        assert restored.pid == original.pid
        assert restored.status == original.status
        assert restored.started_at == original.started_at
        assert restored.baseline_commit == original.baseline_commit
        assert restored.last_commit_hash == original.last_commit_hash
        assert restored.last_commit_message == original.last_commit_message
        assert restored.exit_code == original.exit_code

    def test_repr(self):
        """Test RunnerState string representation."""
        runner = RunnerState(
            runner_id="test-123",
            project_path=Path("/project"),
            spec_name="test-spec",
            provider="codex",
            model="gpt-4",
            pid=12345,
            status=RunnerStatus.RUNNING,
            started_at=datetime.now(),
            baseline_commit="abc123",
        )

        repr_str = repr(runner)
        assert "test-123" in repr_str
        assert "test-spec" in repr_str
        assert "running" in repr_str
        assert "12345" in repr_str


class TestAppState:
    """Tests for AppState dataclass."""

    def test_initialization(self):
        """Test AppState initialization with correct field types."""
        app_state = AppState()

        assert isinstance(app_state.projects, list)
        assert len(app_state.projects) == 0
        assert app_state.selected_project_index is None
        assert app_state.selected_spec_index is None
        assert app_state.filter_text == ""
        assert app_state.filter_mode is False
        assert app_state.show_unfinished_only is False
        assert app_state.log_panel_visible is True
        assert app_state.log_auto_scroll is True
        assert app_state.current_error is None
        assert isinstance(app_state.active_runners, dict)
        assert len(app_state.active_runners) == 0

    def test_with_projects(self):
        """Test AppState with projects."""
        project = ProjectState(path=Path("/project"), name="test-project")
        app_state = AppState(projects=[project])

        assert len(app_state.projects) == 1
        assert app_state.projects[0] == project

    def test_selected_project_none(self):
        """Test selected_project returns None when no selection."""
        app_state = AppState()

        assert app_state.selected_project is None

    def test_selected_project_valid(self):
        """Test selected_project returns project when valid index."""
        project = ProjectState(path=Path("/project"), name="test-project")
        app_state = AppState(projects=[project], selected_project_index=0)

        assert app_state.selected_project == project

    def test_selected_project_out_of_bounds(self):
        """Test selected_project returns None when index out of bounds."""
        project = ProjectState(path=Path("/project"), name="test-project")
        app_state = AppState(projects=[project], selected_project_index=5)

        assert app_state.selected_project is None

    def test_selected_spec_none_no_project(self):
        """Test selected_spec returns None when no project selected."""
        app_state = AppState()

        assert app_state.selected_spec is None

    def test_selected_spec_none_no_spec_index(self):
        """Test selected_spec returns None when no spec index set."""
        project = ProjectState(path=Path("/project"), name="test-project")
        app_state = AppState(projects=[project], selected_project_index=0)

        assert app_state.selected_spec is None

    def test_selected_spec_valid(self):
        """Test selected_spec returns spec when valid indices."""
        spec = SpecState(
            name="test-spec",
            path=Path("/spec"),
            total_tasks=10,
            completed_tasks=5,
            in_progress_tasks=2,
            pending_tasks=3,
        )
        project = ProjectState(
            path=Path("/project"), name="test-project", specs=[spec]
        )
        app_state = AppState(
            projects=[project], selected_project_index=0, selected_spec_index=0
        )

        assert app_state.selected_spec == spec

    def test_selected_spec_out_of_bounds(self):
        """Test selected_spec returns None when spec index out of bounds."""
        spec = SpecState(
            name="test-spec",
            path=Path("/spec"),
            total_tasks=10,
            completed_tasks=5,
            in_progress_tasks=2,
            pending_tasks=3,
        )
        project = ProjectState(
            path=Path("/project"), name="test-project", specs=[spec]
        )
        app_state = AppState(
            projects=[project], selected_project_index=0, selected_spec_index=5
        )

        assert app_state.selected_spec is None

    def test_repr(self):
        """Test AppState string representation."""
        app_state = AppState()

        repr_str = repr(app_state)
        assert "projects=0" in repr_str
        assert "active_runners=0" in repr_str


class TestStatePersister:
    """Tests for StatePersister class."""

    def test_initialization(self):
        """Test StatePersister initialization."""
        cache_dir = Path("/home/user/.cache/spec-workflow-runner")
        config_path = Path("/home/user/config.json")

        persister = StatePersister(cache_dir, config_path)

        assert persister.cache_dir == cache_dir
        assert persister.config_path == config_path
        assert persister.state_file == cache_dir / "runner_state.json"

    @patch("pathlib.Path.exists")
    @patch("pathlib.Path.open", new_callable=mock_open, read_data=b"test content")
    def test_compute_config_hash(self, mock_file, mock_exists):
        """Test config hash computation."""
        mock_exists.return_value = True
        cache_dir = Path("/cache")
        config_path = Path("/config.json")

        persister = StatePersister(cache_dir, config_path)
        hash_value = persister._compute_config_hash()

        assert isinstance(hash_value, str)
        assert len(hash_value) == 64  # SHA256 hex digest length

    @patch("pathlib.Path.exists")
    def test_compute_config_hash_missing_file(self, mock_exists):
        """Test config hash when file doesn't exist."""
        mock_exists.return_value = False
        persister = StatePersister(Path("/cache"), Path("/config.json"))

        hash_value = persister._compute_config_hash()

        assert hash_value == ""

    @patch("pathlib.Path.exists")
    @patch("pathlib.Path.open")
    def test_compute_config_hash_error(self, mock_file, mock_exists):
        """Test config hash handles read errors."""
        mock_exists.return_value = True
        mock_file.side_effect = OSError("Permission denied")
        persister = StatePersister(Path("/cache"), Path("/config.json"))

        hash_value = persister._compute_config_hash()

        assert hash_value == ""

    @patch("os.kill")
    def test_is_pid_alive_true(self, mock_kill):
        """Test PID check returns True for running process."""
        mock_kill.return_value = None  # No exception = process exists
        persister = StatePersister(Path("/cache"), Path("/config.json"))

        result = persister._is_pid_alive(12345)

        assert result is True
        mock_kill.assert_called_once_with(12345, 0)

    @patch("os.kill")
    def test_is_pid_alive_false(self, mock_kill):
        """Test PID check returns False for non-existent process."""
        mock_kill.side_effect = ProcessLookupError()
        persister = StatePersister(Path("/cache"), Path("/config.json"))

        result = persister._is_pid_alive(12345)

        assert result is False

    @patch("os.kill")
    def test_is_pid_alive_permission_error(self, mock_kill):
        """Test PID check returns True when permission denied (process exists)."""
        mock_kill.side_effect = PermissionError()
        persister = StatePersister(Path("/cache"), Path("/config.json"))

        result = persister._is_pid_alive(12345)

        assert result is True

    @patch("os.kill")
    def test_is_pid_alive_os_error(self, mock_kill):
        """Test PID check returns False on OS error."""
        mock_kill.side_effect = OSError("Unknown error")
        persister = StatePersister(Path("/cache"), Path("/config.json"))

        result = persister._is_pid_alive(12345)

        assert result is False

    @patch("pathlib.Path.mkdir")
    @patch("pathlib.Path.open", new_callable=mock_open)
    @patch.object(StatePersister, "_compute_config_hash")
    def test_save_creates_cache_dir(self, mock_hash, mock_file, mock_mkdir):
        """Test save creates cache directory if it doesn't exist."""
        mock_hash.return_value = "hash123"
        persister = StatePersister(Path("/cache"), Path("/config.json"))

        persister.save([])

        mock_mkdir.assert_called_once_with(parents=True, exist_ok=True)

    @patch("pathlib.Path.mkdir")
    @patch("pathlib.Path.open", new_callable=mock_open)
    @patch.object(StatePersister, "_compute_config_hash")
    def test_save_writes_json(self, mock_hash, mock_file, mock_mkdir):
        """Test save writes runner state as JSON."""
        mock_hash.return_value = "hash123"
        persister = StatePersister(Path("/cache"), Path("/config.json"))

        runner = RunnerState(
            runner_id="test-123",
            project_path=Path("/project"),
            spec_name="test-spec",
            provider="codex",
            model="gpt-4",
            pid=12345,
            status=RunnerStatus.RUNNING,
            started_at=datetime(2025, 12, 17, 14, 30, 0),
            baseline_commit="abc123",
        )

        persister.save([runner])

        # Verify file was opened for writing
        mock_file.assert_called_once()
        # Verify json.dump was called with correct structure
        handle = mock_file()
        written_data = "".join(
            call.args[0] for call in handle.write.call_args_list if call.args
        )
        data = json.loads(written_data)
        assert data["config_hash"] == "hash123"
        assert len(data["runners"]) == 1
        assert data["runners"][0]["runner_id"] == "test-123"

    @patch("pathlib.Path.mkdir")
    @patch("pathlib.Path.open")
    @patch.object(StatePersister, "_compute_config_hash")
    def test_save_handles_write_error(self, mock_hash, mock_file, mock_mkdir):
        """Test save handles write errors gracefully."""
        mock_hash.return_value = "hash123"
        mock_file.side_effect = OSError("Disk full")
        persister = StatePersister(Path("/cache"), Path("/config.json"))

        # Should not raise exception
        persister.save([])

    @patch("pathlib.Path.exists")
    def test_load_empty_when_no_file(self, mock_exists):
        """Test load returns empty list when state file doesn't exist."""
        mock_exists.return_value = False
        persister = StatePersister(Path("/cache"), Path("/config.json"))

        runners = persister.load()

        assert runners == []

    @patch("pathlib.Path.exists")
    @patch("pathlib.Path.open", new_callable=mock_open, read_data="invalid json")
    @patch("pathlib.Path.unlink")
    def test_load_handles_corrupted_json(self, mock_unlink, mock_file, mock_exists):
        """Test load deletes corrupted JSON and returns empty list."""
        mock_exists.return_value = True
        persister = StatePersister(Path("/cache"), Path("/config.json"))

        runners = persister.load()

        assert runners == []
        mock_unlink.assert_called_once()

    @patch("pathlib.Path.exists")
    @patch("pathlib.Path.open")
    @patch("pathlib.Path.unlink")
    def test_load_handles_read_error(self, mock_unlink, mock_file, mock_exists):
        """Test load handles read errors gracefully."""
        mock_exists.return_value = True
        mock_file.side_effect = OSError("Permission denied")
        persister = StatePersister(Path("/cache"), Path("/config.json"))

        runners = persister.load()

        assert runners == []
        mock_unlink.assert_called_once()

    @patch("pathlib.Path.exists")
    @patch("pathlib.Path.open", new_callable=mock_open)
    @patch("pathlib.Path.unlink")
    @patch.object(StatePersister, "_compute_config_hash")
    def test_load_invalidates_on_config_change(
        self, mock_hash, mock_unlink, mock_file, mock_exists
    ):
        """Test load invalidates state when config hash changes."""
        mock_exists.return_value = True
        mock_hash.return_value = "new_hash"

        state_data = json.dumps({"config_hash": "old_hash", "runners": []})
        mock_file.return_value.__enter__.return_value.read.return_value = state_data

        persister = StatePersister(Path("/cache"), Path("/config.json"))
        runners = persister.load()

        assert runners == []
        # Verify unlink was called (it's called on the state_file path)
        assert mock_unlink.called

    @patch("pathlib.Path.exists")
    @patch("pathlib.Path.open", new_callable=mock_open)
    @patch.object(StatePersister, "_compute_config_hash")
    @patch.object(StatePersister, "_is_pid_alive")
    def test_load_validates_running_pids(
        self, mock_is_alive, mock_hash, mock_file, mock_exists
    ):
        """Test load validates PIDs and marks dead runners as crashed."""
        mock_exists.return_value = True
        mock_hash.return_value = "hash123"
        mock_is_alive.return_value = False  # PID is dead

        runner_data = {
            "runner_id": "test-123",
            "project_path": "/project",
            "spec_name": "test-spec",
            "provider": "codex",
            "model": "gpt-4",
            "pid": 12345,
            "status": "running",
            "started_at": "2025-12-17T14:30:00",
            "baseline_commit": "abc123",
        }
        state_data = json.dumps({"config_hash": "hash123", "runners": [runner_data]})
        mock_file.return_value.__enter__.return_value.read.return_value = state_data

        persister = StatePersister(Path("/cache"), Path("/config.json"))
        runners = persister.load()

        assert len(runners) == 1
        assert runners[0].status == RunnerStatus.CRASHED
        mock_is_alive.assert_called_once_with(12345)

    @patch("pathlib.Path.exists")
    @patch("pathlib.Path.open", new_callable=mock_open)
    @patch.object(StatePersister, "_compute_config_hash")
    @patch.object(StatePersister, "_is_pid_alive")
    def test_load_keeps_alive_runners(
        self, mock_is_alive, mock_hash, mock_file, mock_exists
    ):
        """Test load keeps runners with alive PIDs as running."""
        mock_exists.return_value = True
        mock_hash.return_value = "hash123"
        mock_is_alive.return_value = True  # PID is alive

        runner_data = {
            "runner_id": "test-123",
            "project_path": "/project",
            "spec_name": "test-spec",
            "provider": "codex",
            "model": "gpt-4",
            "pid": 12345,
            "status": "running",
            "started_at": "2025-12-17T14:30:00",
            "baseline_commit": "abc123",
        }
        state_data = json.dumps({"config_hash": "hash123", "runners": [runner_data]})
        mock_file.return_value.__enter__.return_value.read.return_value = state_data

        persister = StatePersister(Path("/cache"), Path("/config.json"))
        runners = persister.load()

        assert len(runners) == 1
        assert runners[0].status == RunnerStatus.RUNNING
        mock_is_alive.assert_called_once_with(12345)

    @patch("pathlib.Path.exists")
    @patch("pathlib.Path.open", new_callable=mock_open)
    @patch.object(StatePersister, "_compute_config_hash")
    def test_load_skips_pid_check_for_stopped(
        self, mock_hash, mock_file, mock_exists
    ):
        """Test load doesn't validate PIDs for stopped/completed runners."""
        mock_exists.return_value = True
        mock_hash.return_value = "hash123"

        runner_data = {
            "runner_id": "test-123",
            "project_path": "/project",
            "spec_name": "test-spec",
            "provider": "codex",
            "model": "gpt-4",
            "pid": 12345,
            "status": "stopped",
            "started_at": "2025-12-17T14:30:00",
            "baseline_commit": "abc123",
        }
        state_data = json.dumps({"config_hash": "hash123", "runners": [runner_data]})
        mock_file.return_value.__enter__.return_value.read.return_value = state_data

        persister = StatePersister(Path("/cache"), Path("/config.json"))
        runners = persister.load()

        assert len(runners) == 1
        assert runners[0].status == RunnerStatus.STOPPED

    @patch("pathlib.Path.exists")
    @patch("pathlib.Path.open", new_callable=mock_open)
    @patch.object(StatePersister, "_compute_config_hash")
    def test_load_skips_invalid_entries(self, mock_hash, mock_file, mock_exists):
        """Test load skips invalid runner entries."""
        mock_exists.return_value = True
        mock_hash.return_value = "hash123"

        # Missing required field
        invalid_runner = {
            "runner_id": "test-123",
            # Missing project_path and other fields
        }
        valid_runner = {
            "runner_id": "test-456",
            "project_path": "/project",
            "spec_name": "test-spec",
            "provider": "codex",
            "model": "gpt-4",
            "pid": 12345,
            "status": "stopped",
            "started_at": "2025-12-17T14:30:00",
            "baseline_commit": "abc123",
        }
        state_data = json.dumps(
            {"config_hash": "hash123", "runners": [invalid_runner, valid_runner]}
        )
        mock_file.return_value.__enter__.return_value.read.return_value = state_data

        persister = StatePersister(Path("/cache"), Path("/config.json"))
        runners = persister.load()

        # Should only load the valid runner
        assert len(runners) == 1
        assert runners[0].runner_id == "test-456"

    @patch("pathlib.Path.exists")
    @patch("pathlib.Path.open", new_callable=mock_open)
    @patch("pathlib.Path.mkdir")
    @patch.object(StatePersister, "_compute_config_hash")
    @patch.object(StatePersister, "_is_pid_alive")
    def test_save_and_load_integration(
        self, mock_is_alive, mock_hash, mock_mkdir, mock_file, mock_exists
    ):
        """Test integration of save and load operations."""
        mock_hash.return_value = "hash123"
        mock_is_alive.return_value = True
        mock_exists.return_value = True

        persister = StatePersister(Path("/cache"), Path("/config.json"))

        # Create runners
        runner1 = RunnerState(
            runner_id="test-123",
            project_path=Path("/project1"),
            spec_name="spec1",
            provider="codex",
            model="gpt-4",
            pid=12345,
            status=RunnerStatus.RUNNING,
            started_at=datetime(2025, 12, 17, 14, 30, 0),
            baseline_commit="abc123",
        )
        runner2 = RunnerState(
            runner_id="test-456",
            project_path=Path("/project2"),
            spec_name="spec2",
            provider="claude",
            model="claude-3",
            pid=67890,
            status=RunnerStatus.STOPPED,
            started_at=datetime(2025, 12, 17, 15, 0, 0),
            baseline_commit="def456",
            exit_code=0,
        )

        # Save runners
        persister.save([runner1, runner2])

        # Get written data
        handle = mock_file()
        written_data = "".join(
            call.args[0] for call in handle.write.call_args_list if call.args
        )

        # Setup mock for reading
        mock_file.return_value.__enter__.return_value.read.return_value = written_data

        # Load runners
        loaded_runners = persister.load()

        # Verify
        assert len(loaded_runners) == 2
        assert loaded_runners[0].runner_id == "test-123"
        assert loaded_runners[1].runner_id == "test-456"
