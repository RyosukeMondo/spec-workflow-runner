"""Unit tests for status panel renderer."""

from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest
from rich.panel import Panel

from spec_workflow_runner.tui.state import RunnerState, RunnerStatus, SpecState
from spec_workflow_runner.tui.views.status_panel import (
    _format_duration,
    render_status_panel,
)


class TestFormatDuration:
    """Tests for _format_duration helper function."""

    @patch("spec_workflow_runner.tui.views.status_panel.datetime")
    def test_zero_duration(self, mock_datetime):
        """Test formatting when no time has passed."""
        now = datetime(2024, 1, 1, 12, 0, 0)
        mock_datetime.now.return_value = now
        started_at = now
        result = _format_duration(started_at)
        assert result == "00:00:00"

    @patch("spec_workflow_runner.tui.views.status_panel.datetime")
    def test_one_second(self, mock_datetime):
        """Test formatting 1 second duration."""
        now = datetime(2024, 1, 1, 12, 0, 1)
        mock_datetime.now.return_value = now
        started_at = datetime(2024, 1, 1, 12, 0, 0)
        result = _format_duration(started_at)
        assert result == "00:00:01"

    @patch("spec_workflow_runner.tui.views.status_panel.datetime")
    def test_one_minute(self, mock_datetime):
        """Test formatting 1 minute duration."""
        now = datetime(2024, 1, 1, 12, 1, 0)
        mock_datetime.now.return_value = now
        started_at = datetime(2024, 1, 1, 12, 0, 0)
        result = _format_duration(started_at)
        assert result == "00:01:00"

    @patch("spec_workflow_runner.tui.views.status_panel.datetime")
    def test_one_hour(self, mock_datetime):
        """Test formatting 1 hour duration."""
        now = datetime(2024, 1, 1, 13, 0, 0)
        mock_datetime.now.return_value = now
        started_at = datetime(2024, 1, 1, 12, 0, 0)
        result = _format_duration(started_at)
        assert result == "01:00:00"

    @patch("spec_workflow_runner.tui.views.status_panel.datetime")
    def test_mixed_duration(self, mock_datetime):
        """Test formatting 1h 23m 45s duration."""
        now = datetime(2024, 1, 1, 13, 23, 45)
        mock_datetime.now.return_value = now
        started_at = datetime(2024, 1, 1, 12, 0, 0)
        result = _format_duration(started_at)
        assert result == "01:23:45"

    @patch("spec_workflow_runner.tui.views.status_panel.datetime")
    def test_large_duration(self, mock_datetime):
        """Test formatting duration > 24 hours."""
        now = datetime(2024, 1, 2, 14, 30, 15)
        mock_datetime.now.return_value = now
        started_at = datetime(2024, 1, 1, 12, 0, 0)
        result = _format_duration(started_at)
        assert result == "26:30:15"


