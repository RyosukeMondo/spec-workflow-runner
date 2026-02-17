"""Retry handler for robust subprocess execution with crash recovery.

This module provides retry logic with exponential backoff, crash detection,
and comprehensive logging for provider subprocess execution.
"""

from __future__ import annotations

import json
import logging
import subprocess
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RetryConfig:
    """Configuration for retry behavior."""

    max_retries: int = 3
    """Maximum number of retry attempts (default: 3)"""

    retry_backoff_seconds: int = 5
    """Initial backoff delay in seconds (default: 5)"""

    retry_on_crash: bool = True
    """Enable automatic retry on subprocess crash (default: True)"""

    retry_log_dir: Path = field(default_factory=lambda: Path("logs/retries"))
    """Directory for retry logs (default: logs/retries)"""

    activity_timeout_seconds: int = 300
    """Timeout for subprocess inactivity in seconds (default: 300/5min)"""

    backoff_multiplier: float = 2.0
    """Exponential backoff multiplier (default: 2.0)"""

    max_backoff_seconds: int = 300
    """Maximum backoff delay in seconds (default: 300/5min)"""


@dataclass
class RetryAttempt:
    """Record of a single retry attempt."""

    attempt_number: int
    timestamp: str
    exit_code: int | None
    error_message: str | None
    duration_seconds: float


@dataclass
class RetryContext:
    """Context for tracking retry state across attempts."""

    runner_id: str
    spec_name: str
    project_path: Path
    attempts: list[RetryAttempt] = field(default_factory=list)
    start_time: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def attempt_count(self) -> int:
        """Get total number of attempts made."""
        return len(self.attempts)

    @property
    def total_duration_seconds(self) -> float:
        """Get total duration across all attempts."""
        return (datetime.now(UTC) - self.start_time).total_seconds()

    def add_attempt(
        self,
        exit_code: int | None,
        error_message: str | None,
        duration: float,
    ) -> None:
        """Record a retry attempt."""
        attempt = RetryAttempt(
            attempt_number=self.attempt_count + 1,
            timestamp=datetime.now(UTC).isoformat(),
            exit_code=exit_code,
            error_message=error_message,
            duration_seconds=duration,
        )
        self.attempts.append(attempt)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for logging."""
        return {
            "runner_id": self.runner_id,
            "spec_name": self.spec_name,
            "project_path": str(self.project_path),
            "start_time": self.start_time.isoformat(),
            "total_duration_seconds": self.total_duration_seconds,
            "attempt_count": self.attempt_count,
            "attempts": [asdict(a) for a in self.attempts],
        }


class RetryHandler:
    """Handles retry logic with crash detection and exponential backoff."""

    def __init__(self, config: RetryConfig) -> None:
        """Initialize retry handler with configuration.

        Args:
            config: Retry configuration
        """
        self.config = config
        self._ensure_log_dir()

    def _ensure_log_dir(self) -> None:
        """Ensure retry log directory exists."""
        self.config.retry_log_dir.mkdir(parents=True, exist_ok=True)

    def _calculate_backoff(self, attempt: int) -> float:
        """Calculate exponential backoff delay.

        Args:
            attempt: Current attempt number (1-indexed)

        Returns:
            Backoff delay in seconds
        """
        delay = self.config.retry_backoff_seconds * (
            self.config.backoff_multiplier ** (attempt - 1)
        )
        return min(delay, self.config.max_backoff_seconds)

    def _log_retry_context(self, context: RetryContext) -> None:
        """Log retry context to JSON file.

        Args:
            context: Retry context to log
        """
        log_file = self.config.retry_log_dir / f"{context.runner_id}.json"
        try:
            with open(log_file, "w", encoding="utf-8") as f:
                json.dump(context.to_dict(), f, indent=2)
        except Exception as e:
            logger.warning(f"Failed to write retry log: {e}")

    def _should_retry(
        self,
        context: RetryContext,
        exit_code: int | None,
    ) -> bool:
        """Determine if subprocess should be retried.

        Args:
            context: Current retry context
            exit_code: Exit code from subprocess (None if crash/timeout)

        Returns:
            True if should retry, False otherwise
        """
        # Check if retry is enabled
        if not self.config.retry_on_crash:
            return False

        # Check if max retries exceeded
        if context.attempt_count >= self.config.max_retries:
            logger.warning(
                f"Max retries ({self.config.max_retries}) exceeded for runner {context.runner_id}"
            )
            return False

        # Retry on crash (exit_code None or non-zero)
        if exit_code is None or exit_code != 0:
            return True

        # Success - no retry needed
        return False

    def execute_with_retry(
        self,
        context: RetryContext,
        command_fn: Callable[[], subprocess.Popen[str]],
        monitor_fn: Callable[[subprocess.Popen[str]], tuple[int | None, str | None]],
    ) -> tuple[bool, RetryContext]:
        """Execute subprocess with retry logic.

        Args:
            context: Retry context for tracking attempts
            command_fn: Callable that creates and returns subprocess
            monitor_fn: Callable that monitors subprocess and returns (exit_code, error)

        Returns:
            Tuple of (success, updated_context)
        """
        attempt = 0

        while True:
            attempt += 1
            start_time = time.time()

            logger.info(
                f"Attempt {attempt}/{self.config.max_retries + 1} for "
                f"runner {context.runner_id} (spec: {context.spec_name})"
            )

            try:
                # Start subprocess
                process = command_fn()

                # Monitor subprocess
                exit_code, error_message = monitor_fn(process)
                duration = time.time() - start_time

                # Record attempt
                context.add_attempt(exit_code, error_message, duration)

                # Check if successful
                if exit_code == 0:
                    logger.info(
                        f"Runner {context.runner_id} completed successfully "
                        f"(attempt {attempt}, duration: {duration:.1f}s)"
                    )
                    self._log_retry_context(context)
                    return True, context

                # Check if should retry
                if not self._should_retry(context, exit_code):
                    logger.error(f"Runner {context.runner_id} failed after {attempt} attempts")
                    self._log_retry_context(context)
                    return False, context

                # Calculate backoff and retry
                backoff = self._calculate_backoff(attempt)
                logger.warning(
                    f"Runner {context.runner_id} failed (exit_code: {exit_code}), "
                    f"retrying in {backoff:.1f}s... "
                    f"({attempt}/{self.config.max_retries} retries)"
                )
                time.sleep(backoff)

            except Exception as e:
                duration = time.time() - start_time
                error_msg = f"Exception during execution: {e}"
                logger.exception(error_msg)

                # Record attempt
                context.add_attempt(None, error_msg, duration)

                # Check if should retry
                if not self._should_retry(context, None):
                    logger.error(
                        f"Runner {context.runner_id} failed with exception after {attempt} attempts"
                    )
                    self._log_retry_context(context)
                    return False, context

                # Calculate backoff and retry
                backoff = self._calculate_backoff(attempt)
                logger.warning(f"Runner {context.runner_id} crashed, retrying in {backoff:.1f}s...")
                time.sleep(backoff)


def create_retry_handler(config: RetryConfig) -> RetryHandler:
    """Factory function to create a retry handler.

    Args:
        config: Retry configuration

    Returns:
        Configured RetryHandler instance
    """
    return RetryHandler(config)
