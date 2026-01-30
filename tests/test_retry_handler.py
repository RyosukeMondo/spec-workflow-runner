"""Tests for retry handler functionality."""

from __future__ import annotations

import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

from spec_workflow_runner.retry_handler import (
    RetryAttempt,
    RetryConfig,
    RetryContext,
    RetryHandler,
    create_retry_handler,
)


class TestRetryConfig:
    """Tests for RetryConfig dataclass."""

    def test_default_values(self):
        """Test default configuration values."""
        config = RetryConfig()
        assert config.max_retries == 3
        assert config.retry_backoff_seconds == 5
        assert config.retry_on_crash is True
        assert config.activity_timeout_seconds == 300
        assert config.backoff_multiplier == 2.0
        assert config.max_backoff_seconds == 300

    def test_custom_values(self):
        """Test custom configuration values."""
        config = RetryConfig(
            max_retries=5,
            retry_backoff_seconds=10,
            retry_on_crash=False,
            backoff_multiplier=1.5,
        )
        assert config.max_retries == 5
        assert config.retry_backoff_seconds == 10
        assert config.retry_on_crash is False
        assert config.backoff_multiplier == 1.5


class TestRetryContext:
    """Tests for RetryContext."""

    def test_initial_state(self):
        """Test initial retry context state."""
        ctx = RetryContext(
            runner_id="test-123",
            spec_name="my-spec",
            project_path=Path("/test/path"),
        )
        assert ctx.runner_id == "test-123"
        assert ctx.spec_name == "my-spec"
        assert ctx.attempt_count == 0
        assert len(ctx.attempts) == 0

    def test_add_attempt(self):
        """Test adding retry attempts."""
        ctx = RetryContext(
            runner_id="test-123",
            spec_name="my-spec",
            project_path=Path("/test/path"),
        )

        ctx.add_attempt(exit_code=1, error_message="Failed", duration=10.5)
        assert ctx.attempt_count == 1
        assert len(ctx.attempts) == 1
        assert ctx.attempts[0].attempt_number == 1
        assert ctx.attempts[0].exit_code == 1
        assert ctx.attempts[0].error_message == "Failed"
        assert ctx.attempts[0].duration_seconds == 10.5

    def test_multiple_attempts(self):
        """Test tracking multiple retry attempts."""
        ctx = RetryContext(
            runner_id="test-123",
            spec_name="my-spec",
            project_path=Path("/test/path"),
        )

        ctx.add_attempt(exit_code=1, error_message="Error 1", duration=5.0)
        ctx.add_attempt(exit_code=2, error_message="Error 2", duration=6.0)
        ctx.add_attempt(exit_code=0, error_message=None, duration=7.0)

        assert ctx.attempt_count == 3
        assert ctx.attempts[0].attempt_number == 1
        assert ctx.attempts[1].attempt_number == 2
        assert ctx.attempts[2].attempt_number == 3

    def test_to_dict(self):
        """Test serialization to dictionary."""
        ctx = RetryContext(
            runner_id="test-123",
            spec_name="my-spec",
            project_path=Path("/test/path"),
        )
        ctx.add_attempt(exit_code=1, error_message="Failed", duration=10.0)

        data = ctx.to_dict()
        assert data["runner_id"] == "test-123"
        assert data["spec_name"] == "my-spec"
        assert data["attempt_count"] == 1
        assert len(data["attempts"]) == 1
        assert data["attempts"][0]["exit_code"] == 1


