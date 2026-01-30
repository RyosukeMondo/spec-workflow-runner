"""Tests for subprocess monitoring functionality."""

from __future__ import annotations

import subprocess
import time
from unittest.mock import Mock, patch

import pytest

from spec_workflow_runner.subprocess_helpers import (
    monitor_process_with_timeout,
    safe_terminate_process,
)


class TestMonitorProcessWithTimeout:
    """Tests for monitor_process_with_timeout function."""

    def test_successful_completion(self):
        """Test monitoring a process that completes successfully."""
        # Mock process that exits with code 0
        mock_process = Mock(spec=subprocess.Popen)
        mock_process.poll.return_value = 0  # Process has exited
        mock_process.returncode = 0
        mock_process.stdout = Mock()
        mock_process.stdout.read.return_value = ""

        exit_code, error = monitor_process_with_timeout(mock_process, timeout_seconds=10)

        assert exit_code == 0
        assert error is None

    def test_process_failure(self):
        """Test monitoring a process that fails."""
        # Mock process that exits with non-zero code
        mock_process = Mock(spec=subprocess.Popen)
        mock_process.poll.return_value = 1  # Process has exited with error
        mock_process.returncode = 1
        mock_process.stdout = Mock()
        mock_process.stdout.read.return_value = "Error occurred\n"

        exit_code, error = monitor_process_with_timeout(mock_process, timeout_seconds=10)

        assert exit_code == 1
        assert error == "Error occurred\n"

    def test_activity_callback(self):
        """Test activity callback is called with output."""
        output_lines = ["Line 1\n", "Line 2\n", ""]
        mock_process = Mock(spec=subprocess.Popen)
        mock_process.poll.side_effect = [None, None, 0]  # Running, running, then done
        mock_process.returncode = 0
        mock_process.stdout = Mock()
        mock_process.stdout.readline.side_effect = output_lines
        mock_process.stdout.read.return_value = ""

        callback = Mock()
        exit_code, error = monitor_process_with_timeout(
            mock_process,
            timeout_seconds=10,
            on_activity=callback,
        )

        assert exit_code == 0
        assert callback.call_count == 2  # Called for each line
        callback.assert_any_call("Line 1\n")
        callback.assert_any_call("Line 2\n")

    @patch('spec_workflow_runner.subprocess_helpers.time.time')
    @patch('spec_workflow_runner.subprocess_helpers.time.sleep')
    def test_timeout_detection(self, mock_sleep, mock_time):
        """Test timeout detection when process hangs."""
        # Simulate time passing - provide enough values for all calls
        time_values = [1000.0, 1000.0, 1000.1]
        # Add more values to handle all the time.time() calls
        time_values.extend([1301.0] * 20)  # Provide plenty of timeout values
        mock_time.side_effect = time_values

        # Mock process that never exits and produces no output
        mock_process = Mock(spec=subprocess.Popen)
        mock_process.poll.return_value = None  # Still running
        mock_process.pid = 12345
        mock_process.stdout = Mock()
        mock_process.stdout.readline.return_value = ""  # No output

        exit_code, error = monitor_process_with_timeout(mock_process, timeout_seconds=300)

        assert exit_code is None
        assert "timed out" in error
        mock_process.terminate.assert_called_once()


class TestSafeTerminateProcess:
    """Tests for safe_terminate_process function."""

    def test_graceful_termination(self):
        """Test process terminates gracefully."""
        mock_process = Mock()
        mock_process.wait.return_value = None  # Terminates successfully

        safe_terminate_process(mock_process, timeout=5)

        mock_process.terminate.assert_called_once()
        mock_process.wait.assert_called_once_with(timeout=5)
        mock_process.kill.assert_not_called()

    def test_force_kill_on_timeout(self):
        """Test process is killed if it doesn't terminate gracefully."""
        mock_process = Mock()
        mock_process.wait.side_effect = [
            subprocess.TimeoutExpired("cmd", 5),  # First wait times out
            None,  # Second wait (after kill) succeeds
        ]
        mock_process.pid = 12345

        safe_terminate_process(mock_process, timeout=5)

        mock_process.terminate.assert_called_once()
        assert mock_process.wait.call_count == 2
        mock_process.kill.assert_called_once()

    def test_handle_exception(self):
        """Test exception handling during termination."""
        mock_process = Mock()
        mock_process.terminate.side_effect = OSError("Process not found")
        mock_process.pid = 12345

        # Should not raise exception
        safe_terminate_process(mock_process, timeout=5)

        mock_process.terminate.assert_called_once()
