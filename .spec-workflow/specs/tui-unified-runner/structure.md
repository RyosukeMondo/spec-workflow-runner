# Project Structure

## Directory Organization

```
spec-workflow-runner/
├── src/
│   └── spec_workflow_runner/
│       ├── __init__.py
│       ├── run_tasks.py              # Existing: CLI runner (preserve for automation)
│       ├── monitor.py                # Existing: Standalone monitor (keep for compatibility)
│       ├── pipx_installer.py         # Existing: pipx bootstrap
│       ├── providers.py              # Existing: Provider interface and implementations
│       ├── utils.py                  # Existing: Shared helpers (discover, config, tasks)
│       │
│       ├── tui/                      # NEW: TUI application module
│       │   ├── __init__.py
│       │   ├── app.py                # Main TUI application and event loop
│       │   ├── state.py              # State models and file system polling
│       │   ├── runner_manager.py    # Provider subprocess lifecycle management
│       │   ├── keybindings.py       # Keyboard event handlers
│       │   ├── tui_utils.py         # TUI-specific helpers (format_duration, etc.)
│       │   │
│       │   └── views/               # Rich UI components
│       │       ├── __init__.py
│       │       ├── tree_view.py     # Project/spec tree renderer
│       │       ├── status_panel.py  # Spec status panel renderer
│       │       ├── log_viewer.py    # Log tail viewer
│       │       ├── help_panel.py    # Keybinding help overlay
│       │       └── footer_bar.py    # Status bar renderer
│       │
├── tests/
│   ├── test_providers.py            # Existing: Provider tests
│   ├── test_utils.py                # Existing: Utils tests
│   │
│   └── tui/                         # NEW: TUI tests
│       ├── test_state.py            # State models and polling tests
│       ├── test_runner_manager.py   # Subprocess management tests
│       ├── test_keybindings.py      # Keyboard handler tests
│       ├── test_tree_view.py        # Tree rendering tests
│       ├── test_status_panel.py     # Status panel rendering tests
│       ├── test_log_viewer.py       # Log viewer tests
│       └── fixtures/                # Test fixtures
│           ├── sample_tasks.md      # Example tasks files
│           ├── sample_logs.txt      # Example log outputs
│           └── sample_config.json   # Example configurations
│
├── .spec-workflow/                  # Existing: Spec workflow metadata
│   ├── templates/                   # Steering document templates
│   └── specs/                       # Specifications (including this one)
│       └── tui-unified-runner/      # This spec
│
├── pyproject.toml                   # Project config: add tui CLI entry point
├── config.json                      # User config: add TUI settings
└── README.md                        # Update with TUI documentation
```

## Naming Conventions

### Files
- **Modules**: `snake_case` (e.g., `runner_manager.py`, `status_panel.py`)
- **View Components**: `{component}_view.py` or `{component}_panel.py` pattern
- **Tests**: `test_{module}.py` (e.g., `test_state.py`)
- **CLI Entry Points**: Named in `pyproject.toml` scripts section

### Code
- **Classes**: `PascalCase` (e.g., `RunnerManager`, `StatePoller`, `LogViewer`)
- **Functions**: `snake_case` (e.g., `render_tree`, `start_runner`, `poll_log`)
- **Constants**: `UPPER_SNAKE_CASE` (e.g., `DEFAULT_REFRESH_SECONDS`, `MIN_TERMINAL_SIZE`)
- **Private Members**: Leading underscore (e.g., `_poll_cycle`, `_latest_path`)
- **Type Aliases**: `PascalCase` (e.g., `ProjectList`, `SpecMap`)

### Variables
- **Local Variables**: `snake_case` (e.g., `project_path`, `task_stats`)
- **Instance Variables**: `snake_case` (e.g., `self.selected_spec`, `self.log_buffer`)
- **Type Annotations**: Use `from __future__ import annotations` for forward references

## Import Patterns

