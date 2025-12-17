"""Status panel renderer for spec details.

This module provides the render_status_panel function that displays detailed
information about the selected spec including task progress and runner status.
"""

from __future__ import annotations

from datetime import datetime

from rich.panel import Panel
from rich.progress import Progress, BarColumn, TextColumn
from rich.table import Table
from rich.text import Text

from ..state import SpecState


def _format_duration(started_at: datetime) -> str:
    """Format duration from start time to now as HH:MM:SS.

    Args:
        started_at: Start timestamp

    Returns:
        Duration string in HH:MM:SS format
    """
    duration = datetime.now() - started_at
    total_seconds = int(duration.total_seconds())

    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60

    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def render_status_panel(spec: SpecState | None, project_path: str | None = None) -> Panel:
    """Build Rich Panel displaying spec task progress and runner details.

    Args:
        spec: Selected spec state to display, or None if no spec selected
        project_path: Path to the project containing the spec

    Returns:
        Rich Panel component ready for rendering
    """
    # Handle no spec selected
    if spec is None:
        content = Text(
            "Select a spec from the tree to view details",
            justify="center",
            style="dim italic"
        )
        return Panel(
            content,
            title="Status",
            border_style="dim",
            padding=(1, 2)
        )

    # Build metadata table
    metadata_table = Table.grid(padding=(0, 2))
    metadata_table.add_column(style="bold cyan", justify="right")
    metadata_table.add_column()

    # Add metadata rows
    if project_path:
        metadata_table.add_row("Project:", project_path)
    metadata_table.add_row("Spec:", spec.name)
    metadata_table.add_row("Total Tasks:", str(spec.total_tasks))
    metadata_table.add_row("Completed:", str(spec.completed_tasks))
    metadata_table.add_row("In Progress:", str(spec.in_progress_tasks))
    metadata_table.add_row("Pending:", str(spec.pending_tasks))

    # Add progress bar
    progress = Progress(
        TextColumn("[bold blue]Progress:"),
        BarColumn(complete_style="green", finished_style="green"),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
    )
    progress_task = progress.add_task(
        "",
        total=spec.total_tasks if spec.total_tasks > 0 else 1,
        completed=spec.completed_tasks
    )

    # Build content list
    content_items = [metadata_table, "", progress]

    # Add runner section if runner is active
    if spec.runner:
        content_items.append("")
        content_items.append(Text("Runner Details", style="bold yellow"))
        content_items.append("")

        runner_table = Table.grid(padding=(0, 2))
        runner_table.add_column(style="bold cyan", justify="right")
        runner_table.add_column()

        # Provider and model
        runner_table.add_row(
            "Provider/Model:",
            f"{spec.runner.provider} - {spec.runner.model}"
        )

        # Running duration
        duration = _format_duration(spec.runner.started_at)
        runner_table.add_row("Running Duration:", duration)

        # PID
        runner_table.add_row("PID:", str(spec.runner.pid))

        # Last commit if available
        if spec.runner.last_commit_hash and spec.runner.last_commit_message:
            commit_info = (
                f"{spec.runner.last_commit_hash[:7]} - "
                f"{spec.runner.last_commit_message}"
            )
            runner_table.add_row("Last Commit:", commit_info)

        content_items.append(runner_table)

    # Combine all content into a single renderable group
    from rich.console import Group
    content = Group(*content_items)

    # Determine border color based on completion status
    border_style = "green" if spec.is_complete else "yellow"

    return Panel(
        content,
        title=f"[bold]{spec.name}[/bold]",
        border_style=border_style,
        padding=(1, 2)
    )
