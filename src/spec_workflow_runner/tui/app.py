"""Main TUI application loop and layout.

This module orchestrates the TUI application with real-time updates,
integrating StatePoller, RunnerManager, KeybindingHandler, and all view components.
"""

from __future__ import annotations

import logging
import queue
import select
import sys
from pathlib import Path

from rich.console import Console
from rich.layout import Layout
from rich.live import Live

from ..utils import Config, discover_projects, discover_specs, load_config, read_task_stats
from .keybindings import KeybindingHandler
from .runner_manager import RunnerManager
from .state import AppState, ProjectState, SpecState, StatePoller, StateUpdate
from .tui_utils import get_terminal_size
from .views.footer_bar import render_footer_bar
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

        # Initialize managers
        self.runner_manager = RunnerManager(config, config_path)
        self.keybinding_handler = KeybindingHandler(self.app_state, self.runner_manager)

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

        # Attach runner states to specs
        self._sync_runner_states()

        logger.info(f"Loaded {len(project_states)} project(s) with specs")

    def _sync_runner_states(self) -> None:
        """Sync runner states from RunnerManager to spec states."""
        # Build map of (project_path, spec_name) -> runner
        runner_map: dict[tuple[Path, str], str] = {}
        for runner_id, runner in self.runner_manager.runners.items():
            key = (runner.project_path, runner.spec_name)
            runner_map[key] = runner_id

        # Update active_runners in app_state
        self.app_state.active_runners = dict(self.runner_manager.runners)

        # Attach runners to specs
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
            f"State update: project={update.project}, spec={update.spec}, "
            f"type={update.update_type}"
        )

        if update.update_type == "runner_state":
            # Reload runner states from disk
            self._sync_runner_states()

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
                            break
                    break

        elif update.update_type == "logs":
            # Update log viewer path if this is the selected spec
            selected_spec = self.app_state.selected_spec
            if selected_spec and selected_spec.name == update.spec:
                if update.data:
                    log_path = Path(update.data)
                    self.log_viewer.update_log_path(log_path)

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

        # Split main into left (tree) and right (status + logs)
        layout["main"].split_row(
            Layout(name="tree", ratio=3),
            Layout(name="right", ratio=7),
        )

        # Split right into status (top) and logs (bottom)
        if self.app_state.log_panel_visible:
            layout["right"].split_column(
                Layout(name="status", ratio=6),
                Layout(name="logs", ratio=4),
            )
        else:
            layout["right"].update(Layout(name="status"))

        return layout

    def _render_layout(self, layout: Layout) -> None:
        """Render all panels into the layout.

        Args:
            layout: Layout to render into
        """
        # Render tree view
        tree = render_tree(
            projects=self.app_state.projects,
            selected_project_index=self.app_state.selected_project_index,
            selected_spec_index=self.app_state.selected_spec_index,
            filter_text=self.app_state.filter_text,
            show_unfinished_only=self.app_state.show_unfinished_only,
        )
        layout["tree"].update(tree)

        # Render status panel
        selected_spec = self.app_state.selected_spec
        project_path = None
        if self.app_state.selected_project:
            project_path = str(self.app_state.selected_project.path)

        status_panel = render_status_panel(selected_spec, project_path)
        layout["status"].update(status_panel)

        # Render logs panel if visible
        if self.app_state.log_panel_visible and "logs" in layout:
            # Poll log viewer for new content
            self.log_viewer.poll()
            logs_panel = self.log_viewer.render_panel(self.app_state.log_auto_scroll)
            layout["logs"].update(logs_panel)

        # Render footer
        active_runner_count = len(
            [r for r in self.app_state.active_runners.values() if r.status.value == "running"]
        )
        footer = render_footer_bar(
            active_runner_count=active_runner_count,
            error_message=self.app_state.current_error,
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
                key = sys.stdin.read(1)
                return key
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
            # Load initial state
            self._load_initial_state()

            # Check terminal size
            if not self._check_terminal_size():
                self.app_state.current_error = (
                    f"Terminal too small! Need {self.min_terminal_cols}x"
                    f"{self.min_terminal_rows}, got {self.terminal_width}x"
                    f"{self.terminal_height}"
                )

            # Start state poller
            self._start_state_poller()

            # Build initial layout
            layout = self._build_layout()

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
                    if not self._check_terminal_size():
                        if self.app_state.current_error is None:
                            self.app_state.current_error = (
                                f"Terminal too small! Need {self.min_terminal_cols}x"
                                f"{self.min_terminal_rows}"
                            )
                    else:
                        # Clear size error if terminal is now OK
                        if (
                            self.app_state.current_error
                            and "Terminal too small" in self.app_state.current_error
                        ):
                            self.app_state.current_error = None

                        # Rebuild layout on resize
                        layout = self._build_layout()

                    # Poll for keyboard input
                    key = self._poll_keyboard(timeout=0.1)
                    if key:
                        handled, message = self.keybinding_handler.handle_key(key)
                        if handled and message:
                            if message == "quit":
                                self.should_quit = True
                            else:
                                # Display message (could be success or error)
                                if message.startswith("Error:"):
                                    self.app_state.current_error = message
                                else:
                                    # Clear error on successful action
                                    self.app_state.current_error = None

                    # Update log viewer for selected spec
                    selected_spec = self.app_state.selected_spec
                    if selected_spec and selected_spec.runner:
                        # Find latest log file
                        log_dir = (
                            selected_spec.path / self.config.log_dir_name
                        )
                        if log_dir.exists():
                            log_files = sorted(
                                log_dir.glob("*.log"),
                                key=lambda f: f.stat().st_mtime,
                                reverse=True,
                            )
                            if log_files:
                                self.log_viewer.update_log_path(log_files[0])
                    elif not selected_spec:
                        self.log_viewer.update_log_path(None)

                    # Check runner health and update commit info
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
                        except KeyError:
                            # Runner was removed
                            pass
                        except Exception as err:
                            logger.warning(f"Error checking runner {runner_id}: {err}")

                    # Sync runner states to specs
                    self._sync_runner_states()

                    # Re-render layout
                    self._render_layout(layout)
                    live.update(layout)

            logger.info("TUI main loop exited")
            return 0

        except KeyboardInterrupt:
            logger.info("TUI interrupted by user")
            return 130

        except Exception as err:
            logger.error(f"TUI crashed: {err}", exc_info=True)
            self.console.print(f"[red]Error: {err}[/red]")
            return 1

        finally:
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

        # Stop state poller
        if self.state_poller:
            self.state_poller.stop()

        # Shutdown runner manager
        self.runner_manager.shutdown(stop_all=stop_all, timeout=timeout)

        logger.info("TUI shutdown complete")
