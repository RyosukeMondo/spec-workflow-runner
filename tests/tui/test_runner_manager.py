"""Unit tests for RunnerManager subprocess lifecycle management."""

from __future__ import annotations

import signal
import subprocess
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, Mock, PropertyMock, call, mock_open, patch

import pytest

from spec_workflow_runner.providers import ClaudeProvider, CodexProvider, ProviderCommand
from spec_workflow_runner.tui.runner_manager import RunnerManager
from spec_workflow_runner.tui.state import RunnerState, RunnerStatus
from spec_workflow_runner.utils import Config


@pytest.fixture
def mock_config():
    """Create a mock Config object."""
    config = Mock(spec=Config)
    config.cache_dir = Path("/tmp/test-cache")
    config.spec_workflow_dir_name = ".spec-workflow"
    config.log_dir_name = "logs"
    config.log_file_template = "{spec_name}_{timestamp}.log"
    config.prompt_template = "Work on spec: {spec_name}"
    config.codex_config_overrides = []
    return config


@pytest.fixture
def mock_provider():
    """Create a mock ClaudeProvider."""
    provider = Mock(spec=ClaudeProvider)
    provider.get_provider_name.return_value = "Claude"
    provider.build_command.return_value = ProviderCommand(
        executable="claude", args=("--skip-permissions", "test prompt")
    )
    return provider


@pytest.fixture
def mock_persister():
    """Create a mock StatePersister."""
    with patch("spec_workflow_runner.tui.runner_manager.StatePersister") as mock_cls:
        persister = Mock()
        persister.load.return_value = []
        persister.save.return_value = None
        mock_cls.return_value = persister
        yield persister


@pytest.fixture
def runner_manager(mock_config, mock_persister):
    """Create a RunnerManager instance with mocked dependencies."""
    config_path = Path("/tmp/test-config.json")
    manager = RunnerManager(config=mock_config, config_path=config_path)
    return manager


class TestRunnerManagerInitialization:
    """Tests for RunnerManager initialization and restoration."""

    def test_initialization(self, mock_config, mock_persister):
        """Test RunnerManager initializes with correct attributes."""
        config_path = Path("/tmp/test-config.json")
        manager = RunnerManager(config=mock_config, config_path=config_path)

        assert manager.config == mock_config
        assert isinstance(manager.runners, dict)
        assert isinstance(manager.processes, dict)
        assert len(manager.runners) == 0
        assert len(manager.processes) == 0

    def test_restore_runners_on_init(self, mock_config, mock_persister):
        """Test that runners are restored from persister on initialization."""
        # Setup persister to return some runners
        mock_runner = RunnerState(
            runner_id="test-id",
            project_path=Path("/test/project"),
            spec_name="test-spec",
            provider="Claude",
            model="sonnet",
            pid=12345,
            status=RunnerStatus.STOPPED,
            started_at=datetime.now(),
            baseline_commit="abc123",
        )
        mock_persister.load.return_value = [mock_runner]

        config_path = Path("/tmp/test-config.json")
        manager = RunnerManager(config=mock_config, config_path=config_path)

        assert "test-id" in manager.runners
        assert manager.runners["test-id"] == mock_runner
        mock_persister.load.assert_called_once()