### Import Order (enforced by Ruff)
1. **Standard Library**: Built-in modules
2. **Third-Party**: Rich, external dependencies
3. **Local Application**: spec_workflow_runner modules
4. **Relative Imports**: Within tui package

Example:
```python
from __future__ import annotations

import json
import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path
from queue import Queue
from typing import TYPE_CHECKING

from rich.console import Console
from rich.layout import Layout
from rich.live import Live

from spec_workflow_runner.providers import Provider
from spec_workflow_runner.utils import Config, TaskStats, discover_projects

from .state import AppState, ProjectState, SpecState
from .views.tree_view import render_tree

if TYPE_CHECKING:
    from collections.abc import Callable
```

### Module Organization
- **Absolute Imports**: Use `spec_workflow_runner.{module}` for cross-package imports
- **Relative Imports**: Use `.{module}` within `tui/` package only
- **Avoid Star Imports**: Never use `from module import *`
- **TYPE_CHECKING**: Import types under `if TYPE_CHECKING:` to avoid circular imports

## Code Structure Patterns

### Module Organization (within files)
```python
"""Module docstring describing purpose and main components."""

from __future__ import annotations

# 1. Standard library imports
import os
from pathlib import Path

# 2. Third-party imports
from rich.panel import Panel

# 3. Local imports
from spec_workflow_runner.utils import Config

# 4. Type checking imports
if TYPE_CHECKING:
    from typing import Any

# 5. Constants and configuration
DEFAULT_TIMEOUT = 5
MAX_LOG_LINES = 200

# 6. Type definitions (dataclasses, enums, protocols)
@dataclass
class State:
    pass

# 7. Main implementation (classes, functions)
class Manager:
    def __init__(self, config: Config) -> None:
        pass

def helper_function(arg: str) -> str:
    pass

# 8. Private helpers (prefixed with _)
def _internal_helper() -> None:
    pass

# 9. Entry point (if applicable)
def main() -> int:
    pass

if __name__ == "__main__":
    raise SystemExit(main())
```

### Function Organization
```python
def function_name(arg1: Type1, arg2: Type2) -> ReturnType:
    """Docstring with description, args, returns, raises.

    Args:
        arg1: Description of arg1.
        arg2: Description of arg2.

    Returns:
        Description of return value.

    Raises:
        ErrorType: When error condition occurs.
    """
    # 1. Input validation (fail-fast)
    if not arg1:
        raise ValueError("arg1 cannot be empty")

    # 2. Setup/initialization
    result = []

    # 3. Core logic
    for item in arg2:
        processed = process(item)
        result.append(processed)

    # 4. Cleanup (if needed)
    # ...

    # 5. Return
    return result
```

### Class Organization
```python
class ComponentName:
    """Docstring describing class purpose and responsibilities."""

    # 1. Class constants
    DEFAULT_VALUE = 10

    # 2. Constructor
    def __init__(self, config: Config) -> None:
        """Initialize with config."""
        self._config = config
        self._state: dict[str, Any] = {}

    # 3. Public methods (alphabetical or logical grouping)
    def public_method(self, arg: str) -> None:
        """Public method docstring."""
        pass

    # 4. Properties
    @property
    def property_name(self) -> str:
        """Property docstring."""
        return self._state.get("key", "")

    # 5. Private methods (prefixed with _)
    def _private_helper(self) -> None:
        """Private helper docstring."""
        pass

    # 6. Special methods (__repr__, __str__, etc.)
    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(...)"
```

## Code Organization Principles

1. **Single Responsibility**: Each module has one clear purpose
   - `state.py`: State models and file system reading only
   - `runner_manager.py`: Subprocess lifecycle only
   - `tree_view.py`: Tree rendering only

2. **Modularity**: Components are independently testable
   - View functions accept state models, not file paths
   - State readers don't depend on UI components
   - Runner manager doesn't import views

3. **Testability**: Structure for easy mocking
   - Dependency injection (pass `Config`, `Provider` instances)
   - Protocols for interfaces (e.g., `StateReader` protocol)
   - Avoid global state (except config)

