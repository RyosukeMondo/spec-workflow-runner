"""State management for TUI application.

This module provides a unified interface to state models, persistence, and polling.
The implementation has been split into smaller modules for better maintainability:
- models.py: State data models
- persistence.py: State persistence to disk
- poller.py: Background file system polling
"""

from __future__ import annotations

# Re-export all public APIs for backward compatibility
from .models import (
    AppState,
    ProjectState,
    RunnerState,
    RunnerStatus,
    SpecState,
    StateUpdate,
)
from .persistence import StatePersister
from .poller import StatePoller

__all__ = [
    "AppState",
    "ProjectState",
    "RunnerState",
    "RunnerStatus",
    "SpecState",
    "StateUpdate",
    "StatePersister",
    "StatePoller",
]