class TestStartRunner:
    """Tests for start_runner method."""

    @patch("spec_workflow_runner.tui.runner_manager.get_current_commit")
    @patch("spec_workflow_runner.tui.runner_manager.check_mcp_server_exists")
    @patch("spec_workflow_runner.tui.runner_manager.check_clean_working_tree")
    @patch("spec_workflow_runner.tui.runner_manager.subprocess.Popen")
    @patch("spec_workflow_runner.tui.runner_manager.uuid.uuid4")
    @patch("pathlib.Path.open", new_callable=mock_open)
    @patch("pathlib.Path.mkdir")
    def test_start_runner_success(
        self,
        mock_mkdir,
        mock_path_open,
        mock_uuid,
        mock_popen,
        mock_check_clean,
        mock_check_mcp,
        mock_get_commit,
        runner_manager,
        mock_provider,
        mock_persister,
    ):
        """Test successful runner start with all preconditions met."""
        # Setup mocks
        mock_uuid.return_value = Mock(hex="test-uuid-1234")
        mock_check_clean.return_value = None  # No exception means clean
        mock_check_mcp.return_value = None  # No exception means exists
        mock_get_commit.return_value = "baseline-commit-abc"

        mock_process = Mock()
        mock_process.pid = 99999
        mock_popen.return_value = mock_process

        # Execute
        project_path = Path("/test/project")
        spec_name = "test-spec"
        model = "sonnet"

        runner = runner_manager.start_runner(
            project_path=project_path,
            spec_name=spec_name,
            provider=mock_provider,
            model=model,
        )

        # Verify preconditions were checked
        mock_check_clean.assert_called_once_with(project_path)
        mock_check_mcp.assert_called_once_with(mock_provider, project_path)
        mock_get_commit.assert_called_once_with(project_path)

        # Verify runner state
        assert runner.spec_name == spec_name
        assert runner.provider == "Claude"
        assert runner.model == model
        assert runner.pid == 99999
        assert runner.status == RunnerStatus.RUNNING
        assert runner.baseline_commit == "baseline-commit-abc"

        # Verify runner stored in manager
        assert str(mock_uuid.return_value) in runner_manager.runners
        assert str(mock_uuid.return_value) in runner_manager.processes

        # Verify state persisted
        mock_persister.save.assert_called()

    @patch("spec_workflow_runner.tui.runner_manager.check_clean_working_tree")
    def test_start_runner_fails_dirty_tree(
        self, mock_check_clean, runner_manager, mock_provider
    ):
        """Test start_runner fails when working tree is dirty."""
        mock_check_clean.side_effect = Exception("Working tree is dirty")

        project_path = Path("/test/project")
        spec_name = "test-spec"
        model = "sonnet"

        with pytest.raises(Exception, match="Working tree is dirty"):
            runner_manager.start_runner(
                project_path=project_path,
                spec_name=spec_name,
                provider=mock_provider,
                model=model,
            )

    @patch("spec_workflow_runner.tui.runner_manager.check_clean_working_tree")
    @patch("spec_workflow_runner.tui.runner_manager.check_mcp_server_exists")
    def test_start_runner_fails_missing_mcp(
        self, mock_check_mcp, mock_check_clean, runner_manager, mock_provider
    ):
        """Test start_runner fails when MCP server is missing."""
        mock_check_clean.return_value = None
        mock_check_mcp.side_effect = Exception("MCP server not found")

        project_path = Path("/test/project")
        spec_name = "test-spec"
        model = "sonnet"

        with pytest.raises(Exception, match="MCP server not found"):
            runner_manager.start_runner(
                project_path=project_path,
                spec_name=spec_name,
                provider=mock_provider,
                model=model,
            )

    @patch("spec_workflow_runner.tui.runner_manager.get_current_commit")
    @patch("spec_workflow_runner.tui.runner_manager.check_mcp_server_exists")
    @patch("spec_workflow_runner.tui.runner_manager.check_clean_working_tree")
    @patch("spec_workflow_runner.tui.runner_manager.subprocess.Popen")
    @patch("pathlib.Path.open", new_callable=mock_open)
    @patch("pathlib.Path.mkdir")
    def test_start_runner_creates_log_directory(
        self,
        mock_mkdir,
        mock_path_open,
        mock_popen,
        mock_check_clean,
        mock_check_mcp,
        mock_get_commit,
        runner_manager,
        mock_provider,
    ):
        """Test that start_runner creates log directory if it doesn't exist."""
        mock_check_clean.return_value = None
        mock_check_mcp.return_value = None
        mock_get_commit.return_value = "abc123"

        mock_process = Mock()
        mock_process.pid = 11111
        mock_popen.return_value = mock_process

        project_path = Path("/test/project")

        runner_manager.start_runner(
            project_path=project_path,
            spec_name="test-spec",
            provider=mock_provider,
            model="sonnet",
        )

        # Verify mkdir was called with parents=True, exist_ok=True
        assert mock_mkdir.call_count >= 1
        calls = mock_mkdir.call_args_list
        assert any(
            call_args.kwargs.get("parents") is True
            and call_args.kwargs.get("exist_ok") is True
            for call_args in calls
        )


