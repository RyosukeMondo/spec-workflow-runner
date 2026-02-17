"""CLI entry point for TUI application.

This module handles command-line argument parsing, logging setup,
signal handling, and the main entry point.
"""

from __future__ import annotations

import argparse
import json
import logging
import logging.handlers
import signal
import sys
from datetime import UTC, datetime
from pathlib import Path

from rich.console import Console

from ..providers import ClaudeProvider
from ..task_fixer import create_task_fixer
from ..utils import discover_specs, load_config
from .app import TUIApp

logger = logging.getLogger(__name__)


class JSONFormatter(logging.Formatter):
    """Custom JSON formatter for structured logging."""

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON.

        Args:
            record: Log record to format

        Returns:
            JSON-formatted log line
        """
        log_data = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "event": record.getMessage(),
            "context": {
                "module": record.module,
                "function": record.funcName,
                "line": record.lineno,
            },
        }

        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        # Add extra context from record if present
        if hasattr(record, "extra_context"):
            log_data["context"].update(record.extra_context)

        return json.dumps(log_data)


def _setup_logging(log_file: Path, debug: bool) -> None:
    """Setup structured JSON logging to file.

    Args:
        log_file: Path to log file
        debug: Enable debug level logging
    """
    # Create log directory if needed
    log_file.parent.mkdir(parents=True, exist_ok=True)

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG if debug else logging.INFO)

    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Create rotating file handler (10MB max, 3 backups)
    file_handler = logging.handlers.RotatingFileHandler(
        log_file,
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setFormatter(JSONFormatter())
    file_handler.setLevel(logging.DEBUG if debug else logging.INFO)

    root_logger.addHandler(file_handler)

    logger.info(
        "Logging initialized",
        extra={"extra_context": {"log_file": str(log_file), "debug": debug}},
    )


def _parse_args() -> argparse.Namespace:
    """Parse command line arguments.

    Returns:
        Parsed arguments
    """
    parser = argparse.ArgumentParser(
        prog="spec-workflow-tui",
        description="Terminal UI for managing spec workflow runners",
    )

    parser.add_argument(
        "--config",
        type=Path,
        default=Path("./config.json"),
        help="Path to config.json (default: ./config.json)",
    )

    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging",
    )

    parser.add_argument(
        "--fix",
        type=str,
        metavar="SPEC_NAME",
        help="Auto-fix format errors in the specified spec's tasks.md file",
    )

    return parser.parse_args()


# Global TUI app instance for signal handlers
_app_instance: TUIApp | None = None


def _signal_handler(signum: int, frame) -> None:
    """Handle shutdown signals.

    Args:
        signum: Signal number
        frame: Current stack frame
    """
    global _app_instance

    if _app_instance is None:
        sys.exit(130 if signum == signal.SIGINT else 1)

    if signum == signal.SIGINT:
        # SIGINT (Ctrl+C): Prompt user about active runners
        logger.info("Received SIGINT, initiating graceful shutdown")
        _app_instance.should_quit = True

    elif signum == signal.SIGTERM:
        # SIGTERM: Immediate shutdown, stop all runners
        logger.info("Received SIGTERM, stopping all runners")
        _app_instance.shutdown(stop_all=True, timeout=10)
        sys.exit(0)


def _find_spec_path(spec_name: str, project_path: Path, config) -> Path | None:
    """Find the spec directory path by name.

    Args:
        spec_name: Name of the spec to find
        project_path: Path to project root
        config: Configuration object

    Returns:
        Path to spec directory, or None if not found
    """
    console = Console()
    try:
        specs = discover_specs(project_path, config)
    except FileNotFoundError as err:
        console.print(f"[red]Error: {err}[/red]")
        logger.error(
            "Specs directory not found",
            extra={"extra_context": {"project_path": str(project_path)}},
        )
        return None

    for name, path in specs:
        if name == spec_name:
            return path

    available_specs = ", ".join([name for name, _ in specs])
    console.print(f"[red]Error: Spec '{spec_name}' not found[/red]")
    console.print(f"[dim]Available specs: {available_specs}[/dim]")
    logger.error(
        "Spec not found",
        extra={"extra_context": {"spec_name": spec_name, "available": available_specs}},
    )
    return None


def _run_fix(fixer, tasks_file: Path, project_path: Path, console: Console):
    """Run the fix operation and return the result.

    Args:
        fixer: TaskFixer instance
        tasks_file: Path to tasks.md file
        project_path: Path to project root
        console: Rich Console for output

    Returns:
        FixResult or None on error
    """
    console.print(f"[cyan]Analyzing {tasks_file}...[/cyan]")
    logger.info("Starting auto-fix", extra={"extra_context": {"tasks_file": str(tasks_file)}})

    try:
        return fixer.fix_tasks_file(tasks_file, project_path)
    except Exception as err:
        console.print(f"[red]Error during fix: {err}[/red]")
        logger.error("Auto-fix failed", extra={"extra_context": {"error": str(err)}}, exc_info=True)
        return None


def _display_diff(diff_result, console: Console) -> None:
    """Display the diff with change summary.

    Args:
        diff_result: DiffResult to display
        console: Rich Console for output
    """
    console.print("\n[bold]Proposed changes:[/bold]")
    console.print(diff_result.diff_text)
    console.print(
        f"\n[dim]Changes: +{diff_result.lines_added} "
        f"-{diff_result.lines_removed} "
        f"~{diff_result.lines_modified}[/dim]\n"
    )


def _apply_fix_with_confirmation(
    fixer, tasks_file: Path, fixed_content: str, console: Console
) -> int:
    """Apply the fix after user confirmation.

    Args:
        fixer: TaskFixer instance
        tasks_file: Path to tasks.md file
        fixed_content: Fixed content to write
        console: Rich Console for output

    Returns:
        Exit code (0=success, 1=error)
    """
    console.print("[yellow]Apply these changes? (y/n): [/yellow]", end="")
    response = input().strip().lower()

    if response != "y":
        console.print("[yellow]Fix cancelled - no changes made[/yellow]")
        logger.info("Fix cancelled by user")
        return 0

    try:
        write_result = fixer.apply_fix(tasks_file, fixed_content)
        if write_result.success:
            console.print("[green]✓ File fixed successfully[/green]")
            console.print(f"[dim]Backup created at: {write_result.backup_path}[/dim]")
            logger.info(
                "Fix applied", extra={"extra_context": {"backup": str(write_result.backup_path)}}
            )
            return 0
        else:
            console.print(f"[red]Failed to write file: {write_result.error_message}[/red]")
            logger.error(
                "Write failed", extra={"extra_context": {"error": write_result.error_message}}
            )
            return 1
    except Exception as err:
        console.print(f"[red]Error applying fix: {err}[/red]")
        logger.error("Apply fix error", extra={"extra_context": {"error": str(err)}}, exc_info=True)
        return 1


def _handle_fix_command(spec_name: str, config_path: Path) -> int:
    """Handle --fix command to auto-fix a spec's tasks.md file.

    Args:
        spec_name: Name of the spec to fix
        config_path: Path to config file

    Returns:
        Exit code (0=success, 1=error)
    """
    console = Console()

    try:
        config = load_config(config_path)
        logger.info("Config loaded", extra={"extra_context": {"spec_name": spec_name}})
    except Exception as err:
        console.print(f"[red]Error loading config: {err}[/red]")
        logger.error(
            "Config load failed", extra={"extra_context": {"error": str(err)}}, exc_info=True
        )
        return 1

    project_path = Path.cwd()
    spec_path = _find_spec_path(spec_name, project_path, config)
    if spec_path is None:
        return 1

    tasks_file = spec_path / "tasks.md"
    if not tasks_file.exists():
        console.print(f"[red]Error: tasks.md not found at {tasks_file}[/red]")
        logger.error("tasks.md not found", extra={"extra_context": {"tasks_file": str(tasks_file)}})
        return 1

    provider = ClaudeProvider(model="sonnet")
    fixer = create_task_fixer(provider, project_path)

    fix_result = _run_fix(fixer, tasks_file, project_path, console)
    if fix_result is None:
        return 1

    if not fix_result.success:
        console.print(f"[red]Fix failed: {fix_result.error_message}[/red]")
        logger.error("Fix failed", extra={"extra_context": {"error": fix_result.error_message}})
        return 1

    if not fix_result.has_changes:
        console.print("[green]✓ File is already valid - no changes needed[/green]")
        logger.info("File already valid")
        return 0

    if fix_result.diff_result:
        _display_diff(fix_result.diff_result, console)

    return _apply_fix_with_confirmation(fixer, tasks_file, fix_result.fixed_content, console)


def main() -> int:
    """Main entry point for TUI application.

    Returns:
        Exit code (0=success, 1=error, 130=SIGINT)
    """
    global _app_instance

    # Parse arguments
    args = _parse_args()

    # Setup logging
    log_dir = Path.home() / ".cache" / "spec-workflow-runner"
    log_file = log_dir / "tui.log"
    _setup_logging(log_file, args.debug)

    # Handle --fix command (bypasses TUI)
    if args.fix:
        logger.info(
            "Fix command invoked",
            extra={"extra_context": {"spec_name": args.fix, "config_path": str(args.config)}},
        )
        return _handle_fix_command(args.fix, args.config.resolve())

    logger.info(
        "TUI starting",
        extra={"extra_context": {"config_path": str(args.config), "debug": args.debug}},
    )

    try:
        # Load configuration
        config_path = args.config.resolve()
        if not config_path.exists():
            console = Console()
            console.print(f"[red]Error: Config file not found: {config_path}[/red]")
            console.print("Create a config.json file or specify path with --config")
            logger.error(
                "Config file not found",
                extra={"extra_context": {"config_path": str(config_path)}},
            )
            return 1

        try:
            config = load_config(config_path)
            logger.info(
                "Config loaded successfully",
                extra={
                    "extra_context": {
                        "repos_root": str(config.repos_root),
                        "cache_dir": str(config.cache_dir),
                    }
                },
            )
        except Exception as err:
            console = Console()
            console.print(f"[red]Error loading config: {err}[/red]")
            logger.error(
                "Failed to load config",
                extra={"extra_context": {"error": str(err)}},
                exc_info=True,
            )
            return 1

        # Create TUI app
        _app_instance = TUIApp(config, config_path)

        # Register signal handlers
        signal.signal(signal.SIGINT, _signal_handler)
        signal.signal(signal.SIGTERM, _signal_handler)

        # Run TUI
        exit_code = _app_instance.run()

        logger.info(
            "TUI exited",
            extra={"extra_context": {"exit_code": exit_code}},
        )

        return exit_code

    except KeyboardInterrupt:
        logger.info("TUI interrupted by user (KeyboardInterrupt)")
        # Handle shutdown with prompt
        if _app_instance:
            active_runners = len(
                [
                    r
                    for r in _app_instance.runner_manager.runners.values()
                    if r.status.value == "running"
                ]
            )

            if active_runners > 0:
                console = Console()
                console.print(
                    f"\n[yellow]{active_runners} runner(s) active. "
                    f"Stop all and quit? (y/n/c)[/yellow]"
                )
                response = input().strip().lower()

                if response == "y":
                    console.print("[yellow]Stopping all runners...[/yellow]")
                    _app_instance.shutdown(stop_all=True, timeout=10)
                    console.print("[green]All runners stopped.[/green]")
                elif response == "n":
                    console.print("[yellow]Leaving runners active.[/yellow]")
                    _app_instance.shutdown(stop_all=False, timeout=0)
                elif response == "c":
                    console.print("[yellow]Cancelled. Returning to TUI...[/yellow]")
                    # User cancelled - could restart TUI here, but for now just exit
                    _app_instance.shutdown(stop_all=False, timeout=0)
                else:
                    console.print("[yellow]Invalid response. Leaving runners active.[/yellow]")
                    _app_instance.shutdown(stop_all=False, timeout=0)
            else:
                _app_instance.shutdown(stop_all=False, timeout=0)

        return 130

    except Exception as err:
        logger.error(
            "TUI crashed with unhandled exception",
            extra={"extra_context": {"error": str(err)}},
            exc_info=True,
        )
        console = Console()
        console.print(f"[red]Fatal error: {err}[/red]")
        console.print(f"[dim]Check logs at: {log_file}[/dim]")
        return 1

    finally:
        if _app_instance:
            _app_instance.shutdown(stop_all=False, timeout=0)


if __name__ == "__main__":
    sys.exit(main())
