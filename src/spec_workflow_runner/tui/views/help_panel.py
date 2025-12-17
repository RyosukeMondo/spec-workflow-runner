"""Help panel renderer for keybinding reference.

This module provides the render_help_panel function that displays
a comprehensive table of all available keybindings organized by category.
"""

from __future__ import annotations

from rich.panel import Panel
from rich.table import Table


def render_help_panel() -> Panel:
    """Build Rich Panel displaying keybinding reference table.

    Returns:
        Rich Panel component with categorized keybindings
    """
    # Create table with columns
    table = Table(
        show_header=True,
        header_style="bold magenta",
        border_style="blue",
        padding=(0, 1),
    )
    table.add_column("Key", style="cyan", no_wrap=True)
    table.add_column("Action", style="yellow")
    table.add_column("Description", style="white")

    # Navigation keybindings
    table.add_row("", "", "")
    table.add_row("", "[bold cyan]Navigation[/bold cyan]", "", style="bold")
    table.add_row("↑/↓", "Navigate", "Move up/down in tree")
    table.add_row("Enter", "Select/Expand", "Select spec or expand/collapse project")
    table.add_row("g", "Jump to top", "Jump to first item in tree")
    table.add_row("G", "Jump to bottom", "Jump to last item in tree")
    table.add_row("/", "Filter", "Enter filter mode to search specs")

    # Runner Control keybindings
    table.add_row("", "", "")
    table.add_row("", "[bold green]Runner Control[/bold green]", "", style="bold")
    table.add_row("s", "Start", "Start runner for selected spec")
    table.add_row("x", "Stop", "Stop runner for selected spec")
    table.add_row("r", "Restart", "Restart runner for selected spec")

    # View Control keybindings
    table.add_row("", "", "")
    table.add_row("", "[bold yellow]View Control[/bold yellow]", "", style="bold")
    table.add_row("l", "Toggle logs", "Toggle log auto-scroll on/off")
    table.add_row("L", "Re-enable scroll", "Re-enable auto-scroll for logs")
    table.add_row("u", "Unfinished only", "Filter to show only specs with unfinished tasks")
    table.add_row("a", "All active", "Show all specs with active runners")

    # Meta keybindings
    table.add_row("", "", "")
    table.add_row("", "[bold magenta]Meta[/bold magenta]", "", style="bold")
    table.add_row("?", "Help", "Toggle this help panel")
    table.add_row("c", "Config", "Reload configuration")
    table.add_row("q", "Quit", "Exit TUI (prompts if runners active)")

    return Panel(
        table,
        title="[bold white]Keybindings[/bold white]",
        border_style="blue",
        padding=(1, 2),
    )