class TestStopRunner:
    """Tests for stop_runner method."""

    def test_stop_runner_not_found(self, runner_manager):
        """Test stop_runner raises KeyError for unknown runner_id."""
        with pytest.raises(KeyError, match="Runner.*not found"):
            runner_manager.stop_runner("nonexistent-id")

    @patch("spec_workflow_runner.tui.runner_manager.subprocess.Popen")
    def test_stop_runner_no_process_handle(
        self, mock_popen, runner_manager, mock_persister
    ):
        """Test stop_runner handles missing process handle gracefully."""
        # Add a runner without a process
        runner = RunnerState(
            runner_id="test-id",
            project_path=Path("/test"),
            spec_name="test-spec",
            provider="Claude",
            model="sonnet",
            pid=12345,
            status=RunnerStatus.RUNNING,
            started_at=datetime.now(),
            baseline_commit="abc123",
        )
        runner_manager.runners["test-id"] = runner

        # Stop without process handle
        runner_manager.stop_runner("test-id")

        # Verify status updated to STOPPED
        assert runner_manager.runners["test-id"].status == RunnerStatus.STOPPED
        assert runner_manager.runners["test-id"].exit_code == 0
        mock_persister.save.assert_called()

    @patch("spec_workflow_runner.tui.runner_manager.subprocess.Popen")
    def test_stop_runner_sigterm_success(
        self, mock_popen, runner_manager, mock_persister
    ):
        """Test stop_runner sends SIGTERM and waits successfully."""
        # Setup runner and process
        runner = RunnerState(
            runner_id="test-id",
            project_path=Path("/test"),
            spec_name="test-spec",
            provider="Claude",
            model="sonnet",
            pid=12345,
            status=RunnerStatus.RUNNING,
            started_at=datetime.now(),
            baseline_commit="abc123",
        )
        runner_manager.runners["test-id"] = runner

        mock_process = Mock()
        mock_process.send_signal = Mock()
        mock_process.wait = Mock(return_value=0)  # Exit code 0
        mock_process.poll = Mock(return_value=0)
        runner_manager.processes["test-id"] = mock_process

        # Stop runner
        runner_manager.stop_runner("test-id", timeout=5)

        # Verify SIGTERM sent
        mock_process.send_signal.assert_called_once_with(signal.SIGTERM)
        mock_process.wait.assert_called_once_with(timeout=5)

        # Verify status updated
        assert runner_manager.runners["test-id"].status == RunnerStatus.STOPPED
        assert runner_manager.runners["test-id"].exit_code == 0
        assert "test-id" not in runner_manager.processes
        mock_persister.save.assert_called()

    @patch("spec_workflow_runner.tui.runner_manager.subprocess.Popen")
    def test_stop_runner_sigterm_non_zero_exit(
        self, mock_popen, runner_manager, mock_persister
    ):
        """Test stop_runner marks runner as CRASHED on non-zero exit."""
        runner = RunnerState(
            runner_id="test-id",
            project_path=Path("/test"),
            spec_name="test-spec",
            provider="Claude",
            model="sonnet",
            pid=12345,
            status=RunnerStatus.RUNNING,
            started_at=datetime.now(),
            baseline_commit="abc123",
        )
        runner_manager.runners["test-id"] = runner

        mock_process = Mock()
        mock_process.send_signal = Mock()
        mock_process.wait = Mock(return_value=1)  # Exit code 1 (error)
        runner_manager.processes["test-id"] = mock_process

        runner_manager.stop_runner("test-id", timeout=5)

        # Verify status is CRASHED
        assert runner_manager.runners["test-id"].status == RunnerStatus.CRASHED
        assert runner_manager.runners["test-id"].exit_code == 1

    @patch("spec_workflow_runner.tui.runner_manager.subprocess.Popen")
    def test_stop_runner_sigkill_escalation(
        self, mock_popen, runner_manager, mock_persister
    ):
        """Test stop_runner escalates to SIGKILL on timeout."""
        runner = RunnerState(
            runner_id="test-id",
            project_path=Path("/test"),
            spec_name="test-spec",
            provider="Claude",
            model="sonnet",
            pid=12345,
            status=RunnerStatus.RUNNING,
            started_at=datetime.now(),
            baseline_commit="abc123",
        )
        runner_manager.runners["test-id"] = runner

        mock_process = Mock()
        mock_process.send_signal = Mock()
        # First wait times out, second wait (after kill) succeeds
        mock_process.wait = Mock(
            side_effect=[subprocess.TimeoutExpired("cmd", 5), -9]
        )
        mock_process.kill = Mock()
        runner_manager.processes["test-id"] = mock_process

        runner_manager.stop_runner("test-id", timeout=5)

        # Verify SIGTERM sent first
        mock_process.send_signal.assert_called_once_with(signal.SIGTERM)
        # Verify SIGKILL sent after timeout
        mock_process.kill.assert_called_once()
        # Verify status is CRASHED
        assert runner_manager.runners["test-id"].status == RunnerStatus.CRASHED
        assert runner_manager.runners["test-id"].exit_code == -9

    @patch("spec_workflow_runner.tui.runner_manager.subprocess.Popen")
    def test_stop_runner_process_already_exited(
        self, mock_popen, runner_manager, mock_persister
    ):
        """Test stop_runner handles ProcessLookupError gracefully."""
        runner = RunnerState(
            runner_id="test-id",
            project_path=Path("/test"),
            spec_name="test-spec",
            provider="Claude",
            model="sonnet",
            pid=12345,
            status=RunnerStatus.RUNNING,
            started_at=datetime.now(),
            baseline_commit="abc123",
        )
        runner_manager.runners["test-id"] = runner

        mock_process = Mock()
        mock_process.send_signal = Mock(side_effect=ProcessLookupError())
        mock_process.poll = Mock(return_value=0)
        runner_manager.processes["test-id"] = mock_process

        runner_manager.stop_runner("test-id")

        # Verify status updated
        assert runner_manager.runners["test-id"].status == RunnerStatus.STOPPED
        assert "test-id" not in runner_manager.processes


