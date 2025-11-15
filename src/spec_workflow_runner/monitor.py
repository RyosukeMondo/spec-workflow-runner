"""Real-time monitor for spec-workflow task progress."""
from __future__ import annotations

import argparse
import time
from pathlib import Path

from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.progress import BarColumn, Progress, TextColumn
from rich.table import Table

from .utils import (
    Config,
    choose_option,
    discover_projects,
    discover_specs,
    load_config,
    read_task_stats,
)


def parse_args() -> argparse.Namespace:
    """Return CLI arguments for the monitor."""
    parser = argparse.ArgumentParser(description="Monitor spec task progress.")
    parser.add_argument(
        "--config",
        type=Path,
        default=Path.cwd() / "config.json",
        help="Path to config.json (default: ./config.json).",
    )
    parser.add_argument("--project", type=Path, help="Project path to monitor.")
    parser.add_argument("--spec", type=str, help="Spec name to monitor.")
    return parser.parse_args()


def ensure_project(cfg: Config, explicit_path: Path | None) -> Path:
    """Return the project being watched, prompting if needed."""
    if explicit_path:
        return explicit_path.resolve()
    projects = discover_projects(cfg)
    return choose_option(
        "Select project",
        projects,
        label=lambda path: f"{path.name}  ({path})",
    )


def ensure_spec(project: Path, cfg: Config, spec_name: str | None) -> tuple[str, Path]:
    """Return the spec path, prompting when no explicit name is supplied."""
    specs = discover_specs(project, cfg)
    if spec_name:
        for name, spec_path in specs:
            if name == spec_name:
                return name, spec_path
        raise SystemExit(f"Spec '{spec_name}' not found under {project}.")
    return choose_option(
        f"Select spec within {project}",
        specs,
        label=lambda pair: pair[0],
    )


def build_dashboard(project: Path, spec_name: str, stats) -> Panel:
    """Return a Rich Panel summarizing the current progress."""
    table = Table.grid(padding=(0, 1))
    table.add_row("[bold]Project[/bold]", str(project))
    table.add_row("[bold]Spec[/bold]", spec_name)
    table.add_row("[bold]Total Tasks[/bold]", str(stats.total))
    table.add_row("[bold]Completed[/bold]", str(stats.done))
    table.add_row("[bold]In Progress[/bold]", str(stats.in_progress))
    table.add_row("[bold]Pending[/bold]", str(stats.pending))

    progress = Progress(
        TextColumn("[bold blue]Tasks[/bold blue]"),
        BarColumn(bar_width=None),
        TextColumn("{task.completed}/{task.total}"),
        expand=True,
    )
    task_id = progress.add_task("tasks", total=max(stats.total, 1))
    progress.update(task_id, completed=stats.done)

    return Panel(
        Group(table, progress),
        title="Spec Workflow Monitor",
        border_style="green" if stats.pending == 0 and stats.in_progress == 0 else "yellow",
    )


def monitor(cfg: Config, project: Path, spec_name: str, spec_path: Path) -> None:
    """Continuously render task status for the selected spec."""
    tasks_path = spec_path / cfg.tasks_filename
    if not tasks_path.exists():
        raise SystemExit(f"tasks.md not found at {tasks_path}.")

    console = Console()
    refresh = cfg.monitor_refresh_seconds

    with Live(console=console, refresh_per_second=4) as live:
        while True:
            stats = read_task_stats(tasks_path)
            live.update(build_dashboard(project, spec_name, stats))
            if stats.pending == 0 and stats.in_progress == 0:
                console.print("[bold green]All tasks complete![/bold green]")
                break
            time.sleep(refresh)


def main() -> int:
    """Script entry point."""
    args = parse_args()
    cfg = load_config(args.config)
    try:
        project = ensure_project(cfg, args.project)
        spec_name, spec_path = ensure_spec(project, cfg, args.spec)
        monitor(cfg, project, spec_name, spec_path)
        return 0
    except KeyboardInterrupt:
        Console().print("\n[red]Aborted by user.[/red]")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
