"""Tests for project collapse/expand functionality."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from spec_workflow_runner.tui.keybindings import KeybindingHandler
from spec_workflow_runner.tui.models import AppState, ProjectState, SpecState
from spec_workflow_runner.tui.runner_manager import RunnerManager
from spec_workflow_runner.tui.views.tree_view import render_tree
from spec_workflow_runner.utils import Config


@pytest.fixture
def config():
    """Create mock config."""
    cfg = MagicMock(spec=Config)
    cfg.repos_root = Path("/tmp/repos")
    cfg.cache_dir = Path("/tmp/cache")
    cfg.codex_command = ["codex"]
    return cfg


@pytest.fixture
def app_state():
    """Create app state with test data."""
    state = AppState()
    state.projects = [
        ProjectState(
            path=Path("/test/project1"),
            name="project1",
            specs=[
                SpecState(
                    name="spec1",
                    path=Path("/test/project1/spec1"),
                    total_tasks=10,
                    completed_tasks=5,
                    in_progress_tasks=2,
                    pending_tasks=3,
                ),
                SpecState(
                    name="spec2",
                    path=Path("/test/project1/spec2"),
                    total_tasks=5,
                    completed_tasks=5,
                    in_progress_tasks=0,
                    pending_tasks=0,
                ),
            ],
        ),
        ProjectState(
            path=Path("/test/project2"),
            name="project2",
            specs=[
                SpecState(
                    name="spec3",
                    path=Path("/test/project2/spec3"),
                    total_tasks=8,
                    completed_tasks=2,
                    in_progress_tasks=1,
                    pending_tasks=5,
                ),
            ],
        ),
    ]
    return state


@pytest.fixture
def keybinding_handler(app_state, config):
    """Create keybinding handler with mocked dependencies."""
    runner_manager = MagicMock(spec=RunnerManager)
    return KeybindingHandler(app_state, runner_manager, config)


class TestToggleCollapse:
    """Test collapse/expand toggle functionality."""

    def test_toggle_collapse_on_project(self, app_state, keybinding_handler):
        """Test toggling collapse on a selected project."""
        # Select first project
        app_state.selected_project_index = 0
        app_state.selected_spec_index = None

        # Toggle collapse
        handled, message = keybinding_handler._handle_toggle_collapse()
        assert handled is True
        assert message == "Project collapsed"
        assert 0 in app_state.collapsed_projects

        # Toggle again to expand
        handled, message = keybinding_handler._handle_toggle_collapse()
        assert handled is True
        assert message == "Project expanded"
        assert 0 not in app_state.collapsed_projects

    def test_toggle_collapse_on_spec_does_nothing(self, app_state, keybinding_handler):
        """Test that toggle collapse does nothing when spec is selected."""
        # Select first spec
        app_state.selected_project_index = 0
        app_state.selected_spec_index = 0

        # Try to toggle collapse
        handled, message = keybinding_handler._handle_toggle_collapse()
        assert handled is True
        assert message is None
        assert len(app_state.collapsed_projects) == 0

    def test_toggle_collapse_with_no_selection(self, app_state, keybinding_handler):
        """Test that toggle collapse does nothing with no selection."""
        app_state.selected_project_index = None
        app_state.selected_spec_index = None

        handled, message = keybinding_handler._handle_toggle_collapse()
        assert handled is True
        assert message is None
        assert len(app_state.collapsed_projects) == 0


class TestNavigationWithCollapsedProjects:
    """Test navigation skips collapsed projects correctly."""

    def test_move_down_from_collapsed_project(self, app_state, keybinding_handler):
        """Test moving down from a collapsed project skips specs."""
        # Select and collapse first project
        app_state.selected_project_index = 0
        app_state.selected_spec_index = None
        app_state.collapsed_projects.add(0)

        # Move down should skip to next project, not first spec
        handled, _ = keybinding_handler._handle_move_down()
        assert handled is True
        assert app_state.selected_project_index == 1
        assert app_state.selected_spec_index is None

    def test_move_down_from_expanded_project(self, app_state, keybinding_handler):
        """Test moving down from expanded project goes to first spec."""
        # Select first project (not collapsed)
        app_state.selected_project_index = 0
        app_state.selected_spec_index = None

        # Move down should go to first spec
        handled, _ = keybinding_handler._handle_move_down()
        assert handled is True
        assert app_state.selected_project_index == 0
        assert app_state.selected_spec_index == 0

    def test_move_up_to_collapsed_project(self, app_state, keybinding_handler):
        """Test moving up to collapsed project stops at project level."""
        # Select second project
        app_state.selected_project_index = 1
        app_state.selected_spec_index = None
        # Collapse first project
        app_state.collapsed_projects.add(0)

        # Move up should select collapsed project at project level
        handled, _ = keybinding_handler._handle_move_up()
        assert handled is True
        assert app_state.selected_project_index == 0
        assert app_state.selected_spec_index is None

    def test_move_up_to_expanded_project(self, app_state, keybinding_handler):
        """Test moving up to expanded project goes to last spec."""
        # Select second project
        app_state.selected_project_index = 1
        app_state.selected_spec_index = None

        # Move up should go to last spec of first project
        handled, _ = keybinding_handler._handle_move_up()
        assert handled is True
        assert app_state.selected_project_index == 0
        assert app_state.selected_spec_index == 1  # Last spec


class TestEnterKeyWithCollapsed:
    """Test Enter key behavior with collapsed projects."""

    def test_enter_expands_collapsed_project(self, app_state, keybinding_handler):
        """Test that Enter on collapsed project expands and selects first spec."""
        # Select and collapse first project
        app_state.selected_project_index = 0
        app_state.selected_spec_index = None
        app_state.collapsed_projects.add(0)

        # Press Enter
        handled, message = keybinding_handler._handle_select()
        assert handled is True
        assert 0 not in app_state.collapsed_projects  # Should be expanded
        assert app_state.selected_spec_index == 0  # First spec selected
        assert "spec1" in message


class TestTreeRenderingWithCollapsed:
    """Test tree rendering with collapsed projects."""

    def test_render_tree_with_collapsed_projects(self):
        """Test that render_tree accepts collapsed_projects parameter."""
        from rich.tree import Tree

        projects = [
            ProjectState(
                path=Path("/test/project1"),
                name="project1",
                specs=[
                    SpecState(
                        name="spec1",
                        path=Path("/test/project1/spec1"),
                        total_tasks=10,
                        completed_tasks=5,
                        in_progress_tasks=2,
                        pending_tasks=3,
                    ),
                ],
            ),
        ]

        # Test with collapsed set
        tree, _ = render_tree(
            projects=projects,
            selected_project_index=None,
            selected_spec_index=None,
            collapsed_projects={0},
        )
        assert isinstance(tree, Tree)

        # Test with empty collapsed set
        tree, _ = render_tree(
            projects=projects,
            selected_project_index=None,
            selected_spec_index=None,
            collapsed_projects=set(),
        )
        assert isinstance(tree, Tree)

        # Test with None (defaults to empty set)
        tree, _ = render_tree(
            projects=projects,
            selected_project_index=None,
            selected_spec_index=None,
            collapsed_projects=None,
        )
        assert isinstance(tree, Tree)

    def test_collapsed_project_children_count(self):
        """Test that collapsed project has fewer children than expanded."""
        projects = [
            ProjectState(
                path=Path("/test/project1"),
                name="project1",
                specs=[
                    SpecState(
                        name="spec1",
                        path=Path("/test/project1/spec1"),
                        total_tasks=10,
                        completed_tasks=5,
                        in_progress_tasks=2,
                        pending_tasks=3,
                    ),
                    SpecState(
                        name="spec2",
                        path=Path("/test/project1/spec2"),
                        total_tasks=5,
                        completed_tasks=5,
                        in_progress_tasks=0,
                        pending_tasks=0,
                    ),
                ],
            ),
        ]

        # Render expanded
        tree_expanded, _ = render_tree(
            projects=projects,
            selected_project_index=None,
            selected_spec_index=None,
            collapsed_projects=set(),
        )

        # Render collapsed
        tree_collapsed, _ = render_tree(
            projects=projects,
            selected_project_index=None,
            selected_spec_index=None,
            collapsed_projects={0},
        )

        # Get project nodes
        project_node_expanded = list(tree_expanded.children)[0]
        project_node_collapsed = list(tree_collapsed.children)[0]

        # Expanded should have child specs, collapsed should not
        assert len(list(project_node_expanded.children)) == 2
        assert len(list(project_node_collapsed.children)) == 0