4. **Consistency**: Follow existing codebase patterns
   - Reuse `utils.py` patterns for config/state loading
   - Match `monitor.py` style for Rich components
   - Use same error handling (raise custom exceptions, not print+exit)

## Module Boundaries

### Separation of Concerns
```
tui/
├── app.py              # TUI entry point, coordinates all components
│   ├─ Imports: state, runner_manager, keybindings, views
│   └─ Responsibility: Main loop, layout orchestration, event routing
│
├── state.py            # State models and file system readers (SSOT)
│   ├─ Imports: utils (discover, read_task_stats), providers
│   └─ Responsibility: Read-only file system access, state modeling
│   └─ Does NOT import: views, app, keybindings
│
├── runner_manager.py   # Subprocess lifecycle (start/stop/monitor)
│   ├─ Imports: providers, state, utils
│   └─ Responsibility: Process management, state persistence
│   └─ Does NOT import: views, app
│
├── keybindings.py      # Keyboard event handlers
│   ├─ Imports: state, runner_manager
│   └─ Responsibility: Map key presses to actions
│   └─ Does NOT import: views (receives view state, not views)
│
├── views/              # Rich component renderers
│   ├─ Imports: state models, rich components
│   └─ Responsibility: Render state as Rich UI elements
│   └─ Does NOT import: runner_manager, keybindings (pure view)
│
└── tui_utils.py        # TUI-specific helpers
    ├─ Imports: Standard library only
    └─ Responsibility: Formatting, parsing, small utilities
    └─ Does NOT import: Any tui modules (to avoid cycles)
```

### Dependency Direction
```
app.py
  ↓
  ├─→ state.py ←─ runner_manager.py ←─ keybindings.py
  ├─→ views/ (only depend on state models)
  └─→ tui_utils.py (no dependencies within tui/)

utils.py, providers.py (existing, reused by all)
```

**Rules**:
- `views/` depends only on state models (data classes), not on managers or app
- `state.py` is a leaf (depends only on `utils`, `providers`, stdlib)
- `keybindings.py` and `runner_manager.py` can depend on `state.py` but not on each other
- `app.py` is the root (orchestrates everything, no other module imports it)

## Code Size Guidelines

Following CLAUDE.md standards:
- **File size**: Maximum 500 lines (excluding comments/blank lines)
  - If module exceeds 500 lines, split into submodules
  - Example: Split `state.py` into `state/models.py` and `state/poller.py`
- **Function size**: Maximum 50 lines (excluding docstrings)
  - Extract complex logic into private helpers
  - Use early returns to reduce nesting
- **Class complexity**: Maximum 10 public methods per class
  - If class grows too large, split responsibilities
  - Example: Split `RunnerManager` into `RunnerStarter`, `RunnerStopper`, `RunnerMonitor`
- **Nesting depth**: Maximum 3 levels
  - Use guard clauses (early returns) to flatten nesting
  - Extract nested loops into separate functions

## TUI-Specific Structure

### Entry Point
- **CLI Command**: `spec-workflow-tui` (defined in `pyproject.toml`)
- **Entry Module**: `src/spec_workflow_runner/tui/app.py`
- **Entry Function**: `main() -> int`

```python
# pyproject.toml addition
[project.scripts]
spec-workflow-run = "spec_workflow_runner.run_tasks:main"
spec-workflow-monitor = "spec_workflow_runner.monitor:main"
spec-workflow-pipx = "spec_workflow_runner.pipx_installer:main"
spec-workflow-tui = "spec_workflow_runner.tui.app:main"  # NEW
```

### State Management
- **SSOT**: File system (tasks.md, logs, runner_state.json)
- **In-Memory Cache**: `AppState` in `app.py` (UI navigation state only)
- **Persistence**: `runner_state.json` in `~/.cache/spec-workflow-runner/`
- **Cache Invalidation**: mtime checks in `StatePoller`