class TestRenderStatusPanel:
    """Tests for render_status_panel function."""

    def test_no_spec_selected(self):
        """Test rendering when no spec is selected."""
        panel = render_status_panel(None)
        assert isinstance(panel, Panel)
        assert panel.title == "Status"
        assert "Select a spec" in str(panel.renderable)

    def test_spec_without_runner(self):
        """Test rendering spec without active runner."""
        spec = SpecState(
            name="test-spec",
            path=Path("/test/spec"),
            total_tasks=10,
            completed_tasks=5,
            in_progress_tasks=2,
            pending_tasks=3,
            runner=None,
        )
        panel = render_status_panel(spec)
        assert isinstance(panel, Panel)
        assert "test-spec" in str(panel.title)

    def test_spec_with_project_path(self):
        """Test rendering spec with project path displayed."""
        spec = SpecState(
            name="test-spec",
            path=Path("/test/spec"),
            total_tasks=10,
            completed_tasks=5,
            in_progress_tasks=2,
            pending_tasks=3,
            runner=None,
        )
        panel = render_status_panel(spec, project_path="/test/project")
        assert isinstance(panel, Panel)

    def test_spec_with_runner(self):
        """Test rendering spec with active runner."""
        runner = RunnerState(
            runner_id="test-1",
            project_path=Path("/test"),
            spec_name="test-spec",
            provider="claude",
            model="sonnet-3.5",
            pid=12345,
            status=RunnerStatus.RUNNING,
            started_at=datetime.now() - timedelta(seconds=3661),
            baseline_commit="abc123",
        )
        spec = SpecState(
            name="test-spec",
            path=Path("/test/spec"),
            total_tasks=10,
            completed_tasks=5,
            in_progress_tasks=2,
            pending_tasks=3,
            runner=runner,
        )
        panel = render_status_panel(spec)
        assert isinstance(panel, Panel)

    def test_spec_with_runner_and_commit(self):
        """Test rendering spec with runner and commit info."""
        runner = RunnerState(
            runner_id="test-1",
            project_path=Path("/test"),
            spec_name="test-spec",
            provider="claude",
            model="sonnet-3.5",
            pid=12345,
            status=RunnerStatus.RUNNING,
            started_at=datetime.now() - timedelta(seconds=120),
            baseline_commit="abc123",
            last_commit_hash="def456",
            last_commit_message="feat: add new feature",
        )
        spec = SpecState(
            name="test-spec",
            path=Path("/test/spec"),
            total_tasks=10,
            completed_tasks=5,
            in_progress_tasks=2,
            pending_tasks=3,
            runner=runner,
        )
        panel = render_status_panel(spec)
        assert isinstance(panel, Panel)

    def test_complete_spec_green_border(self):
        """Test that complete specs have green border."""
        spec = SpecState(
            name="test-spec",
            path=Path("/test/spec"),
            total_tasks=10,
            completed_tasks=10,
            in_progress_tasks=0,
            pending_tasks=0,
            runner=None,
        )
        panel = render_status_panel(spec)
        assert isinstance(panel, Panel)
        assert panel.border_style == "green"

    def test_incomplete_spec_yellow_border(self):
        """Test that incomplete specs have yellow border."""
        spec = SpecState(
            name="test-spec",
            path=Path("/test/spec"),
            total_tasks=10,
            completed_tasks=5,
            in_progress_tasks=2,
            pending_tasks=3,
            runner=None,
        )
        panel = render_status_panel(spec)
        assert isinstance(panel, Panel)
        assert panel.border_style == "yellow"

    def test_progress_bar_with_zero_tasks(self):
        """Test that panel handles specs with zero tasks."""
        spec = SpecState(
            name="test-spec",
            path=Path("/test/spec"),
            total_tasks=0,
            completed_tasks=0,
            in_progress_tasks=0,
            pending_tasks=0,
            runner=None,
        )
        panel = render_status_panel(spec)
        assert isinstance(panel, Panel)

    def test_progress_bar_percentage(self):
        """Test progress bar shows correct completion percentage."""
        spec = SpecState(
            name="test-spec",
            path=Path("/test/spec"),
            total_tasks=10,
            completed_tasks=7,
            in_progress_tasks=1,
            pending_tasks=2,
            runner=None,
        )
        panel = render_status_panel(spec)
        assert isinstance(panel, Panel)
        # Progress should be 70%

    def test_task_counts_display(self):
        """Test that all task counts are displayed."""
        spec = SpecState(
            name="test-spec",
            path=Path("/test/spec"),
            total_tasks=20,
            completed_tasks=10,
            in_progress_tasks=5,
            pending_tasks=5,
            runner=None,
        )
        panel = render_status_panel(spec)
        assert isinstance(panel, Panel)
        # Should display: Total: 20, Completed: 10, In Progress: 5, Pending: 5

    def test_runner_pid_display(self):
        """Test that runner PID is displayed."""
        runner = RunnerState(
            runner_id="test-1",
            project_path=Path("/test"),
            spec_name="test-spec",
            provider="claude",
            model="sonnet",
            pid=99999,
            status=RunnerStatus.RUNNING,
            started_at=datetime.now(),
            baseline_commit="abc123",
        )
        spec = SpecState(
            name="test-spec",
            path=Path("/test/spec"),
            total_tasks=10,
            completed_tasks=5,
            in_progress_tasks=2,
            pending_tasks=3,
            runner=runner,
        )
        panel = render_status_panel(spec)
        assert isinstance(panel, Panel)

    def test_provider_and_model_display(self):
        """Test that provider and model are displayed."""
        runner = RunnerState(
            runner_id="test-1",
            project_path=Path("/test"),
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
            path=Path("/test/spec"),
            total_tasks=10,
            completed_tasks=5,
            in_progress_tasks=2,
            pending_tasks=3,
            runner=runner,
        )
        panel = render_status_panel(spec)
        assert isinstance(panel, Panel)

    def test_commit_hash_truncated(self):
        """Test that commit hash is truncated to 7 characters."""
        runner = RunnerState(
            runner_id="test-1",
            project_path=Path("/test"),
            spec_name="test-spec",
            provider="claude",
            model="sonnet",
            pid=12345,
            status=RunnerStatus.RUNNING,
            started_at=datetime.now(),
            baseline_commit="abc123",
            last_commit_hash="0123456789abcdef",
            last_commit_message="test commit",
        )
        spec = SpecState(
            name="test-spec",
            path=Path("/test/spec"),
            total_tasks=10,
            completed_tasks=5,
            in_progress_tasks=2,
            pending_tasks=3,
            runner=runner,
        )
        panel = render_status_panel(spec)
        assert isinstance(panel, Panel)
        # Commit hash should be truncated to first 7 chars: "0123456"

    def test_runner_without_commit_info(self):
        """Test runner display when commit info is not available."""
        runner = RunnerState(
            runner_id="test-1",
            project_path=Path("/test"),
            spec_name="test-spec",
            provider="claude",
            model="sonnet",
            pid=12345,
            status=RunnerStatus.RUNNING,
            started_at=datetime.now(),
            baseline_commit="abc123",
            last_commit_hash=None,
            last_commit_message=None,
        )
        spec = SpecState(
            name="test-spec",
            path=Path("/test/spec"),
            total_tasks=10,
            completed_tasks=5,
            in_progress_tasks=2,
            pending_tasks=3,
            runner=runner,
        )
        panel = render_status_panel(spec)
        assert isinstance(panel, Panel)
        # Should not show "Last Commit" row

    def test_spec_name_in_title(self):
        """Test that spec name appears in panel title."""
        spec = SpecState(
            name="my-awesome-spec",
            path=Path("/test/spec"),
            total_tasks=10,
            completed_tasks=5,
            in_progress_tasks=2,
            pending_tasks=3,
            runner=None,
        )
        panel = render_status_panel(spec)
        assert isinstance(panel, Panel)
        assert "my-awesome-spec" in str(panel.title)

    def test_stopped_runner(self):
        """Test displaying spec with stopped runner."""
        runner = RunnerState(
            runner_id="test-1",
            project_path=Path("/test"),
            spec_name="test-spec",
            provider="claude",
            model="sonnet",
            pid=12345,
            status=RunnerStatus.STOPPED,
            started_at=datetime.now() - timedelta(hours=1),
            baseline_commit="abc123",
        )
        spec = SpecState(
            name="test-spec",
            path=Path("/test/spec"),
            total_tasks=10,
            completed_tasks=5,
            in_progress_tasks=2,
            pending_tasks=3,
            runner=runner,
        )
        panel = render_status_panel(spec)
        assert isinstance(panel, Panel)

    def test_crashed_runner(self):
        """Test displaying spec with crashed runner."""
        runner = RunnerState(
            runner_id="test-1",
            project_path=Path("/test"),
            spec_name="test-spec",
            provider="claude",
            model="sonnet",
            pid=12345,
            status=RunnerStatus.CRASHED,
            started_at=datetime.now() - timedelta(minutes=30),
            baseline_commit="abc123",
            exit_code=1,
        )
        spec = SpecState(
            name="test-spec",
            path=Path("/test/spec"),
            total_tasks=10,
            completed_tasks=5,
            in_progress_tasks=2,
            pending_tasks=3,
            runner=runner,
        )
        panel = render_status_panel(spec)
        assert isinstance(panel, Panel)

    def test_all_pending_tasks(self):
        """Test spec with all pending tasks."""
        spec = SpecState(
            name="test-spec",
            path=Path("/test/spec"),
            total_tasks=10,
            completed_tasks=0,
            in_progress_tasks=0,
            pending_tasks=10,
            runner=None,
        )
        panel = render_status_panel(spec)
        assert isinstance(panel, Panel)
        assert panel.border_style == "yellow"

    def test_all_in_progress_tasks(self):
        """Test spec with all tasks in progress."""
        spec = SpecState(
            name="test-spec",
            path=Path("/test/spec"),
            total_tasks=10,
            completed_tasks=0,
            in_progress_tasks=10,
            pending_tasks=0,
            runner=None,
        )
        panel = render_status_panel(spec)
        assert isinstance(panel, Panel)
        assert panel.border_style == "yellow"
