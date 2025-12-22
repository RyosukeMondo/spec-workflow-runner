"""State persistence and recovery for TUI application.

This module handles saving and loading runner state to/from disk with validation.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from pathlib import Path

from .models import RunnerState, RunnerStatus

logger = logging.getLogger(__name__)


class StatePersister:
    """Manages persistence and recovery of runner state across TUI restarts."""

    def __init__(self, cache_dir: Path, config_path: Path):
        """Initialize state persister.

        Args:
            cache_dir: Directory to store state files (~/.cache/spec-workflow-runner/)
            config_path: Path to config.json for hash validation
        """
        self.cache_dir = cache_dir
        self.config_path = config_path
        self.state_file = cache_dir / "runner_state.json"

    def _compute_config_hash(self) -> str:
        """Compute SHA256 hash of config.json for invalidation detection."""
        if not self.config_path.exists():
            return ""
        try:
            with self.config_path.open("rb") as f:
                return hashlib.sha256(f.read()).hexdigest()
        except OSError as err:
            logger.warning(f"Failed to read config for hashing: {err}")
            return ""

    def _is_pid_alive(self, pid: int) -> bool:
        """Check if a process with the given PID is still running."""
        try:
            # os.kill with signal 0 checks if process exists without sending signal
            os.kill(pid, 0)
            return True
        except ProcessLookupError:
            # Process doesn't exist
            return False
        except PermissionError:
            # Process exists but we don't have permission (still alive)
            return True
        except OSError as err:
            logger.warning(f"Error checking PID {pid}: {err}")
            return False

    def save(self, runners: list[RunnerState]) -> None:
        """Save runner state to disk.

        Args:
            runners: List of runner states to persist
        """
        # Ensure cache directory exists
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        # Prepare data with config hash
        data = {
            "config_hash": self._compute_config_hash(),
            "runners": [runner.to_dict() for runner in runners],
        }

        # Write to file
        try:
            with self.state_file.open("w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except OSError as err:
            logger.error(f"Failed to save runner state: {err}")

    def load(self) -> list[RunnerState]:
        """Load and validate runner state from disk.

        Returns:
            List of validated runner states (stale entries removed)
        """
        # If state file doesn't exist, return empty list
        if not self.state_file.exists():
            return []

        # Read state file
        try:
            with self.state_file.open("r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError) as err:
            # Corrupted or unreadable file - delete and continue
            logger.warning(f"Corrupted state file, deleting: {err}")
            try:
                self.state_file.unlink()
            except OSError:
                pass
            return []

        # Validate config hash
        stored_hash = data.get("config_hash", "")
        current_hash = self._compute_config_hash()
        if stored_hash and current_hash and stored_hash != current_hash:
            logger.warning("Config has changed since state was saved, invalidating state")
            try:
                self.state_file.unlink()
            except OSError:
                pass
            return []

        # Parse runner states
        runners_data = data.get("runners", [])
        validated_runners: list[RunnerState] = []

        for runner_data in runners_data:
            try:
                runner = RunnerState.from_dict(runner_data)

                # Validate PID is still alive for running runners
                if runner.status == RunnerStatus.RUNNING:
                    if not self._is_pid_alive(runner.pid):
                        logger.warning(
                            f"Runner {runner.runner_id} (PID {runner.pid}) is not alive, "
                            f"marking as crashed"
                        )
                        # Update status to crashed since process died
                        runner = RunnerState(
                            runner_id=runner.runner_id,
                            project_path=runner.project_path,
                            spec_name=runner.spec_name,
                            provider=runner.provider,
                            model=runner.model,
                            pid=runner.pid,
                            status=RunnerStatus.CRASHED,
                            started_at=runner.started_at,
                            baseline_commit=runner.baseline_commit,
                            last_commit_hash=runner.last_commit_hash,
                            last_commit_message=runner.last_commit_message,
                            exit_code=None,
                        )

                validated_runners.append(runner)

            except (KeyError, ValueError, TypeError) as err:
                logger.warning(f"Invalid runner state entry, skipping: {err}")
                continue

        return validated_runners