### View Component Pattern
```python
# views/tree_view.py
from rich.tree import Tree
from ..state import ProjectState

def render_tree(
    projects: list[ProjectState],
    selected: tuple[str, str | None],
    filter_text: str = "",
) -> Tree:
    """Render project/spec tree with status badges.

    Args:
        projects: List of project states to render.
        selected: Tuple of (project_name, spec_name or None) for highlighting.
        filter_text: Filter string to match against names.

    Returns:
        Rich Tree component ready for display.
    """
    tree = Tree("Projects")
    for project in projects:
        if filter_text and filter_text.lower() not in project.name.lower():
            continue
        # Rendering logic...
    return tree
```

### Configuration Extension
Add TUI settings to `config.json`:
```json
{
  "repos_root": "~/repos",
  "spec_workflow_dir_name": ".spec-workflow",
  "...": "...",

  // NEW: TUI-specific settings
  "tui_refresh_seconds": 2,
  "tui_log_tail_lines": 200,
  "tui_min_terminal_cols": 80,
  "tui_min_terminal_rows": 24,
  "tui_theme": "default"  // Future: "dark", "light", "monokai"
}
```

## Documentation Standards

### Module Docstrings
Every module must have a docstring:
```python
"""Short one-line summary.

Longer description of module purpose, key components, and usage patterns.
Mention main classes/functions and their responsibilities.

Example:
    Basic usage example showing typical interaction.
"""
```

### Function Docstrings
Use Google-style docstrings:
```python
def function(arg1: str, arg2: int = 10) -> bool:
    """Short summary of function purpose.

    Longer description if needed, explaining behavior, edge cases, etc.

    Args:
        arg1: Description of arg1.
        arg2: Description of arg2. Defaults to 10.

    Returns:
        Description of return value.

    Raises:
        ValueError: When arg1 is empty.
        RuntimeError: When operation fails.

    Example:
        >>> function("test", 5)
        True
    """
```

### Class Docstrings
Document class purpose and attributes:
```python
class ClassName:
    """Short summary of class purpose.

    Longer description of responsibilities and usage patterns.

    Attributes:
        attr1: Description of public attribute.
        attr2: Description of public attribute.

    Example:
        >>> obj = ClassName(config)
        >>> obj.method()
    """
```

### Inline Comments
- Use sparingly for complex logic only (code should be self-explanatory)
- Explain *why*, not *what* (code shows what)
- Keep comments up-to-date with code changes

### Type Annotations
- All public functions/methods must have type annotations
- Use `from __future__ import annotations` for forward references
- Use `typing.Protocol` for interfaces (duck typing)
- Use `dataclasses` for simple data containers (auto-generates `__init__`, `__repr__`)

## Testing Structure

### Test Organization
```python
# tests/tui/test_state.py
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from spec_workflow_runner.tui.state import ProjectState, StatePoller
from spec_workflow_runner.utils import TaskStats

class TestProjectState:
    """Test suite for ProjectState data class."""

    def test_initialization(self) -> None:
        """Test ProjectState can be initialized with valid data."""
        # Test implementation

    def test_serialization(self) -> None:
        """Test ProjectState can be serialized to/from JSON."""
        # Test implementation


class TestStatePoller:
    """Test suite for StatePoller background polling."""

    @pytest.fixture
    def mock_config(self) -> Mock:
        """Fixture providing mocked Config."""
        return Mock(tui_refresh_seconds=1, repos_root=Path("/tmp"))

    def test_poll_cycle_detects_changes(self, mock_config: Mock) -> None:
        """Test poll cycle detects file mtime changes."""
        # Test implementation with mocked file system
```

### Test Coverage
- All public functions/methods must have tests
- Critical paths (state management, subprocess control) require 90% coverage
- View renderers require snapshot tests (compare rendered output)
- Integration tests for end-to-end workflows

### Fixtures
- Shared fixtures in `tests/tui/fixtures/` directory
- Sample data files (tasks.md, logs, configs) for testing
- Mock factories for common objects (Config, Provider, State)
