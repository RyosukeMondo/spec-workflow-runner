"""Keyboard input handling for TUI application.

This module maps keyboard inputs to actions, handling navigation,
runner control, view control, and meta commands with validation.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .runner_manager import RunnerManager
    from .state import AppState, SpecState

logger = logging.getLogger(__name__)


class KeybindingHandler:
    """Handles keyboard input and dispatches actions with validation."""

    def __init__(self, app_state: AppState, runner_manager: RunnerManager) -> None:
        """Initialize keybinding handler.

        Args:
            app_state: Application state for navigation tracking
            runner_manager: Runner manager for subprocess control
        """
        self.app_state = app_state
        self.runner_manager = runner_manager

    def handle_key(self, key: str) -> tuple[bool, str | None]:
        """Process keyboard input and execute corresponding action.

        Args:
            key: Key press identifier (e.g., "up", "down", "s", "q")

        Returns:
            Tuple of (handled, message):
                - handled: True if key was recognized and handled, False otherwise
                - message: Optional feedback message for user (success/error/info)
        """
        # Navigation handlers
        if key in ("up", "k"):
            return self._handle_move_up()
        if key in ("down", "j"):
            return self._handle_move_down()
        if key in ("enter", "\n", "\r"):
            return self._handle_select()
        if key == "g":
            return self._handle_jump_top()
        if key == "G":
            return self._handle_jump_bottom()
        if key == "/":
            return self._handle_filter_mode()

        # Runner control handlers
        if key == "s":
            return self._handle_start_runner()
        if key == "x":
            return self._handle_stop_runner()
        if key == "r":
            return self._handle_restart_runner()

        # View control handlers
        if key == "l":
            return self._handle_toggle_logs()
        if key == "L":
            return self._handle_reenable_autoscroll()
        if key == "u":
            return self._handle_toggle_unfinished()
        if key == "a":
            return self._handle_show_all_active()

        # Meta handlers
        if key == "?":
            return self._handle_help()
        if key == "c":
            return self._handle_config()
        if key == "q":
            return self._handle_quit()

        # Unhandled key
        return False, None

    # Navigation handlers

    def _handle_move_up(self) -> tuple[bool, str | None]:
        """Move selection up in tree."""
        if not self.app_state.projects:
            return True, None

        # If spec selected, move to previous spec or project
        if (
            self.app_state.selected_project_index is not None
            and self.app_state.selected_spec_index is not None
        ):
            if self.app_state.selected_spec_index > 0:
                # Move to previous spec
                self.app_state.selected_spec_index -= 1
            else:
                # Move to project level
                self.app_state.selected_spec_index = None
        # If project selected, move to previous project
        elif self.app_state.selected_project_index is not None:
            if self.app_state.selected_project_index > 0:
                self.app_state.selected_project_index -= 1
                # Select last spec of previous project if available
                project = self.app_state.selected_project
                if project and project.specs:
                    self.app_state.selected_spec_index = len(project.specs) - 1
        else:
            # Nothing selected, select last project
            self.app_state.selected_project_index = len(self.app_state.projects) - 1
            project = self.app_state.selected_project
            if project and project.specs:
                self.app_state.selected_spec_index = len(project.specs) - 1

        return True, None

    def _handle_move_down(self) -> tuple[bool, str | None]:
        """Move selection down in tree."""
        if not self.app_state.projects:
            return True, None

        # If nothing selected, select first project
        if self.app_state.selected_project_index is None:
            self.app_state.selected_project_index = 0
            return True, None

        project = self.app_state.selected_project
        if not project:
            return True, None

        # If project selected (no spec), move to first spec or next project
        if self.app_state.selected_spec_index is None:
            if project.specs:
                # Move to first spec
                self.app_state.selected_spec_index = 0
            else:
                # No specs, move to next project
                if self.app_state.selected_project_index < len(self.app_state.projects) - 1:
                    self.app_state.selected_project_index += 1
        # If spec selected, move to next spec or next project
        else:
            if self.app_state.selected_spec_index < len(project.specs) - 1:
                # Move to next spec
                self.app_state.selected_spec_index += 1
            else:
                # Last spec, move to next project
                if self.app_state.selected_project_index < len(self.app_state.projects) - 1:
                    self.app_state.selected_project_index += 1
                    self.app_state.selected_spec_index = None

        return True, None

    def _handle_select(self) -> tuple[bool, str | None]:
        """Select/expand current item."""
        if not self.app_state.projects:
            return True, None

        # If project selected (no spec), expand to first spec
        if (
            self.app_state.selected_project_index is not None
            and self.app_state.selected_spec_index is None
        ):
            project = self.app_state.selected_project
            if project and project.specs:
                self.app_state.selected_spec_index = 0
                return True, f"Selected {project.specs[0].name}"
            return True, "No specs in project"

        # If spec already selected, just confirm selection
        spec = self.app_state.selected_spec
        if spec:
            return True, f"Selected {spec.name}"

        return True, None

    def _handle_jump_top(self) -> tuple[bool, str | None]:
        """Jump to top of tree."""
        if not self.app_state.projects:
            return True, None

        self.app_state.selected_project_index = 0
        self.app_state.selected_spec_index = None
        return True, "Jumped to top"

    def _handle_jump_bottom(self) -> tuple[bool, str | None]:
        """Jump to bottom of tree."""
        if not self.app_state.projects:
            return True, None

        self.app_state.selected_project_index = len(self.app_state.projects) - 1
        project = self.app_state.selected_project
        if project and project.specs:
            self.app_state.selected_spec_index = len(project.specs) - 1
        else:
            self.app_state.selected_spec_index = None
        return True, "Jumped to bottom"

    def _handle_filter_mode(self) -> tuple[bool, str | None]:
        """Enter filter mode."""
        self.app_state.filter_mode = True
        return True, "Filter mode: type to search, ESC to cancel"

    # Runner control handlers

    def _handle_start_runner(self) -> tuple[bool, str | None]:
        """Start runner for selected spec."""
        spec = self.app_state.selected_spec
        if not spec:
            return True, "Error: No spec selected"

        if spec.runner is not None:
            return True, f"Error: Runner already active for {spec.name}"

        if not spec.has_unfinished_tasks:
            return True, f"Error: No unfinished tasks in {spec.name}"

        # TODO: Get provider and model from config or user input
        # For now, return error indicating this needs implementation
        return True, "Error: Runner start requires provider selection (not yet implemented)"

    def _handle_stop_runner(self) -> tuple[bool, str | None]:
        """Stop runner for selected spec."""
        spec = self.app_state.selected_spec
        if not spec:
            return True, "Error: No spec selected"

        if spec.runner is None:
            return True, f"Error: No runner active for {spec.name}"

        try:
            self.runner_manager.stop_runner(spec.runner.runner_id)
            return True, f"Stopped runner for {spec.name}"
        except Exception as err:
            logger.error(f"Failed to stop runner: {err}", exc_info=True)
            return True, f"Error stopping runner: {err}"

    def _handle_restart_runner(self) -> tuple[bool, str | None]:
        """Restart runner for selected spec."""
        spec = self.app_state.selected_spec
        if not spec:
            return True, "Error: No spec selected"

        if spec.runner is None:
            return True, f"Error: No runner active for {spec.name}"

        # Stop first, then start would go here
        # For now, just stop
        try:
            self.runner_manager.stop_runner(spec.runner.runner_id)
            return True, f"Stopped runner for {spec.name} (restart start not yet implemented)"
        except Exception as err:
            logger.error(f"Failed to restart runner: {err}", exc_info=True)
            return True, f"Error restarting runner: {err}"

    # View control handlers

    def _handle_toggle_logs(self) -> tuple[bool, str | None]:
        """Toggle log panel visibility."""
        self.app_state.log_panel_visible = not self.app_state.log_panel_visible
        state = "visible" if self.app_state.log_panel_visible else "hidden"
        return True, f"Log panel {state}"

    def _handle_reenable_autoscroll(self) -> tuple[bool, str | None]:
        """Re-enable auto-scroll for logs."""
        self.app_state.log_auto_scroll = True
        return True, "Auto-scroll enabled"

    def _handle_toggle_unfinished(self) -> tuple[bool, str | None]:
        """Toggle showing only unfinished specs."""
        self.app_state.show_unfinished_only = not self.app_state.show_unfinished_only
        state = "enabled" if self.app_state.show_unfinished_only else "disabled"
        return True, f"Show unfinished only: {state}"

    def _handle_show_all_active(self) -> tuple[bool, str | None]:
        """Show all active runners across projects."""
        active_runners = self.runner_manager.get_active_runners()
        count = len(active_runners)
        if count == 0:
            return True, "No active runners"
        runner_list = ", ".join(f"{r.spec_name}" for r in active_runners)
        return True, f"{count} active runner(s): {runner_list}"

    # Meta handlers

    def _handle_help(self) -> tuple[bool, str | None]:
        """Show help panel."""
        # TODO: Implement help panel toggle in app state
        return True, "Help: Press ? to toggle help panel (not yet implemented)"

    def _handle_config(self) -> tuple[bool, str | None]:
        """Show config panel."""
        # TODO: Implement config panel
        return True, "Config panel not yet implemented"

    def _handle_quit(self) -> tuple[bool, str | None]:
        """Signal quit action."""
        # This should be handled by the main app loop
        return True, "quit"  # Special message to signal quit