class TestRetryHandler:
    """Tests for RetryHandler."""

    @pytest.fixture
    def temp_log_dir(self, tmp_path):
        """Create temporary log directory."""
        log_dir = tmp_path / "retry_logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        return log_dir

    @pytest.fixture
    def handler(self, temp_log_dir):
        """Create RetryHandler with temporary log directory."""
        config = RetryConfig(
            max_retries=3,
            retry_backoff_seconds=1,  # Fast for testing
            retry_on_crash=True,
            retry_log_dir=temp_log_dir,
        )
        return RetryHandler(config)

    def test_calculate_backoff(self, handler):
        """Test exponential backoff calculation."""
        # Default: backoff = 1 * (2.0 ^ attempt)
        assert handler._calculate_backoff(1) == 1.0  # 1 * 2^0
        assert handler._calculate_backoff(2) == 2.0  # 1 * 2^1
        assert handler._calculate_backoff(3) == 4.0  # 1 * 2^2
        assert handler._calculate_backoff(4) == 8.0  # 1 * 2^3

    def test_calculate_backoff_with_cap(self, temp_log_dir):
        """Test backoff calculation with maximum cap."""
        config = RetryConfig(
            retry_backoff_seconds=10,
            backoff_multiplier=2.0,
            max_backoff_seconds=30,
            retry_log_dir=temp_log_dir,
        )
        handler = RetryHandler(config)

        assert handler._calculate_backoff(1) == 10.0  # 10 * 2^0
        assert handler._calculate_backoff(2) == 20.0  # 10 * 2^1
        assert handler._calculate_backoff(3) == 30.0  # 10 * 2^2 = 40, capped at 30
        assert handler._calculate_backoff(4) == 30.0  # Capped

    def test_should_retry_disabled(self, temp_log_dir):
        """Test retry disabled in config."""
        config = RetryConfig(retry_on_crash=False, retry_log_dir=temp_log_dir)
        handler = RetryHandler(config)

        ctx = RetryContext(
            runner_id="test-123",
            spec_name="my-spec",
            project_path=Path("/test"),
        )

        assert handler._should_retry(ctx, exit_code=1) is False

    def test_should_retry_max_exceeded(self, handler):
        """Test max retries exceeded."""
        ctx = RetryContext(
            runner_id="test-123",
            spec_name="my-spec",
            project_path=Path("/test"),
        )

        # Add 3 failed attempts (max_retries=3)
        ctx.add_attempt(1, "Error", 1.0)
        ctx.add_attempt(1, "Error", 1.0)
        ctx.add_attempt(1, "Error", 1.0)

        assert ctx.attempt_count == 3
        assert handler._should_retry(ctx, exit_code=1) is False

    def test_should_retry_on_failure(self, handler):
        """Test retry on non-zero exit code."""
        ctx = RetryContext(
            runner_id="test-123",
            spec_name="my-spec",
            project_path=Path("/test"),
        )

        # First failure - should retry
        assert handler._should_retry(ctx, exit_code=1) is True

        # Add attempt and check again
        ctx.add_attempt(1, "Error", 1.0)
        assert handler._should_retry(ctx, exit_code=1) is True

    def test_should_not_retry_on_success(self, handler):
        """Test no retry on successful exit."""
        ctx = RetryContext(
            runner_id="test-123",
            spec_name="my-spec",
            project_path=Path("/test"),
        )

        assert handler._should_retry(ctx, exit_code=0) is False

    def test_execute_with_retry_success_first_try(self, handler):
        """Test successful execution on first try."""
        ctx = RetryContext(
            runner_id="test-123",
            spec_name="my-spec",
            project_path=Path("/test"),
        )

        # Mock subprocess that succeeds immediately
        mock_process = Mock()
        command_fn = Mock(return_value=mock_process)
        monitor_fn = Mock(return_value=(0, None))  # Success

        success, result_ctx = handler.execute_with_retry(ctx, command_fn, monitor_fn)

        assert success is True
        assert result_ctx.attempt_count == 1
        assert command_fn.call_count == 1
        assert monitor_fn.call_count == 1

    def test_execute_with_retry_failure_then_success(self, handler):
        """Test retry after initial failure."""
        ctx = RetryContext(
            runner_id="test-123",
            spec_name="my-spec",
            project_path=Path("/test"),
        )

        # Mock subprocess that fails once, then succeeds
        mock_process = Mock()
        command_fn = Mock(return_value=mock_process)
        monitor_fn = Mock(side_effect=[
            (1, "First failure"),  # First attempt fails
            (0, None),             # Second attempt succeeds
        ])

        with patch('time.sleep'):  # Speed up test by skipping sleep
            success, result_ctx = handler.execute_with_retry(ctx, command_fn, monitor_fn)

        assert success is True
        assert result_ctx.attempt_count == 2
        assert command_fn.call_count == 2
        assert monitor_fn.call_count == 2

    def test_execute_with_retry_max_retries_exceeded(self, handler):
        """Test failure after max retries exceeded."""
        ctx = RetryContext(
            runner_id="test-123",
            spec_name="my-spec",
            project_path=Path("/test"),
        )

        # Mock subprocess that always fails
        # With max_retries=3, we get: 1 initial + 2 retries = 3 total attempts
        mock_process = Mock()
        command_fn = Mock(return_value=mock_process)
        monitor_fn = Mock(return_value=(1, "Always fails"))

        with patch('time.sleep'):  # Speed up test
            success, result_ctx = handler.execute_with_retry(ctx, command_fn, monitor_fn)

        assert success is False
        assert result_ctx.attempt_count == 3  # 1 initial + 2 retries (max_retries=3 is the limit)
        assert command_fn.call_count == 3

    def test_execute_with_retry_exception_handling(self, handler):
        """Test exception handling during retry."""
        ctx = RetryContext(
            runner_id="test-123",
            spec_name="my-spec",
            project_path=Path("/test"),
        )

        # Mock subprocess that raises exception
        # With max_retries=3, we get: 1 initial + 2 retries = 3 total attempts
        command_fn = Mock(side_effect=RuntimeError("Process failed"))
        monitor_fn = Mock()

        with patch('time.sleep'):
            success, result_ctx = handler.execute_with_retry(ctx, command_fn, monitor_fn)

        assert success is False
        assert result_ctx.attempt_count == 3  # 1 initial + 2 retries (max_retries=3 is the limit)
        assert command_fn.call_count == 3
        assert monitor_fn.call_count == 0  # Never called due to exception

    def test_log_retry_context(self, handler, temp_log_dir):
        """Test logging retry context to file."""
        ctx = RetryContext(
            runner_id="test-123",
            spec_name="my-spec",
            project_path=Path("/test"),
        )
        ctx.add_attempt(1, "Failed", 10.0)

        handler._log_retry_context(ctx)

        log_file = temp_log_dir / "test-123.json"
        assert log_file.exists()

        import json
        with open(log_file) as f:
            data = json.load(f)

        assert data["runner_id"] == "test-123"
        assert data["spec_name"] == "my-spec"
        assert data["attempt_count"] == 1


class TestCreateRetryHandler:
    """Tests for factory function."""

    def test_create_retry_handler(self, tmp_path):
        """Test factory function creates handler."""
        config = RetryConfig(retry_log_dir=tmp_path / "logs")
        handler = create_retry_handler(config)

        assert isinstance(handler, RetryHandler)
        assert handler.config == config


class TestRetryAttempt:
    """Tests for RetryAttempt dataclass."""

    def test_creation(self):
        """Test creating a retry attempt."""
        attempt = RetryAttempt(
            attempt_number=1,
            timestamp="2026-01-30T10:00:00Z",
            exit_code=1,
            error_message="Failed",
            duration_seconds=10.5,
        )

        assert attempt.attempt_number == 1
        assert attempt.exit_code == 1
        assert attempt.error_message == "Failed"
        assert attempt.duration_seconds == 10.5