class TestGetActiveRunners:
    """Tests for get_active_runners method."""

    def test_get_active_runners_empty(self, runner_manager):
        """Test get_active_runners returns empty list when no runners."""
        active = runner_manager.get_active_runners()
        assert active == []

    def test_get_active_runners_filters_by_status(self, runner_manager):
        """Test get_active_runners returns only RUNNING runners."""
        # Add runners with different statuses
        runner1 = RunnerState(
            runner_id="id1",
            project_path=Path("/test"),
            spec_name="spec1",
            provider="Claude",
            model="sonnet",
            pid=111,
            status=RunnerStatus.RUNNING,
            started_at=datetime.now(),
            baseline_commit="abc",
        )
        runner2 = RunnerState(
            runner_id="id2",
            project_path=Path("/test"),
            spec_name="spec2",
            provider="Claude",
            model="sonnet",
            pid=222,
            status=RunnerStatus.STOPPED,
            started_at=datetime.now(),
            baseline_commit="def",
        )
        runner3 = RunnerState(
            runner_id="id3",
            project_path=Path("/test"),
            spec_name="spec3",
            provider="Claude",
            model="sonnet",
            pid=333,
            status=RunnerStatus.RUNNING,
            started_at=datetime.now(),
            baseline_commit="ghi",
        )

        runner_manager.runners = {"id1": runner1, "id2": runner2, "id3": runner3}

        active = runner_manager.get_active_runners()

        assert len(active) == 2
        assert runner1 in active
        assert runner3 in active
        assert runner2 not in active


