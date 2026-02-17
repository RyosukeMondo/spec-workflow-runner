"""Main TUI application loop and layout.

This module orchestrates the TUI application with real-time updates,
integrating StatePoller, RunnerManager, KeybindingHandler, and all view components.
"""

from __future__ import annotations

import fcntl
import logging
import os
import queue
import select
import sys
import termios
import tty
from datetime import datetime, timedelta
from pathlib import Path

from rich.console import Console
from rich.layout import Layout
from rich.live import Live

from ..utils import Config, discover_projects, discover_specs, read_task_stats
from .keybindings import KeybindingHandler
from .runner_manager import RunnerManager
from .state import AppState, ProjectState, SpecState, StatePoller, StateUpdate
from .tui_utils import get_terminal_size
from .views.footer_bar import render_footer_bar
from .views.help_panel import render_help_panel
from .views.log_viewer import LogViewer
from .views.status_panel import render_status_panel
from .views.tree_view import render_tree

logger = logging.getLogger(__name__)


class TUIApp:
    """Main TUI application orchestrating all components."""

    def __init__(self, config: Config, config_path: Path):
        """Initialize TUI application.

        Args:
            config: Runtime configuration
            config_path: Path to config.json
        """
        self.config = config
        self.config_path = config_path
        self.console = Console()

        # Initialize state
        self.app_state = AppState()
        self.should_quit = False

        # Terminal state for restoration
        self.original_terminal_settings = None

        # Initialize managers
        self.runner_manager = RunnerManager(config, config_path)
        self.keybinding_handler = KeybindingHandler(self.app_state, self.runner_manager, config)

        # Initialize log viewer
        log_tail_lines = getattr(config, "tui_log_tail_lines", 200)
        self.log_viewer = LogViewer(max_lines=log_tail_lines)

        # Initialize state poller
        self.update_queue: queue.Queue[StateUpdate] = queue.Queue()
        self.state_poller: StatePoller | None = None

        # Terminal size tracking
        self.terminal_width, self.terminal_height = get_terminal_size()
        self.min_terminal_cols = getattr(config, "tui_min_terminal_cols", 80)
        self.min_terminal_rows = getattr(config, "tui_min_terminal_rows", 24)

        # Performance optimization - track when to check runner health
        self.last_health_check = datetime.now()
        self.health_check_interval = timedelta(seconds=2)

    def _load_initial_state(self) -> None:
        """Load initial project and spec state."""
        logger.info("Loading initial project state")

        # Discover projects
        projects = discover_projects(self.config, force_refresh=False)
        logger.info(f"Discovered {len(projects)} project(s)")

        # Build project state
        project_states: list[ProjectState] = []
        for project_path in projects:
            try:
                specs_info = discover_specs(project_path, self.config)
                spec_states: list[SpecState] = []

                for spec_name, spec_path in specs_info:
                    tasks_path = spec_path / self.config.tasks_filename
                    if tasks_path.exists():
                        stats = read_task_stats(tasks_path)
                        spec_state = SpecState(
                            name=spec_name,
                            path=spec_path,
                            total_tasks=stats.total,
                            completed_tasks=stats.done,
                            in_progress_tasks=stats.in_progress,
                            pending_tasks=stats.pending,
                            runner=None,
                        )
                        spec_states.append(spec_state)

                if spec_states:
                    project_state = ProjectState(
                        path=project_path,
                        name=project_path.name,
                        specs=spec_states,
                    )
                    project_states.append(project_state)

            except Exception as err:
                logger.warning(f"Failed to load project {project_path.name}: {err}")
                continue

        self.app_state.projects = project_states

        # Collapse all projects by default
        self.app_state.collapsed_projects = set(range(len(project_states)))

        # Attach runner states to specs
        self._sync_runner_states()

        logger.info(f"Loaded {len(project_states)} project(s) with specs")

    def _sync_runner_states(self) -> None:
        """Sync runner states from RunnerManager to spec states."""
        from .models import RunnerStatus

        # Build map of (project_path, spec_name) -> runner (RUNNING only)
        runner_map: dict[tuple[Path, str], str] = {}
        for runner_id, runner in self.runner_manager.runners.items():
            # Only attach RUNNING runners to specs for display
            if runner.status == RunnerStatus.RUNNING:
                key = (runner.project_path, runner.spec_name)
                runner_map[key] = runner_id

        # Update active_runners in app_state (keep all runners for history)
        self.app_state.active_runners = dict(self.runner_manager.runners)

        # Attach runners to specs (only RUNNING ones)
        for project in self.app_state.projects:
            for spec in project.specs:
                key = (project.path, spec.name)
                runner_id = runner_map.get(key)
                if runner_id:
                    spec.runner = self.runner_manager.runners[runner_id]
                else:
                    spec.runner = None

    def _start_state_poller(self) -> None:
        """Start background state poller thread."""
        refresh_seconds = getattr(self.config, "tui_refresh_seconds", 2.0)
        state_file = self.config.cache_dir / "runner_state.json"

        project_paths = [p.path for p in self.app_state.projects]

        self.state_poller = StatePoller(
            projects=project_paths,
            spec_workflow_dir=self.config.spec_workflow_dir_name,
            specs_subdir=self.config.specs_subdir,
            tasks_filename=self.config.tasks_filename,
            log_dir_name=self.config.log_dir_name,
            state_file=state_file,
            update_queue=self.update_queue,
            refresh_seconds=refresh_seconds,
        )
        self.state_poller.start()
        logger.info("State poller started")

    def _process_state_updates(self) -> None:
        """Process all pending state updates from queue."""
        try:
            while True:
                update = self.update_queue.get_nowait()
                self._handle_state_update(update)
        except queue.Empty:
            pass

    def _handle_state_update(self, update: StateUpdate) -> None:
        """Handle a single state update.

        Args:
            update: State update to process
        """
        logger.debug(
            f"State update: project={update.project}, spec={update.spec}, type={update.update_type}"
        )

        if update.update_type == "runner_state":
            # Reload runner states from disk
            self._sync_runner_states()
            self.app_state.mark_dirty()

        elif update.update_type == "tasks":
            # Update task counts for the spec
            for project in self.app_state.projects:
                if project.name == update.project:
                    for spec in project.specs:
                        if spec.name == update.spec:
                            tasks_path = spec.path / self.config.tasks_filename
                            if tasks_path.exists():
                                stats = read_task_stats(tasks_path)
                                spec.total_tasks = stats.total
                                spec.completed_tasks = stats.done
                                spec.in_progress_tasks = stats.in_progress
                                spec.pending_tasks = stats.pending
                            self.app_state.mark_dirty()
                            break
                    break

        elif update.update_type == "logs":
            # Update log viewer path if this is the selected spec
            selected_spec = self.app_state.selected_spec
            if selected_spec and selected_spec.name == update.spec:
                if update.data:
                    log_path = Path(update.data)
                    self.log_viewer.update_log_path(log_path)
                    self.app_state.mark_dirty()

    def _check_terminal_size(self) -> bool:
        """Check if terminal meets minimum size requirements.

        Returns:
            True if terminal is large enough, False otherwise
        """
        self.terminal_width, self.terminal_height = get_terminal_size()
        return (
            self.terminal_width >= self.min_terminal_cols
            and self.terminal_height >= self.min_terminal_rows
        )

    def _calculate_selected_line_index(self) -> int | None:
        """Calculate the line index of the currently selected item in the tree.

        Returns:
            Line index (0-based) or None if nothing selected
        """
        if self.app_state.selected_project_index is None:
            return None

        line_index = 0
        for proj_idx, project in enumerate(self.app_state.projects):
            # Apply same filtering as render_tree
            if self.app_state.show_unfinished_only:
                visible_specs = [s for s in project.specs if s.has_unfinished_tasks]
            else:
                visible_specs = project.specs

            if not visible_specs:
                continue

            # Count project line
            if proj_idx == self.app_state.selected_project_index:
                if self.app_state.selected_spec_index is None:
                    return line_index
                # Selected spec is under this project
                line_index += 1  # Skip project line
                # Check if project is collapsed
                if proj_idx in self.app_state.collapsed_projects:
                    return line_index - 1  # Return project line
                # Count to selected spec
                spec_count = 0
                for _spec in visible_specs:
                    if spec_count == self.app_state.selected_spec_index:
                        return line_index
                    line_index += 1
                    spec_count += 1
                return line_index
            else:
                # Count this project and its visible specs
                line_index += 1  # Project line
                if proj_idx not in self.app_state.collapsed_projects:
                    line_index += len(visible_specs)  # Spec lines

        return None

    def _build_layout(self) -> Layout:
        """Build the multi-panel layout.

        Returns:
            Rich Layout with all panels configured
        """
        layout = Layout()

        # Split into main content and footer
        layout.split_column(
            Layout(name="main", ratio=1),
            Layout(name="footer", size=1),
        )

        # If help panel is visible, show it instead of normal content
        if self.app_state.help_panel_visible:
            layout["main"].split_column(
                Layout(name="help", ratio=1),
            )
        else:
            # Split main into left (tree) and right (status + logs)
            layout["main"].split_row(
                Layout(name="tree", ratio=4),
                Layout(name="right", ratio=6),
            )

            # Split right into status (top) and logs/tasks (bottom)
            show_logs = self.app_state.log_panel_visible
            show_tasks = self.app_state.task_list_visible

            if show_logs or show_tasks:
                layout["right"].split_column(
                    Layout(name="status", ratio=6),
                    Layout(name="logs", ratio=4),
                )
            else:
                # Even with one child, use split_column to create named layout
                layout["right"].split_column(
                    Layout(name="status", ratio=1),
                )

        return layout

    def _render_layout(self, layout: Layout) -> None:
        """Render all panels into the layout.

        Args:
            layout: Layout to render into
        """
        # If help panel is visible, render it
        if self.app_state.help_panel_visible:
            help_panel = render_help_panel()
            layout["help"].update(help_panel)
        else:
            # Calculate viewport size for tree panel - maximize to show all projects
            # The tree panel should use most of the available height
            tree_panel_height = self.terminal_height - 1  # Subtract footer
            # Tree should get about 90% of available height (very generous)
            tree_panel_height = int(tree_panel_height * 0.9)
            # Subtract minimal overhead for borders
            tree_panel_height = max(15, tree_panel_height - 2)

            self.app_state.tree_viewport_size = tree_panel_height

            # Calculate viewport offset to keep selected item visible
            selected_line = self._calculate_selected_line_index()
            if selected_line is not None:
                # Try to center selected item in viewport
                ideal_offset = selected_line - (tree_panel_height // 2)
                self.app_state.tree_viewport_offset = max(0, ideal_offset)

            # Render tree view with viewport
            tree, viewport_info = render_tree(
                projects=self.app_state.projects,
                selected_project_index=self.app_state.selected_project_index,
                selected_spec_index=self.app_state.selected_spec_index,
                filter_text=self.app_state.filter_text,
                show_unfinished_only=self.app_state.show_unfinished_only,
                collapsed_projects=self.app_state.collapsed_projects,
                viewport_offset=self.app_state.tree_viewport_offset,
                viewport_limit=self.app_state.tree_viewport_size,
            )
            layout["tree"].update(tree)

            # Render status panel
            selected_spec = self.app_state.selected_spec
            project_path = None
            if self.app_state.selected_project:
                project_path = str(self.app_state.selected_project.path)

            status_panel = render_status_panel(selected_spec, project_path)
            layout["status"].update(status_panel)

            # Render logs or task list panel if visible
            if self.app_state.task_list_visible and selected_spec:
                # Render task list panel
                from .views.task_list_panel import render_task_list_panel

                # Calculate viewport size for tasks - maximize available space
                # Layout: main_height = terminal - footer, right panel gets full main height
                # Task panel gets 40% of right in layout (ratio 4 out of 10)
                # But we want to fill it completely, so be more aggressive
                main_height = self.terminal_height - 1  # Subtract footer
                # Allocate 50% of main height to task panel (more generous than layout ratio)
                task_panel_height = main_height // 2
                # Subtract only 2 lines for table header and minimal spacing
                task_viewport_size = max(10, task_panel_height - 2)

                # Debug logging
                logger.info(
                    f"Task viewport calculation: terminal_height={self.terminal_height}, "
                    f"main_height={main_height}, task_panel_height={task_panel_height}, "
                    f"task_viewport_size={task_viewport_size}"
                )

                tasks_file = selected_spec.path / self.config.tasks_filename
                task_panel = render_task_list_panel(
                    selected_spec.name,
                    tasks_file,
                    scroll_offset=self.app_state.task_scroll_offset,
                    viewport_size=task_viewport_size,
                )
                layout["logs"].update(task_panel)
            elif self.app_state.log_panel_visible:
                # Render log viewer (polling happens in main loop)
                logs_panel = self.log_viewer.render_panel(self.app_state.log_auto_scroll)
                layout["logs"].update(logs_panel)

        # Render footer
        active_runner_count = len(
            [r for r in self.app_state.active_runners.values() if r.status.value == "running"]
        )
        footer = render_footer_bar(
            active_runner_count=active_runner_count,
            error_message=self.app_state.current_error,
            status_message=self.app_state.status_message,
            last_key=self.app_state.last_key_pressed,
            terminal_width=self.terminal_width,
        )
        layout["footer"].update(footer)

    def _poll_keyboard(self, timeout: float = 0.1) -> str | None:
        """Poll for keyboard input with timeout.

        Args:
            timeout: Timeout in seconds

        Returns:
            Key string if key pressed, None otherwise
        """
        # Check if stdin has data available
        ready, _, _ = select.select([sys.stdin], [], [], timeout)
        if ready:
            try:
                # Set stdin to non-blocking to read all available data
                fd = sys.stdin.fileno()
                flags = fcntl.fcntl(fd, fcntl.F_GETFL)
                fcntl.fcntl(fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)

                # Read all available input
                data = ""
                try:
                    while True:
                        chunk = sys.stdin.read(1)
                        if not chunk:
                            break
                        data += chunk
                except BlockingIOError:
                    # No more data available
                    pass
                finally:
                    # Restore blocking mode
                    fcntl.fcntl(fd, fcntl.F_SETFL, flags)

                if not data:
                    return None

                # Parse the input
                # Handle escape sequences (arrow keys, etc.)
                if data.startswith("\x1b["):
                    # ANSI escape sequence
                    if len(data) >= 3:
                        direction = data[2]
                        # Map arrow keys
                        if direction == "A":
                            return "up"
                        elif direction == "B":
                            return "down"
                        elif direction == "C":
                            return "right"
                        elif direction == "D":
                            return "left"
                        else:
                            logger.debug(f"Unknown escape sequence: {repr(data)}")
                            return None
                    else:
                        # Incomplete escape sequence
                        logger.debug(f"Incomplete escape sequence: {repr(data)}")
                        return None
                elif data == "\x1b":
                    # Just ESC
                    return "\x1b"
                elif len(data) == 1:
                    # Single character
                    return data
                else:
                    # Multiple characters or unknown sequence
                    logger.debug(f"Unknown input sequence: {repr(data)}")
                    # Return first character only
                    return data[0]

            except Exception as err:
                logger.warning(f"Error reading keyboard input: {err}")
                return None
        return None

    def run(self) -> int:
        """Run the main TUI event loop.

        Returns:
            Exit code (0 for success, non-zero for error)
        """
        try:
            # Save original terminal settings
            self.original_terminal_settings = termios.tcgetattr(sys.stdin)

            # Set terminal to cbreak mode (raw mode without disabling Ctrl+C)
            tty.setcbreak(sys.stdin.fileno())

            # Load initial state
            logger.debug("Loading initial state")
            self._load_initial_state()

            # Check terminal size
            logger.debug("Checking terminal size")
            if not self._check_terminal_size():
                self.app_state.current_error = (
                    f"Terminal too small! Need {self.min_terminal_cols}x"
                    f"{self.min_terminal_rows}, got {self.terminal_width}x"
                    f"{self.terminal_height}"
                )

            # Start state poller
            logger.debug("Starting state poller")
            self._start_state_poller()

            # Build initial layout
            logger.debug(
                f"Building initial layout (help_visible={self.app_state.help_panel_visible})"
            )
            layout = self._build_layout()
            logger.debug(f"Layout children: {[child.name for child in layout.children]}")

            # Render initial layout before entering Live context
            logger.debug("Rendering initial layout")
            self._render_layout(layout)
            logger.debug("Initial layout rendered successfully")

            # Enter Rich Live context for flicker-free updates
            with Live(
                layout,
                console=self.console,
                refresh_per_second=4,
                screen=True,
            ) as live:
                logger.info("TUI main loop started")

                while not self.should_quit:
                    # Process state updates from poller
                    self._process_state_updates()

                    # Check for terminal resize
                    prev_width, prev_height = self.terminal_width, self.terminal_height
                    if not self._check_terminal_size():
                        if self.app_state.current_error is None:
                            self.app_state.current_error = (
                                f"Terminal too small! Need {self.min_terminal_cols}x"
                                f"{self.min_terminal_rows}"
                            )
                            self.app_state.mark_dirty()
                    else:
                        # Clear size error if terminal is now OK
                        if (
                            self.app_state.current_error
                            and "Terminal too small" in self.app_state.current_error
                        ):
                            self.app_state.current_error = None
                            self.app_state.mark_dirty()
                        # Mark dirty if terminal size changed
                        if self.terminal_width != prev_width or self.terminal_height != prev_height:
                            self.app_state.mark_dirty()

                    # Poll for keyboard input
                    key = self._poll_keyboard(timeout=0.1)
                    if key:
                        # Track last key pressed for debugging
                        self.app_state.last_key_pressed = key

                        handled, message = self.keybinding_handler.handle_key(key)
                        if handled:
                            # Keyboard input changed state, mark dirty
                            self.app_state.mark_dirty()
                            if message:
                                if message == "quit":
                                    self.should_quit = True
                                else:
                                    # Display message (could be success, info, or error)
                                    if message.startswith("Error:"):
                                        self.app_state.current_error = message
                                        self.app_state.status_message = None
                                    else:
                                        # Clear error and show status message
                                        self.app_state.current_error = None
                                        self.app_state.status_message = message
                                        self.app_state.status_message_timestamp = datetime.now()

                    # Auto-clear status messages after 3 seconds
                    if self.app_state.status_message and self.app_state.status_message_timestamp:
                        elapsed = datetime.now() - self.app_state.status_message_timestamp
                        if elapsed > timedelta(seconds=3):
                            self.app_state.status_message = None
                            self.app_state.status_message_timestamp = None
                            self.app_state.mark_dirty()

                    # Update log viewer for selected spec
                    selected_spec = self.app_state.selected_spec
                    if selected_spec and selected_spec.runner:
                        # Find latest log file
                        log_dir = selected_spec.path / self.config.log_dir_name
                        if log_dir.exists():
                            log_files = sorted(
                                log_dir.glob("*.log"),
                                key=lambda f: f.stat().st_mtime,
                                reverse=True,
                            )
                            if log_files and log_files[0] != self.log_viewer.log_path:
                                self.log_viewer.update_log_path(log_files[0])
                                self.app_state.mark_dirty()
                    elif not selected_spec:
                        if self.log_viewer.log_path is not None:
                            self.log_viewer.update_log_path(None)
                            self.app_state.mark_dirty()

                    # Poll log viewer for new content
                    if self.app_state.log_panel_visible and self.log_viewer.log_path:
                        if self.log_viewer.poll():
                            self.app_state.mark_dirty()

                    # Check runner health and update commit info (only every 2 seconds)
                    now = datetime.now()
                    if now - self.last_health_check >= self.health_check_interval:
                        self.last_health_check = now
                        state_changed = False

                        for runner_id in list(self.runner_manager.runners.keys()):
                            try:
                                self.runner_manager.check_runner_health(runner_id)

                                # Detect new commits
                                commit_hash, commit_msg = self.runner_manager.detect_new_commits(
                                    runner_id
                                )
                                if commit_hash:
                                    runner = self.runner_manager.runners[runner_id]
                                    from dataclasses import replace

                                    updated = replace(
                                        runner,
                                        last_commit_hash=commit_hash,
                                        last_commit_message=commit_msg,
                                    )
                                    self.runner_manager.runners[runner_id] = updated
                                    state_changed = True
                            except KeyError:
                                # Runner was removed
                                state_changed = True
                            except Exception as err:
                                logger.warning(f"Error checking runner {runner_id}: {err}")

                        # Sync runner states to specs
                        if state_changed:
                            self._sync_runner_states()
                            self.app_state.mark_dirty()

                    # Only rebuild and re-render if state changed
                    if self.app_state._needs_render:
                        # Rebuild layout to ensure it matches current state
                        # (keyboard input may have toggled help_panel_visible)
                        layout = self._build_layout()

                        # Re-render layout
                        self._render_layout(layout)
                        live.update(layout)

                        # Mark state as clean
                        self.app_state.mark_clean()

            logger.info("TUI main loop exited")
            return 0

        except KeyboardInterrupt:
            logger.info("TUI interrupted by user")
            return 130

        except Exception as err:
            import traceback

            logger.error(f"TUI crashed: {err}", exc_info=True)
            self.console.print(f"[red]Error: {err}[/red]")
            self.console.print("[dim]Full logs at: ~/.cache/spec-workflow-runner/tui.log[/dim]")
            self.console.print("\n[yellow]Traceback:[/yellow]")
            self.console.print(traceback.format_exc())
            return 1

        finally:
            # Restore terminal settings
            if self.original_terminal_settings:
                termios.tcsetattr(sys.stdin, termios.TCSADRAIN, self.original_terminal_settings)

            # Stop state poller
            if self.state_poller:
                self.state_poller.stop()

            # Shutdown runner manager (without stopping runners by default)
            # The shutdown handler will handle runner cleanup
            logger.info("TUI cleanup complete")

    def shutdown(self, stop_all: bool = False, timeout: int = 10) -> None:
        """Graceful shutdown of TUI.

        Args:
            stop_all: If True, stop all running processes
            timeout: Seconds to wait for each process to terminate
        """
        logger.info(f"Shutting down TUI (stop_all={stop_all})")

        # Restore terminal settings
        if self.original_terminal_settings:
            termios.tcsetattr(sys.stdin, termios.TCSADRAIN, self.original_terminal_settings)

        # Stop state poller
        if self.state_poller:
            self.state_poller.stop()

        # Shutdown runner manager
        self.runner_manager.shutdown(stop_all=stop_all, timeout=timeout)

        logger.info("TUI shutdown complete")
