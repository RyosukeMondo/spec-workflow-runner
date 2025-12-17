"""State management for TUI application.

This module defines all state data models used throughout the TUI,
including project/spec state, runner state, and state persistence.
"""

from __future__ import annotations

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