class TestCheckRunnerHealth:
    """Tests for check_runner_health method."""

    def test_check_runner_health_not_found(self, runner_manager):
        """Test check_runner_health raises KeyError for unknown runner."""
        with pytest.raises(KeyError, match="Runner.*not found"):
            runner_manager.check_runner_health("nonexistent-id")

    def test_check_runner_health_not_running(self, runner_manager):
        """Test check_runner_health returns current status if not RUNNING."""
        runner = RunnerState(
            runner_id="test-id",
            project_path=Path("/test"),
            spec_name="test-spec",
            provider="Claude",
            model="sonnet",
            pid=12345,
            status=RunnerStatus.STOPPED,
            started_at=datetime.now(),
            baseline_commit="abc",
        )
        runner_manager.runners["test-id"] = runner

        status = runner_manager.check_runner_health("test-id")
        assert status == RunnerStatus.STOPPED

    def test_check_runner_health_no_process_handle(
        self, runner_manager, mock_persister
    ):
        """Test check_runner_health marks as CRASHED when no process handle."""
        runner = RunnerState(
            runner_id="test-id",
            project_path=Path("/test"),
            spec_name="test-spec",
            provider="Claude",
            model="sonnet",
            pid=12345,
            status=RunnerStatus.RUNNING,
            started_at=datetime.now(),
            baseline_commit="abc",
        )
        runner_manager.runners["test-id"] = runner

        status = runner_manager.check_runner_health("test-id")

        assert status == RunnerStatus.CRASHED
        assert runner_manager.runners["test-id"].status == RunnerStatus.CRASHED

    def test_check_runner_health_still_running(self, runner_manager):
        """Test check_runner_health returns RUNNING when process alive."""
        runner = RunnerState(
            runner_id="test-id",
            project_path=Path("/test"),
            spec_name="test-spec",
            provider="Claude",
            model="sonnet",
            pid=12345,
            status=RunnerStatus.RUNNING,
            started_at=datetime.now(),
            baseline_commit="abc",
        )
        runner_manager.runners["test-id"] = runner

        mock_process = Mock()
        mock_process.poll = Mock(return_value=None)  # Still running
        runner_manager.processes["test-id"] = mock_process

        status = runner_manager.check_runner_health("test-id")

        assert status == RunnerStatus.RUNNING
        mock_process.poll.assert_called_once()

    def test_check_runner_health_completed(self, runner_manager, mock_persister):
        """Test check_runner_health marks as COMPLETED on exit code 0."""
        runner = RunnerState(
            runner_id="test-id",
            project_path=Path("/test"),
            spec_name="test-spec",
            provider="Claude",
            model="sonnet",
            pid=12345,
            status=RunnerStatus.RUNNING,
            started_at=datetime.now(),
            baseline_commit="abc",
        )
        runner_manager.runners["test-id"] = runner

        mock_process = Mock()
        mock_process.poll = Mock(return_value=0)  # Exited successfully
        runner_manager.processes["test-id"] = mock_process

        status = runner_manager.check_runner_health("test-id")

        assert status == RunnerStatus.COMPLETED
        assert runner_manager.runners["test-id"].status == RunnerStatus.COMPLETED
        assert runner_manager.runners["test-id"].exit_code == 0
        assert "test-id" not in runner_manager.processes

    def test_check_runner_health_crashed(self, runner_manager, mock_persister):
        """Test check_runner_health marks as CRASHED on non-zero exit."""
        runner = RunnerState(
            runner_id="test-id",
            project_path=Path("/test"),
            spec_name="test-spec",
            provider="Claude",
            model="sonnet",
            pid=12345,
            status=RunnerStatus.RUNNING,
            started_at=datetime.now(),
            baseline_commit="abc",
        )
        runner_manager.runners["test-id"] = runner

        mock_process = Mock()
        mock_process.poll = Mock(return_value=1)  # Exited with error
        runner_manager.processes["test-id"] = mock_process

        status = runner_manager.check_runner_health("test-id")

        assert status == RunnerStatus.CRASHED
        assert runner_manager.runners["test-id"].status == RunnerStatus.CRASHED
        assert runner_manager.runners["test-id"].exit_code == 1


