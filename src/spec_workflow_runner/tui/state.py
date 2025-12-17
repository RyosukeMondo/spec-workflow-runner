"""State management for TUI application.

This module defines all state data models used throughout the TUI,
including project/spec state, runner state, and state persistence.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any


class RunnerStatus(Enum):
    """Status of a runner process."""

    RUNNING = "running"
    STOPPED = "stopped"
    CRASHED = "crashed"
    COMPLETED = "completed"


@dataclass
class ProjectState:
    """State for a single project."""

    path: Path
    name: str
    specs: list[SpecState] = field(default_factory=list)

    def __repr__(self) -> str:
        return f"ProjectState(name={self.name!r}, specs={len(self.specs)})"


@dataclass
class SpecState:
    """State for a single spec within a project."""

    name: str
    path: Path
    total_tasks: int
    completed_tasks: int
    in_progress_tasks: int
    pending_tasks: int
    runner: RunnerState | None = None

    @property
    def is_complete(self) -> bool:
        """Check if all tasks are completed."""
        return self.total_tasks > 0 and self.completed_tasks == self.total_tasks

    @property
    def has_unfinished_tasks(self) -> bool:
        """Check if spec has unfinished tasks."""
        return self.total_tasks > 0 and self.completed_tasks < self.total_tasks

    def __repr__(self) -> str:
        return (
            f"SpecState(name={self.name!r}, "
            f"tasks={self.completed_tasks}/{self.total_tasks}, "
            f"runner={self.runner.status if self.runner else None})"
        )


@dataclass
class RunnerState:
    """State for a running or stopped spec workflow runner."""

    runner_id: str
    project_path: Path
    spec_name: str
    provider: str
    model: str
    pid: int
    status: RunnerStatus
    started_at: datetime
    baseline_commit: str
    last_commit_hash: str | None = None
    last_commit_message: str | None = None
    exit_code: int | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize runner state to JSON-compatible dict."""
        return {
            "runner_id": self.runner_id,
            "project_path": str(self.project_path),
            "spec_name": self.spec_name,
            "provider": self.provider,
            "model": self.model,
            "pid": self.pid,
            "status": self.status.value,
            "started_at": self.started_at.isoformat(),
            "baseline_commit": self.baseline_commit,
            "last_commit_hash": self.last_commit_hash,
            "last_commit_message": self.last_commit_message,
            "exit_code": self.exit_code,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RunnerState:
        """Deserialize runner state from JSON-compatible dict."""
        return cls(
            runner_id=str(data["runner_id"]),
            project_path=Path(data["project_path"]),
            spec_name=str(data["spec_name"]),
            provider=str(data["provider"]),
            model=str(data["model"]),
            pid=int(data["pid"]),
            status=RunnerStatus(data["status"]),
            started_at=datetime.fromisoformat(data["started_at"]),
            baseline_commit=str(data["baseline_commit"]),
            last_commit_hash=data.get("last_commit_hash"),
            last_commit_message=data.get("last_commit_message"),
            exit_code=data.get("exit_code"),
        )

    def __repr__(self) -> str:
        return (
            f"RunnerState(id={self.runner_id}, spec={self.spec_name}, "
            f"status={self.status.value}, pid={self.pid})"
        )


@dataclass
class AppState:
    """Global application state."""

    projects: list[ProjectState] = field(default_factory=list)
    selected_project_index: int | None = None
    selected_spec_index: int | None = None
    filter_text: str = ""
    filter_mode: bool = False
    show_unfinished_only: bool = False
    log_panel_visible: bool = True
    log_auto_scroll: bool = True
    current_error: str | None = None
    active_runners: dict[str, RunnerState] = field(default_factory=dict)

    @property
    def selected_project(self) -> ProjectState | None:
        """Get currently selected project."""
        if (
            self.selected_project_index is not None
            and 0 <= self.selected_project_index < len(self.projects)
        ):
            return self.projects[self.selected_project_index]
        return None

    @property
    def selected_spec(self) -> SpecState | None:
        """Get currently selected spec."""
        project = self.selected_project
        if project is None or self.selected_spec_index is None:
            return None
        if 0 <= self.selected_spec_index < len(project.specs):
            return project.specs[self.selected_spec_index]
        return None

    def __repr__(self) -> str:
        return (
            f"AppState(projects={len(self.projects)}, "
            f"active_runners={len(self.active_runners)})"
        )


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
