"""Task list panel renderer for displaying individual tasks.

This module provides the render_task_list_panel function that displays
a detailed list of all tasks from a spec's tasks.md file.
"""

from __future__ import annotations

from pathlib import Path

from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from ..task_parser import Task, TaskStatus, parse_tasks_file


def _get_status_icon(status: TaskStatus) -> tuple[str, str]:
    """Get status icon and color for a task.

    Args:
        status: Task status

    Returns:
        Tuple of (icon, color)
    """
    if status == TaskStatus.COMPLETED:
        return ("✓", "green")
    elif status == TaskStatus.IN_PROGRESS:
        return ("▶", "yellow")
    else:  # PENDING
        return ("○", "dim")


def render_task_list_panel(
    spec_name: str,
    tasks_file_path: Path,
    scroll_offset: int = 0,
    viewport_size: int | None = None,
) -> Panel:
    """Build Rich Panel displaying list of tasks from tasks.md.

    Args:
        spec_name: Name of the spec
        tasks_file_path: Path to tasks.md file
        scroll_offset: Number of tasks to skip from top (for scrolling)
        viewport_size: Maximum number of tasks to show (None = show all)

    Returns:
        Rich Panel component with task list
    """
    tasks, warnings = parse_tasks_file(tasks_file_path)

    # Create table for tasks
    table = Table(
        show_header=True,
        header_style="bold cyan",
        border_style="blue",
        padding=(0, 1),
        expand=True,
    )

    table.add_column("Status", style="cyan", no_wrap=True, width=6)
    table.add_column("ID", style="yellow", no_wrap=True, width=8)
    table.add_column("Task", style="white")

    # Show warnings if any
    if warnings:
        for warning in warnings:
            table.add_row("", "", f"[red]⚠ {warning}[/red]")
        table.add_row("", "", "")

    # Calculate viewport bounds
    total_tasks = len(tasks)
    # Clamp scroll_offset to valid range
    scroll_offset = max(0, min(scroll_offset, max(0, total_tasks - 1)))

    # Determine which tasks to show
    if viewport_size and viewport_size > 0:
        end_offset = min(scroll_offset + viewport_size, total_tasks)
        visible_tasks = tasks[scroll_offset:end_offset]
        showing_range = f"{scroll_offset + 1}-{end_offset}" if visible_tasks else "0"
    else:
        visible_tasks = tasks[scroll_offset:]
        showing_range = f"{scroll_offset + 1}-{total_tasks}" if visible_tasks else "0"

    # Add tasks
    if visible_tasks:
        for task in visible_tasks:
            icon, color = _get_status_icon(task.status)
            status_text = f"[{color}]{icon}[/{color}]"

            # Truncate long titles if needed
            title = task.title
            if len(title) > 60:
                title = title[:57] + "..."

            table.add_row(status_text, task.id, title)
    elif not warnings:
        table.add_row("", "", "[dim italic]No tasks found[/dim italic]")

    # Build panel title with task navigation hints and task count
    task_count = f"[dim]({showing_range}/{total_tasks})[/dim]"
    hints = "[dim](j/k: scroll · t: close)[/dim]"
    title = f"[bold white]Tasks: {spec_name}[/bold white] {task_count} {hints}"

    return Panel(
        table,
        title=title,
        border_style="blue",
        padding=(1, 2),
    )