class TestDetectNewCommits:
    """Tests for detect_new_commits method."""

    def test_detect_new_commits_runner_not_found(self, runner_manager):
        """Test detect_new_commits raises KeyError for unknown runner."""
        with pytest.raises(KeyError, match="Runner.*not found"):
            runner_manager.detect_new_commits("nonexistent-id")

    @patch("spec_workflow_runner.tui.runner_manager.get_current_commit")
    def test_detect_new_commits_no_changes(
        self, mock_get_commit, runner_manager
    ):
        """Test detect_new_commits returns None when no new commits."""
        runner = RunnerState(
            runner_id="test-id",
            project_path=Path("/test"),
            spec_name="test-spec",
            provider="Claude",
            model="sonnet",
            pid=12345,
            status=RunnerStatus.RUNNING,
            started_at=datetime.now(),
            baseline_commit="abc123",
        )
        runner_manager.runners["test-id"] = runner

        # Mock: current commit same as baseline
        mock_get_commit.return_value = "abc123"

        commit_hash, commit_msg = runner_manager.detect_new_commits("test-id")

        assert commit_hash is None
        assert commit_msg is None

    @patch("spec_workflow_runner.tui.runner_manager.subprocess.run")
    @patch("spec_workflow_runner.tui.runner_manager.get_current_commit")
    def test_detect_new_commits_has_new_commit(
        self, mock_get_commit, mock_run, runner_manager
    ):
        """Test detect_new_commits returns hash and message for new commit."""
        runner = RunnerState(
            runner_id="test-id",
            project_path=Path("/test"),
            spec_name="test-spec",
            provider="Claude",
            model="sonnet",
            pid=12345,
            status=RunnerStatus.RUNNING,
            started_at=datetime.now(),
            baseline_commit="abc123",
        )
        runner_manager.runners["test-id"] = runner

        # Mock: current commit different from baseline
        mock_get_commit.return_value = "def456"

        # Mock git log output
        mock_result = Mock()
        mock_result.stdout = "def456 Add new feature\n"
        mock_run.return_value = mock_result

        commit_hash, commit_msg = runner_manager.detect_new_commits("test-id")

        assert commit_hash == "def456"
        assert commit_msg == "Add new feature"
        mock_run.assert_called_once()

    @patch("spec_workflow_runner.tui.runner_manager.subprocess.run")
    @patch("spec_workflow_runner.tui.runner_manager.get_current_commit")
    def test_detect_new_commits_git_error(
        self, mock_get_commit, mock_run, runner_manager
    ):
        """Test detect_new_commits returns None on git error."""
        runner = RunnerState(
            runner_id="test-id",
            project_path=Path("/test"),
            spec_name="test-spec",
            provider="Claude",
            model="sonnet",
            pid=12345,
            status=RunnerStatus.RUNNING,
            started_at=datetime.now(),
            baseline_commit="abc123",
        )
        runner_manager.runners["test-id"] = runner

        mock_get_commit.return_value = "def456"
        mock_run.side_effect = subprocess.CalledProcessError(1, "git log")

        commit_hash, commit_msg = runner_manager.detect_new_commits("test-id")

        assert commit_hash is None
        assert commit_msg is None

    @patch("spec_workflow_runner.tui.runner_manager.subprocess.run")
    @patch("spec_workflow_runner.tui.runner_manager.get_current_commit")
    def test_detect_new_commits_empty_output(
        self, mock_get_commit, mock_run, runner_manager
    ):
        """Test detect_new_commits returns None when git log output is empty."""
        runner = RunnerState(
            runner_id="test-id",
            project_path=Path("/test"),
            spec_name="test-spec",
            provider="Claude",
            model="sonnet",
            pid=12345,
            status=RunnerStatus.RUNNING,
            started_at=datetime.now(),
            baseline_commit="abc123",
        )
        runner_manager.runners["test-id"] = runner

        mock_get_commit.return_value = "def456"

        # Mock git log returning empty output
        mock_result = Mock()
        mock_result.stdout = ""
        mock_run.return_value = mock_result

        commit_hash, commit_msg = runner_manager.detect_new_commits("test-id")

        assert commit_hash is None
        assert commit_msg is None


