"""Runner manager for subprocess lifecycle management.

This module manages the lifecycle of provider subprocesses including
starting, stopping, monitoring health, and detecting commits.
"""

from __future__ import annotations

import logging
import signal
import subprocess
import time
import uuid
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from ..utils import (
    check_clean_working_tree,
    check_mcp_server_exists,
    get_current_commit,
)
from .state import RunnerState, RunnerStatus, StatePersister

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
        self._restore_runners()

    def _restore_runners(self) -> None:
        """Restore runner states from disk and validate PIDs."""
        restored = self.persister.load()
        for runner in restored:
            self.runners[runner.runner_id] = runner
            logger.info(
                f"Restored runner {runner.runner_id} "
                f"(spec={runner.spec_name}, status={runner.status.value})"
            )

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
        # Check for clean working tree
        check_clean_working_tree(project_path)

        # Check for MCP server (Codex only, but providers can handle this)
        check_mcp_server_exists(provider, project_path)

    def start_runner(
        self,
        project_path: Path,
        spec_name: str,
        provider: Provider,
        model: str,
    ) -> RunnerState:
        """Start a new runner subprocess for the specified spec.

        Args:
            project_path: Path to project directory
            spec_name: Name of spec to run
            provider: Provider instance to use
            model: Model identifier to use

        Returns:
            RunnerState instance for the new runner

        Raises:
            Exception: If preconditions fail or subprocess cannot start
        """
        # Validate preconditions
        self._check_preconditions(project_path, provider)

        # Get baseline commit before starting
        baseline_commit = get_current_commit(project_path)

        # Build command for provider
        prompt = self.config.prompt_template.format(spec_name=spec_name)
        provider_cmd = provider.build_command(
            prompt=prompt,
            project_path=project_path,
            config_overrides=self.config.codex_config_overrides,
        )

        # Prepare log directory
        log_dir = project_path / self.config.spec_workflow_dir_name / self.config.log_dir_name
        log_dir.mkdir(parents=True, exist_ok=True)

        # Generate log file path
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        log_filename = self.config.log_file_template.format(
            spec_name=spec_name,
            timestamp=timestamp,
        )
        log_path = log_dir / log_filename

        # Start subprocess with Popen (non-blocking)
        cmd_list = provider_cmd.to_list()
        logger.info(f"Starting runner: {' '.join(cmd_list)}")

        with log_path.open("w", encoding="utf-8") as log_file:
            process = subprocess.Popen(
                cmd_list,
                cwd=project_path,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                text=True,
            )

        # Create runner state
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
        )

        # Store runner and process
        self.runners[runner_id] = runner
        self.processes[runner_id] = process

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
                f"Process {runner.pid} did not terminate after {timeout}s, "
                f"sending SIGKILL"
            )
            process.kill()
            exit_code = process.wait()
            logger.info(f"Process {runner.pid} killed (exit code {exit_code})")
            status = RunnerStatus.CRASHED

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
        return [
            runner
            for runner in self.runners.values()
            if runner.status == RunnerStatus.RUNNING
        ]

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
            result = subprocess.run(
                ["git", "log", "-1", "--format=%H %s"],
                cwd=runner.project_path,
                capture_output=True,
                text=True,
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
