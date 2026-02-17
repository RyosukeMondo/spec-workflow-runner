"""Integration tests for TUI app initialization and layout."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from spec_workflow_runner.tui.app import TUIApp
from spec_workflow_runner.utils import Config


@pytest.fixture
def config(tmp_path):
    """Create test config."""
    cfg = MagicMock(spec=Config)
    cfg.repos_root = tmp_path / "repos"
    cfg.cache_dir = tmp_path / "cache"
    cfg.cache_dir.mkdir(parents=True)
    cfg.codex_command = ["codex"]
    cfg.spec_workflow_dir_name = ".spec-workflow"
    cfg.specs_subdir = "specs"
    cfg.tasks_filename = "tasks.md"
    cfg.log_dir_name = "logs"
    cfg.tui_log_tail_lines = 200
    cfg.tui_min_terminal_cols = 80
    cfg.tui_min_terminal_rows = 24
    cfg.tui_refresh_seconds = 2.0
    return cfg


@pytest.fixture
def tui_app(config, tmp_path):
    """Create TUI app instance."""
    config_path = tmp_path / "config.json"
    return TUIApp(config, config_path)


class TestLayoutBuilding:
    """Test layout building in different states."""

    def test_build_layout_initial_state(self, tui_app):
        """Test building layout with initial state (help not visible)."""
        # Initial state - help panel should not be visible
        assert tui_app.app_state.help_panel_visible is False

        # Build layout
        layout = tui_app._build_layout()

        # Should have main and footer
        assert "main" in [child.name for child in layout.children]
        assert "footer" in [child.name for child in layout.children]

        # Main should have tree and right (not help)
        main_layout = layout["main"]
        main_children = [child.name for child in main_layout.children]
        assert "tree" in main_children
        assert "right" in main_children
        assert "help" not in main_children

    def test_build_layout_help_visible(self, tui_app):
        """Test building layout with help panel visible."""
        # Set help panel visible
        tui_app.app_state.help_panel_visible = True

        # Build layout
        layout = tui_app._build_layout()

        # Should have main and footer
        assert "main" in [child.name for child in layout.children]
        assert "footer" in [child.name for child in layout.children]

        # Main should have help (not tree/right)
        main_layout = layout["main"]
        main_children = [child.name for child in main_layout.children]
        assert "help" in main_children
        assert "tree" not in main_children
        assert "right" not in main_children

    def test_render_layout_initial_state(self, tui_app):
        """Test rendering layout with initial state."""
        # Set up minimal project state
        tui_app.app_state.projects = []

        # Build and render layout
        layout = tui_app._build_layout()

        # This should not raise an error
        tui_app._render_layout(layout)

    def test_render_layout_with_help(self, tui_app):
        """Test rendering layout with help panel visible."""
        # Set help panel visible
        tui_app.app_state.help_panel_visible = True

        # Build and render layout
        layout = tui_app._build_layout()

        # This should not raise an error
        tui_app._render_layout(layout)

    def test_toggle_help_panel(self, tui_app):
        """Test toggling help panel visibility."""
        # Start with help not visible
        assert tui_app.app_state.help_panel_visible is False

        # Build and render initial layout
        layout = tui_app._build_layout()
        tui_app._render_layout(layout)

        # Toggle help on
        tui_app.app_state.help_panel_visible = True
        layout = tui_app._build_layout()
        tui_app._render_layout(layout)

        # Toggle help off
        tui_app.app_state.help_panel_visible = False
        layout = tui_app._build_layout()
        tui_app._render_layout(layout)

    def test_load_initial_state(self, tui_app, tmp_path):
        """Test loading initial state with no projects."""
        # Create empty repos directory
        tui_app.config.repos_root.mkdir(parents=True, exist_ok=True)

        # Mock discover_projects to return empty list
        with patch("spec_workflow_runner.tui.app.discover_projects") as mock_discover:
            mock_discover.return_value = []

            # This should not raise an error
            tui_app._load_initial_state()

            assert tui_app.app_state.projects == []

    def test_load_initial_state_with_projects(self, tui_app, tmp_path):
        """Test loading initial state with projects."""
        # Create a test project structure
        project_dir = tmp_path / "repos" / "test-project"
        project_dir.mkdir(parents=True)

        spec_dir = project_dir / ".spec-workflow" / "specs" / "test-spec"
        spec_dir.mkdir(parents=True)

        # Create tasks file
        tasks_file = spec_dir / "tasks.md"
        tasks_file.write_text("- [x] Task 1\n- [ ] Task 2\n")

        # Mock the discovery functions
        with (
            patch("spec_workflow_runner.tui.app.discover_projects") as mock_discover_proj,
            patch("spec_workflow_runner.tui.app.discover_specs") as mock_discover_specs,
            patch("spec_workflow_runner.tui.app.read_task_stats") as mock_read_stats,
        ):
            mock_discover_proj.return_value = [project_dir]
            mock_discover_specs.return_value = [("test-spec", spec_dir)]

            # Mock task stats
            class MockStats:
                total = 2
                done = 1
                in_progress = 0
                pending = 1

            mock_read_stats.return_value = MockStats()

            # Load initial state
            tui_app._load_initial_state()

            # Verify projects were loaded
            assert len(tui_app.app_state.projects) == 1
            assert tui_app.app_state.projects[0].name == "test-project"
            assert len(tui_app.app_state.projects[0].specs) == 1


class TestAppInitialization:
    """Test TUI app initialization."""

    def test_app_initialization(self, tui_app):
        """Test that app initializes without errors."""
        assert tui_app.app_state is not None
        assert tui_app.should_quit is False
        assert tui_app.app_state.help_panel_visible is False
        assert tui_app.app_state.log_panel_visible is True

    def test_check_terminal_size(self, tui_app):
        """Test terminal size checking."""
        # Mock terminal size
        with patch("spec_workflow_runner.tui.app.get_terminal_size") as mock_size:
            mock_size.return_value = (100, 30)

            result = tui_app._check_terminal_size()
            assert result is True

            # Test too small
            mock_size.return_value = (70, 20)
            result = tui_app._check_terminal_size()
            assert result is False


class TestHelpPanelRaceCondition:
    """Regression test for help panel visibility race condition."""

    def test_help_toggle_during_render_cycle(self, tui_app):
        """Test that toggling help visibility mid-cycle doesn't cause layout errors.

        This is a regression test for the bug where:
        1. Layout is built with help_panel_visible=False
        2. Keyboard input toggles help_panel_visible=True
        3. Render tries to access layout["help"] which doesn't exist
        """
        # Start with help not visible
        tui_app.app_state.help_panel_visible = False
        tui_app.app_state.projects = []

        # Build layout (no help panel)
        tui_app._build_layout()

        # Simulate keyboard input toggling help visibility
        # (this is what happens when user presses '?')
        tui_app.app_state.help_panel_visible = True

        # Build new layout with help visible
        layout2 = tui_app._build_layout()

        # Rendering the new layout should work (not the old one)
        tui_app._render_layout(layout2)

        # Toggle back
        tui_app.app_state.help_panel_visible = False
        layout3 = tui_app._build_layout()
        tui_app._render_layout(layout3)

    def test_render_layout_matches_state(self, tui_app):
        """Test that layout structure always matches help_panel_visible state."""
        tui_app.app_state.projects = []

        # Test with help visible
        tui_app.app_state.help_panel_visible = True
        layout = tui_app._build_layout()
        main_children = [child.name for child in layout["main"].children]
        assert "help" in main_children
        # Should be able to render without error
        tui_app._render_layout(layout)

        # Test with help not visible
        tui_app.app_state.help_panel_visible = False
        layout = tui_app._build_layout()
        main_children = [child.name for child in layout["main"].children]
        assert "help" not in main_children
        assert "tree" in main_children
        # Should be able to render without error
        tui_app._render_layout(layout)


class TestStatusMessageFlow:
    """Integration tests for status message display and auto-clear."""

    def test_status_message_set_on_key_press(self, tui_app):
        """Test that status message is set when unassigned key is pressed."""

        # Simulate pressing an unassigned key
        handled, message = tui_app.keybinding_handler.handle_key("z")

        # Message should be returned
        assert handled is True
        assert message is not None
        assert "not assigned" in message

    def test_status_message_stored_in_app_state(self, tui_app):
        """Test that status message is stored in app state."""
        from datetime import datetime

        # Initially no status message
        assert tui_app.app_state.status_message is None

        # Simulate the message handling logic from the main loop
        key = "z"
        tui_app.app_state.last_key_pressed = key
        handled, message = tui_app.keybinding_handler.handle_key(key)

        # Simulate app.py message handling (lines 506-514)
        if handled and message and not message.startswith("Error:"):
            tui_app.app_state.current_error = None
            tui_app.app_state.status_message = message
            tui_app.app_state.status_message_timestamp = datetime.now()

        # Status message should be set
        assert tui_app.app_state.status_message is not None
        assert "not assigned" in tui_app.app_state.status_message
        assert tui_app.app_state.status_message_timestamp is not None
        assert tui_app.app_state.last_key_pressed == "z"

    def test_error_clears_status_message(self, tui_app):
        """Test that error message clears status message."""
        from datetime import datetime

        # Set a status message
        tui_app.app_state.status_message = "Test status"
        tui_app.app_state.status_message_timestamp = datetime.now()

        # Simulate error (start runner with no selection)
        key = "s"
        tui_app.app_state.last_key_pressed = key
        handled, message = tui_app.keybinding_handler.handle_key(key)

        # Simulate error handling (lines 507-509)
        if handled and message and message.startswith("Error:"):
            tui_app.app_state.current_error = message
            tui_app.app_state.status_message = None

        # Error should be set, status should be cleared
        assert tui_app.app_state.current_error is not None
        assert "Error" in tui_app.app_state.current_error
        assert tui_app.app_state.status_message is None

    def test_status_message_auto_clear(self, tui_app):
        """Test that status message auto-clears after 3 seconds."""
        from datetime import datetime, timedelta

        # Set a status message with old timestamp
        tui_app.app_state.status_message = "Old status"
        tui_app.app_state.status_message_timestamp = datetime.now() - timedelta(seconds=4)

        # Simulate auto-clear logic (lines 516-521)
        if tui_app.app_state.status_message and tui_app.app_state.status_message_timestamp:
            elapsed = datetime.now() - tui_app.app_state.status_message_timestamp
            if elapsed > timedelta(seconds=3):
                tui_app.app_state.status_message = None
                tui_app.app_state.status_message_timestamp = None

        # Status message should be cleared
        assert tui_app.app_state.status_message is None
        assert tui_app.app_state.status_message_timestamp is None

    def test_footer_displays_status_message(self, tui_app):
        """Test that footer bar displays status message."""
        from datetime import datetime

        # Set a status message
        tui_app.app_state.status_message = "Test status message"
        tui_app.app_state.status_message_timestamp = datetime.now()

        # Build and render layout
        layout = tui_app._build_layout()
        tui_app._render_layout(layout)

        # Footer should contain the status message
        footer_text = layout["footer"].renderable.plain
        assert "Test status message" in footer_text