class TestShutdown:
    """Tests for shutdown method."""

    @patch("spec_workflow_runner.tui.runner_manager.subprocess.Popen")
    def test_shutdown_stop_all(self, mock_popen, runner_manager, mock_persister):
        """Test shutdown stops all active runners."""
        # Add active runners
        runner1 = RunnerState(
            runner_id="id1",
            project_path=Path("/test"),
            spec_name="spec1",
            provider="Claude",
            model="sonnet",
            pid=111,
            status=RunnerStatus.RUNNING,
            started_at=datetime.now(),
            baseline_commit="abc",
        )
        runner2 = RunnerState(
            runner_id="id2",
            project_path=Path("/test"),
            spec_name="spec2",
            provider="Claude",
            model="sonnet",
            pid=222,
            status=RunnerStatus.RUNNING,
            started_at=datetime.now(),
            baseline_commit="def",
        )

        runner_manager.runners = {"id1": runner1, "id2": runner2}

        # Add mock processes
        mock_proc1 = Mock()
        mock_proc1.send_signal = Mock()
        mock_proc1.wait = Mock(return_value=0)
        mock_proc2 = Mock()
        mock_proc2.send_signal = Mock()
        mock_proc2.wait = Mock(return_value=0)

        runner_manager.processes = {"id1": mock_proc1, "id2": mock_proc2}

        # Shutdown with stop_all=True
        runner_manager.shutdown(stop_all=True, timeout=10)

        # Verify both processes were stopped
        assert mock_proc1.send_signal.called
        assert mock_proc2.send_signal.called
        # Verify state persisted
        mock_persister.save.assert_called()

    def test_shutdown_detach(self, runner_manager, mock_persister):
        """Test shutdown with stop_all=False leaves runners running."""
        # Add active runner
        runner = RunnerState(
            runner_id="id1",
            project_path=Path("/test"),
            spec_name="spec1",
            provider="Claude",
            model="sonnet",
            pid=111,
            status=RunnerStatus.RUNNING,
            started_at=datetime.now(),
            baseline_commit="abc",
        )
        runner_manager.runners = {"id1": runner}

        mock_process = Mock()
        runner_manager.processes = {"id1": mock_process}

        # Shutdown with stop_all=False
        runner_manager.shutdown(stop_all=False)

        # Verify process not stopped
        mock_process.send_signal.assert_not_called()
        # Verify state still persisted
        mock_persister.save.assert_called()

    @patch("spec_workflow_runner.tui.runner_manager.subprocess.Popen")
    def test_shutdown_handles_errors(self, mock_popen, runner_manager, mock_persister):
        """Test shutdown continues even if stopping a runner fails."""
        runner1 = RunnerState(
            runner_id="id1",
            project_path=Path("/test"),
            spec_name="spec1",
            provider="Claude",
            model="sonnet",
            pid=111,
            status=RunnerStatus.RUNNING,
            started_at=datetime.now(),
            baseline_commit="abc",
        )

        runner_manager.runners = {"id1": runner1}

        # Mock process that raises error on stop
        mock_proc = Mock()
        mock_proc.send_signal = Mock(side_effect=Exception("Test error"))
        runner_manager.processes = {"id1": mock_proc}

        # Shutdown should not raise
        runner_manager.shutdown(stop_all=True)

        # Verify state persisted despite error
        mock_persister.save.assert_called()
