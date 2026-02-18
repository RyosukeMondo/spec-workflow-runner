"""Runner manager for subprocess lifecycle management.

This module manages the lifecycle of provider subprocesses including
starting, stopping, monitoring health, and detecting commits.
"""

from __future__ import annotations

import logging
import os
import signal
import subprocess
import time
import uuid
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ..completion_checker import CompletionResult, smart_completion_check
from ..subprocess_helpers import popen_command, run_command
from ..utils import (
    check_clean_working_tree,
    check_mcp_server_exists,
    get_current_commit,
)
from .models import RunnerState, RunnerStatus
from .persistence import StatePersister

if TYPE_CHECKING:
    from ..providers import Provider
    from ..utils import Config

logger = logging.getLogger(__name__)


class RunnerManager:
    """Manages the lifecycle of provider subprocesses."""

    def __init__(self, config: Config, config_path: Path) -> None:
        """Initialize runner manager with configuration.

        Args:
            config: Runtime configuration
            config_path: Path to config.json for state persistence
        """
        self.config = config
        self.persister = StatePersister(
            cache_dir=config.cache_dir,
            config_path=config_path,
        )
        self.runners: dict[str, RunnerState] = {}
        self.processes: dict[str, subprocess.Popen[str]] = {}
        self.log_files: dict[str, Any] = {}  # Keep log files open
        self._restore_runners()

    def _restore_runners(self) -> None:
        """Restore runner states from disk and validate PIDs."""

        restored = self.persister.load()
        for runner in restored:
            # Validate PID if runner is marked as RUNNING
            if runner.status == RunnerStatus.RUNNING:
                # Check if process with this PID still exists
                try:
                    os.kill(runner.pid, 0)  # Signal 0 just checks existence
                    logger.info(
                        f"Restored running runner {runner.runner_id} "
                        f"(spec={runner.spec_name}, PID={runner.pid})"
                    )
                    self.runners[runner.runner_id] = runner
                except (OSError, ProcessLookupError):
                    # Process doesn't exist anymore - mark as crashed
                    logger.warning(
                        f"Runner {runner.runner_id} PID {runner.pid} no longer exists, "
                        f"marking as crashed"
                    )
                    crashed_runner = replace(
                        runner,
                        status=RunnerStatus.CRASHED,
                        exit_code=-1,
                    )
                    self.runners[runner.runner_id] = crashed_runner
            else:
                # Runner is stopped/crashed, just restore as-is
                self.runners[runner.runner_id] = runner
                logger.info(
                    f"Restored {runner.status.value} runner {runner.runner_id} "
                    f"(spec={runner.spec_name})"
                )

        # Persist any status changes (crashed runners)
        self._persist_state()

    def _persist_state(self) -> None:
        """Persist current runner states to disk."""
        runner_list = list(self.runners.values())
        self.persister.save(runner_list)

    def _check_preconditions(self, project_path: Path, provider: Provider) -> None:
        """Validate preconditions before starting a runner.

        Args:
            project_path: Path to project directory
            provider: Provider instance to use

        Raises:
            Exception: If preconditions are not met
        """
        # Check for clean working tree (warns only)
        check_clean_working_tree(project_path)

        # Check for MCP server and auto-install if not found
        check_mcp_server_exists(provider, project_path, self.config)

    def start_runner(
        self,
        project_path: Path,
        spec_name: str,
        provider: Provider,
        model: str,
        total_tasks: int = 0,
        completed_tasks: int = 0,
        in_progress_tasks: int = 0,
    ) -> RunnerState:
        """Start a new runner subprocess for the specified spec.

        Args:
            project_path: Path to project directory
            spec_name: Name of spec to run
            provider: Provider instance to use
            model: Model identifier to use
            total_tasks: Total number of tasks in spec
            completed_tasks: Number of completed tasks
            in_progress_tasks: Number of in-progress tasks

        Returns:
            RunnerState instance for the new runner

        Raises:
            Exception: If preconditions fail or subprocess cannot start
        """
        # Validate preconditions
        self._check_preconditions(project_path, provider)

        # Get baseline commit before starting
        baseline_commit = get_current_commit(project_path)

        # Build prompt context with task statistics
        from datetime import UTC, datetime

        remaining_tasks = total_tasks - completed_tasks
        context = {
            "spec_name": spec_name,
            "tasks_total": total_tasks,
            "tasks_done": completed_tasks,
            "tasks_remaining": remaining_tasks,
            "tasks_in_progress": in_progress_tasks,
            "timestamp": datetime.now(UTC).isoformat(),
        }

        # Build command for provider
        prompt = self.config.prompt_template.format(**context)
        provider_cmd = provider.build_command(
            prompt=prompt,
            project_path=project_path,
            config_overrides=self.config.codex_config_overrides,
        )

        # Prepare log directory
        log_dir = project_path / self.config.spec_workflow_dir_name / self.config.log_dir_name
        log_dir.mkdir(parents=True, exist_ok=True)

        # Generate log file path
        # Support both {index} (for run_tasks.py) and {spec_name}/{timestamp} (for TUI)
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        log_filename = self.config.log_file_template.format(
            index=1,  # TUI doesn't run iterations
            spec_name=spec_name,
            timestamp=timestamp,
        )
        log_path = log_dir / log_filename

        # Start subprocess with Popen (non-blocking)
        cmd_list = provider_cmd.to_list()
        logger.info(f"Starting runner: {' '.join(cmd_list)}")

        # Open log file and keep it open for the duration of the process
        log_file = log_path.open("w", encoding="utf-8", buffering=1)  # Line buffered

        process = popen_command(
            cmd_list,
            cwd=project_path,
            stdout=log_file,
            clean_claude_env=True,
            text_mode=True,
        )

        # Create runner state with retry settings
        runner_id = str(uuid.uuid4())
        runner = RunnerState(
            runner_id=runner_id,
            project_path=project_path,
            spec_name=spec_name,
            provider=provider.get_provider_name(),
            model=model,
            pid=process.pid,
            status=RunnerStatus.RUNNING,
            started_at=datetime.now(),
            baseline_commit=baseline_commit,
            retry_count=0,
            max_retries=(
                self.config.retry_config.max_retries
                if self.config.retry_config.retry_on_crash
                else 0
            ),
        )

        # Store runner, process, and log file
        self.runners[runner_id] = runner
        self.processes[runner_id] = process
        self.log_files[runner_id] = log_file

        # Persist state
        self._persist_state()

        logger.info(
            f"Started runner {runner_id} "
            f"(spec={spec_name}, provider={provider.get_provider_name()}, "
            f"model={model}, pid={process.pid})"
        )

        return runner

    def stop_runner(self, runner_id: str, timeout: int = 5) -> None:
        """Stop a running subprocess with signal escalation.

        Sends SIGTERM first, waits for timeout seconds, then sends SIGKILL if needed.

        Args:
            runner_id: ID of runner to stop
            timeout: Seconds to wait before SIGKILL (default: 5)

        Raises:
            KeyError: If runner_id is not found
        """
        runner = self.runners.get(runner_id)
        if not runner:
            raise KeyError(f"Runner {runner_id} not found")

        process = self.processes.get(runner_id)
        if not process:
            # Process already gone, just update state
            logger.warning(f"No process found for runner {runner_id}, marking as stopped")

            # Close log file if it exists
            log_file = self.log_files.get(runner_id)
            if log_file:
                try:
                    log_file.close()
                except Exception as e:
                    logger.warning(f"Error closing log file: {e}")
                del self.log_files[runner_id]

            updated_runner = replace(
                runner,
                status=RunnerStatus.STOPPED,
                exit_code=0,
            )
            self.runners[runner_id] = updated_runner
            self._persist_state()
            return

        logger.info(f"Stopping runner {runner_id} (PID {runner.pid})")

        # Send SIGTERM
        try:
            process.send_signal(signal.SIGTERM)
            logger.info(f"Sent SIGTERM to PID {runner.pid}")
        except ProcessLookupError:
            # Process already exited
            logger.info(f"Process {runner.pid} already exited")
            exit_code = process.poll() or 0

            # Close log file
            log_file = self.log_files.get(runner_id)
            if log_file:
                try:
                    log_file.close()
                except Exception as e:
                    logger.warning(f"Error closing log file: {e}")
                del self.log_files[runner_id]

            updated_runner = replace(
                runner,
                status=RunnerStatus.STOPPED,
                exit_code=exit_code,
            )
            self.runners[runner_id] = updated_runner
            del self.processes[runner_id]
            self._persist_state()
            return

        # Wait for process to terminate
        try:
            exit_code = process.wait(timeout=timeout)
            logger.info(f"Process {runner.pid} terminated with exit code {exit_code}")
            status = RunnerStatus.STOPPED if exit_code == 0 else RunnerStatus.CRASHED
        except subprocess.TimeoutExpired:
            # Process didn't terminate, escalate to SIGKILL
            logger.warning(
                f"Process {runner.pid} did not terminate after {timeout}s, sending SIGKILL"
            )
            process.kill()
            exit_code = process.wait()
            logger.info(f"Process {runner.pid} killed (exit code {exit_code})")
            status = RunnerStatus.CRASHED

        # Close log file if it exists
        log_file = self.log_files.get(runner_id)
        if log_file:
            try:
                log_file.close()
                logger.info(f"Closed log file for runner {runner_id}")
            except Exception as e:
                logger.warning(f"Error closing log file for runner {runner_id}: {e}")
            del self.log_files[runner_id]

        # Update runner state
        updated_runner = replace(
            runner,
            status=status,
            exit_code=exit_code,
        )
        self.runners[runner_id] = updated_runner
        del self.processes[runner_id]

        # Persist state
        self._persist_state()

    def get_active_runners(self) -> list[RunnerState]:
        """Get list of all currently running runners.

        Returns:
            List of RunnerState instances with status RUNNING
        """
        return [runner for runner in self.runners.values() if runner.status == RunnerStatus.RUNNING]

    def check_runner_health(self, runner_id: str) -> RunnerStatus:
        """Check if a runner process is still running.

        Updates runner state if process has exited.

        Args:
            runner_id: ID of runner to check

        Returns:
            Current RunnerStatus

        Raises:
            KeyError: If runner_id is not found
        """
        runner = self.runners.get(runner_id)
        if not runner:
            raise KeyError(f"Runner {runner_id} not found")

        # If runner is not marked as running, return current status
        if runner.status != RunnerStatus.RUNNING:
            return runner.status

        # Check if process is still alive
        process = self.processes.get(runner_id)
        if not process:
            # No process handle, assume crashed
            logger.warning(f"No process handle for running runner {runner_id}")
            updated_runner = replace(runner, status=RunnerStatus.CRASHED)
            self.runners[runner_id] = updated_runner
            self._persist_state()
            return RunnerStatus.CRASHED

        # Poll process status
        exit_code = process.poll()
        if exit_code is None:
            # Still running
            return RunnerStatus.RUNNING

        # Process has exited
        logger.info(f"Runner {runner_id} exited with code {exit_code}")

        if exit_code == 0:
            status = RunnerStatus.COMPLETED
        else:
            status = RunnerStatus.CRASHED

        updated_runner = replace(
            runner,
            status=status,
            exit_code=exit_code,
        )
        self.runners[runner_id] = updated_runner
        del self.processes[runner_id]

        # Persist state
        self._persist_state()

        return status

    def detect_new_commits(self, runner_id: str) -> tuple[str | None, str | None]:
        """Detect new commits made since runner started.

        Args:
            runner_id: ID of runner to check

        Returns:
            Tuple of (commit_hash, commit_message) or (None, None) if no new commits

        Raises:
            KeyError: If runner_id is not found
        """
        runner = self.runners.get(runner_id)
        if not runner:
            raise KeyError(f"Runner {runner_id} not found")

        try:
            # Get current commit
            current_commit = get_current_commit(runner.project_path)

            # If same as baseline, no new commits
            if current_commit == runner.baseline_commit:
                return None, None

            # Get commit message for the latest commit
            result = run_command(
                ["git", "log", "-1", "--format=%H %s"],
                cwd=runner.project_path,
                check=True,
            )

            output = result.stdout.strip()
            if not output:
                return None, None

            # Parse output: "hash message"
            parts = output.split(" ", 1)
            commit_hash = parts[0]
            commit_message = parts[1] if len(parts) > 1 else ""

            return commit_hash, commit_message

        except subprocess.CalledProcessError as err:
            logger.error(f"Failed to detect commits for runner {runner_id}: {err}")
            return None, None

    def check_completion_smart(
        self,
        runner_id: str,
        max_probes: int | None = None,
        probe_interval: int | None = None,
    ) -> CompletionResult:
        """Smart completion check: git commits + probing + rescue.

        This method uses multiple signals to robustly detect completion:
        1. Primary: Check for new git commits
        2. Fallback: Probe session with --continue when no commits
        3. Rescue: Salvage uncommitted work before declaring incomplete

        Args:
            runner_id: ID of runner to check
            max_probes: Maximum probe attempts (default: from config)
            probe_interval: Seconds between probes (default: from config)

        Returns:
            CompletionResult with status

        Raises:
            KeyError: If runner_id is not found
        """
        runner = self.runners.get(runner_id)
        if not runner:
            raise KeyError(f"Runner {runner_id} not found")

        # Use config defaults if not specified
        if max_probes is None:
            max_probes = self.config.completion_check_max_probes
        if probe_interval is None:
            probe_interval = self.config.completion_check_probe_interval

        logger.info(
            f"Starting smart completion check for runner {runner_id} "
            f"(spec={runner.spec_name}, max_probes={max_probes}, "
            f"probe_interval={probe_interval}s)"
        )

        result = smart_completion_check(
            project_path=runner.project_path,
            spec_name=runner.spec_name,
            baseline_commit=runner.baseline_commit,
            max_probes=max_probes,
            probe_interval=probe_interval,
        )

        logger.info(
            f"Smart completion check result: complete={result.complete}, "
            f"status={result.status}, new_commits={result.new_commits}, "
            f"probes={result.probes_used}, rescued={result.rescued}"
        )

        return result

    def maybe_retry_runner(
        self,
        runner_id: str,
        provider: Provider,
        model: str,
    ) -> bool:
        """Attempt to retry a crashed runner if retry is enabled and not exceeded.

        Args:
            runner_id: ID of runner to retry
            provider: Provider instance to use for retry
            model: Model identifier to use

        Returns:
            True if retry was attempted, False otherwise
        """
        runner = self.runners.get(runner_id)
        if not runner:
            logger.warning(f"Cannot retry runner {runner_id}: not found")
            return False

        # Only retry crashed runners
        if runner.status != RunnerStatus.CRASHED:
            logger.debug(f"Runner {runner_id} not in CRASHED state, skipping retry")
            return False

        # Check if retry is enabled
        if not self.config.retry_config.retry_on_crash:
            logger.debug("Retry disabled in config, skipping retry")
            return False

        # Check if max retries exceeded
        if runner.retry_count >= runner.max_retries:
            logger.info(
                f"Max retries ({runner.max_retries}) reached for runner {runner_id}, not retrying"
            )
            return False

        # Calculate backoff delay
        backoff_seconds = self.config.retry_config.retry_backoff_seconds * (
            self.config.retry_config.backoff_multiplier**runner.retry_count
        )
        backoff_seconds = min(
            backoff_seconds,
            self.config.retry_config.max_backoff_seconds,
        )

        logger.info(
            f"Retrying runner {runner_id} (attempt {runner.retry_count + 1}/{runner.max_retries}) "
            f"after {backoff_seconds:.1f}s backoff..."
        )

        # Apply backoff delay
        time.sleep(backoff_seconds)

        # Close old log file if still open
        old_log_file = self.log_files.get(runner_id)
        if old_log_file:
            try:
                old_log_file.close()
            except Exception as e:
                logger.warning(f"Error closing old log file: {e}")
            del self.log_files[runner_id]

        # Remove old process handle
        if runner_id in self.processes:
            del self.processes[runner_id]

        # Start new subprocess with same parameters
        try:
            # Get current task stats for prompt context
            from ..utils import read_task_stats

            stats = read_task_stats(runner.project_path, runner.spec_name, self.config)

            # Build prompt
            context = {
                "spec_name": runner.spec_name,
                "tasks_total": stats.total,
                "tasks_done": stats.done,
                "tasks_remaining": stats.total - stats.done,
                "tasks_in_progress": stats.in_progress,
                "timestamp": datetime.now().isoformat(),
            }

            prompt = self.config.prompt_template.format(**context)
            provider_cmd = provider.build_command(
                prompt=prompt,
                project_path=runner.project_path,
                config_overrides=self.config.codex_config_overrides,
            )

            # Prepare log file for retry
            log_dir = (
                runner.project_path / self.config.spec_workflow_dir_name / self.config.log_dir_name
            )
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            log_filename = self.config.log_file_template.format(
                index=runner.retry_count + 2,  # retry number (1-indexed + 1 for base)
                spec_name=runner.spec_name,
                timestamp=timestamp,
            )
            log_path = log_dir / log_filename

            # Start new process
            log_file = log_path.open("w", encoding="utf-8", buffering=1)
            process = popen_command(
                provider_cmd.to_list(),
                cwd=runner.project_path,
                stdout=log_file,
                clean_claude_env=True,
                text_mode=True,
            )

            # Update runner state
            updated_runner = replace(
                runner,
                pid=process.pid,
                status=RunnerStatus.RUNNING,
                retry_count=runner.retry_count + 1,
                last_retry_at=datetime.now(),
                exit_code=None,
            )

            self.runners[runner_id] = updated_runner
            self.processes[runner_id] = process
            self.log_files[runner_id] = log_file

            # Persist state
            self._persist_state()

            logger.info(
                f"Successfully restarted runner {runner_id} "
                f"(PID: {process.pid}, retry: {updated_runner.retry_count}/{runner.max_retries})"
            )

            return True

        except Exception as e:
            logger.error(f"Failed to retry runner {runner_id}: {e}")
            import traceback

            traceback.print_exc()
            return False

    def shutdown(self, stop_all: bool = True, timeout: int = 10) -> None:
        """Shutdown all runners gracefully.

        Args:
            stop_all: If True, stop all running processes. If False, leave them running.
            timeout: Seconds to wait for each process to terminate
        """
        if stop_all:
            active = self.get_active_runners()
            logger.info(f"Shutting down {len(active)} active runner(s)")
            for runner in active:
                try:
                    self.stop_runner(runner.runner_id, timeout=timeout)
                except Exception as err:
                    logger.error(f"Error stopping runner {runner.runner_id}: {err}")
        else:
            logger.info("Detaching from active runners without stopping")

        # Final state persist
        self._persist_state()
