"""Tests for help panel rendering."""

from __future__ import annotations

from io import StringIO

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from spec_workflow_runner.tui.views.help_panel import render_help_panel


def _render_to_text(panel: Panel) -> str:
    """Helper to render panel to text for assertions."""
    console = Console(file=StringIO(), width=100, legacy_windows=False)
    console.print(panel)
    return console.file.getvalue()  # type: ignore


class TestRenderHelpPanel:
    """Tests for help panel rendering."""

    def test_returns_panel(self) -> None:
        """Verify return type is Rich Panel."""
        panel = render_help_panel()
        assert isinstance(panel, Panel)

    def test_panel_has_title(self) -> None:
        """Panel should have 'Keybindings' title."""
        panel = render_help_panel()
        assert "Keybindings" in str(panel.title)

    def test_panel_contains_table(self) -> None:
        """Panel should contain a table."""
        panel = render_help_panel()
        # The renderable inside the panel should be a Table
        assert isinstance(panel.renderable, Table)

    def test_table_has_correct_columns(self) -> None:
        """Table should have Key, Action, Description columns."""
        panel = render_help_panel()
        table = panel.renderable
        assert isinstance(table, Table)

        # Check column count
        assert len(table.columns) == 3

        # Check column headers
        assert table.columns[0].header == "Key"
        assert table.columns[1].header == "Action"
        assert table.columns[2].header == "Description"

    def test_contains_navigation_section(self) -> None:
        """Help panel should contain navigation section."""
        panel = render_help_panel()
        panel_text = _render_to_text(panel)

        assert "Navigation" in panel_text
        assert "Navigate" in panel_text or "up/down" in panel_text.lower()

    def test_contains_runner_control_section(self) -> None:
        """Help panel should contain runner control section."""
        panel = render_help_panel()
        panel_text = _render_to_text(panel)

        assert "Runner Control" in panel_text
        assert "Start" in panel_text
        assert "Stop" in panel_text

    def test_contains_view_control_section(self) -> None:
        """Help panel should contain view control section."""
        panel = render_help_panel()
        panel_text = _render_to_text(panel)

        assert "View Control" in panel_text
        assert "Toggle" in panel_text or "logs" in panel_text.lower()

    def test_contains_meta_section(self) -> None:
        """Help panel should contain meta commands section."""
        panel = render_help_panel()
        panel_text = _render_to_text(panel)

        assert "Meta" in panel_text
        assert "Help" in panel_text
        assert "Quit" in panel_text

    def test_contains_specific_keybindings(self) -> None:
        """Help panel should document specific keybindings."""
        panel = render_help_panel()
        panel_text = _render_to_text(panel)

        # Navigation keys
        assert "g" in panel_text  # Jump to top
        assert "G" in panel_text  # Jump to bottom

        # Runner control keys
        assert "s" in panel_text  # Start
        assert "x" in panel_text  # Stop
        assert "r" in panel_text  # Restart

        # View control keys
        assert "l" in panel_text  # Toggle logs
        assert "u" in panel_text  # Unfinished only

        # Meta keys
        assert "?" in panel_text  # Help
        assert "q" in panel_text  # Quit

    def test_table_has_rows(self) -> None:
        """Table should have multiple rows for keybindings."""
        panel = render_help_panel()
        table = panel.renderable
        assert isinstance(table, Table)

        # Should have many rows (at least 15+ keybindings)
        assert len(table.rows) >= 15

    def test_panel_styling(self) -> None:
        """Panel should have appropriate styling."""
        panel = render_help_panel()

        # Check border style
        assert panel.border_style == "blue"

        # Check padding
        assert panel.padding == (1, 2)

    def test_table_styling(self) -> None:
        """Table should have appropriate styling."""
        panel = render_help_panel()
        table = panel.renderable
        assert isinstance(table, Table)

        # Check table has header
        assert table.show_header is True

        # Check border style
        assert table.border_style == "blue"

    def test_consistent_rendering(self) -> None:
        """Multiple calls should produce identical output."""
        panel1 = render_help_panel()
        panel2 = render_help_panel()

        text1 = _render_to_text(panel1)
        text2 = _render_to_text(panel2)
        assert text1 == text2

    def test_contains_all_keybinding_categories(self) -> None:
        """All four keybinding categories should be present."""
        panel = render_help_panel()
        panel_text = _render_to_text(panel)

        categories = ["Navigation", "Runner Control", "View Control", "Meta"]
        for category in categories:
            assert category in panel_text, f"Missing category: {category}"
