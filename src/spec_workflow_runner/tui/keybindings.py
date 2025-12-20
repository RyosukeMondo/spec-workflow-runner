"""Keyboard input handling for TUI application.

This module maps keyboard inputs to actions, handling navigation,
runner control, view control, and meta commands with validation.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..utils import Config
    from .runner_manager import RunnerManager
    from .state import AppState

logger = logging.getLogger(__name__)


class KeybindingHandler:
    """Handles keyboard input and dispatches actions with validation."""

    def __init__(self, app_state: AppState, runner_manager: RunnerManager, config: Config) -> None:
        """Initialize keybinding handler.

        Args:
            app_state: Application state for navigation tracking
            runner_manager: Runner manager for subprocess control
            config: Runtime configuration
        """
        self.app_state = app_state
        self.runner_manager = runner_manager
        self.config = config

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
        # If task list is visible, j/k scroll tasks instead of tree
        if key == "k":
            if self.app_state.task_list_visible:
                return self._handle_scroll_tasks_up()
            else:
                return self._handle_move_up()
        if key == "j":
            if self.app_state.task_list_visible:
                return self._handle_scroll_tasks_down()
            else:
                return self._handle_move_down()
        # Arrow keys always navigate tree
        if key == "up":
            return self._handle_move_up()
        if key == "down":
            return self._handle_move_down()
        if key in ("enter", "\n", "\r"):
            return self._handle_select()
        if key == " ":  # Space bar
            return self._handle_toggle_collapse()
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
        if key == "X":  # Capital X - cleanup dead runners
            return self._handle_cleanup_dead_runners()
        if key == "r":
            return self._handle_restart_runner()
        if key == "F":
            return self._handle_fix_tasks()

        # View control handlers
        if key == "l":
            return self._handle_toggle_logs()
        if key == "L":
            return self._handle_reenable_autoscroll()
        if key == "t":
            return self._handle_toggle_task_list()
        if key == "u":
            return self._handle_toggle_unfinished()
        if key == "f":
            return self._handle_toggle_remaining_filter()
        if key == "a":
            return self._handle_show_all_active()

        # Provider/Model selection handlers
        if key == "p":
            return self._handle_cycle_provider()
        if key == "m":
            return self._handle_cycle_model()

        # Meta handlers
        if key == "?":
            return self._handle_help()
        if key == "c":
            return self._handle_config()
        if key == "q":
            return self._handle_quit()
        if key == "\x1b":  # ESC key
            return self._handle_escape()

        # Unhandled key - provide feedback
        if len(key) == 1 and key.isprintable():
            return True, f"Key '{key}' not assigned"
        elif key in ("left", "right"):
            return True, f"Key '{key}' not assigned"
        else:
            # For special keys, show raw representation
            return True, f"Key {repr(key)} not assigned"

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
                # Select last spec of previous project if not collapsed
                project_idx = self.app_state.selected_project_index
                project = self.app_state.selected_project
                if (
                    project
                    and project.specs
                    and project_idx not in self.app_state.collapsed_projects
                ):
                    self.app_state.selected_spec_index = len(project.specs) - 1
                else:
                    self.app_state.selected_spec_index = None
        else:
            # Nothing selected, select last project
            self.app_state.selected_project_index = len(self.app_state.projects) - 1
            project_idx = self.app_state.selected_project_index
            project = self.app_state.selected_project
            if project and project.specs and project_idx not in self.app_state.collapsed_projects:
                self.app_state.selected_spec_index = len(project.specs) - 1
            else:
                self.app_state.selected_spec_index = None

        # Reset task scroll when changing specs
        self.app_state.task_scroll_offset = 0
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
            project_idx = self.app_state.selected_project_index
            # If project is collapsed, skip specs and go to next project
            if project_idx in self.app_state.collapsed_projects or not project.specs:
                # Move to next project
                if self.app_state.selected_project_index < len(self.app_state.projects) - 1:
                    self.app_state.selected_project_index += 1
            else:
                # Move to first spec
                self.app_state.selected_spec_index = 0
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

        # Reset task scroll when changing specs
        self.app_state.task_scroll_offset = 0
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
                # Uncollapse the project if it's collapsed
                if self.app_state.selected_project_index in self.app_state.collapsed_projects:
                    self.app_state.collapsed_projects.remove(self.app_state.selected_project_index)
                self.app_state.selected_spec_index = 0
                return True, f"Selected {project.specs[0].name}"
            return True, "No specs in project"

        # If spec already selected, just confirm selection
        spec = self.app_state.selected_spec
        if spec:
            return True, f"Selected {spec.name}"

        return True, None

    def _handle_toggle_collapse(self) -> tuple[bool, str | None]:
        """Toggle collapse state of selected project."""
        if not self.app_state.projects:
            return True, None

        # Only toggle if a project is selected (not a spec)
        if (
            self.app_state.selected_project_index is not None
            and self.app_state.selected_spec_index is None
        ):
            project_idx = self.app_state.selected_project_index
            if project_idx in self.app_state.collapsed_projects:
                self.app_state.collapsed_projects.remove(project_idx)
                return True, "Project expanded"
            else:
                self.app_state.collapsed_projects.add(project_idx)
                return True, "Project collapsed"

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

    def _handle_scroll_tasks_up(self) -> tuple[bool, str | None]:
        """Scroll task list up."""
        if self.app_state.task_scroll_offset > 0:
            self.app_state.task_scroll_offset -= 1
        return True, None

    def _handle_scroll_tasks_down(self) -> tuple[bool, str | None]:
        """Scroll task list down."""
        # We'll let the render function handle the max offset based on task count
        self.app_state.task_scroll_offset += 1
        return True, None

    # Runner control handlers

    def _handle_start_runner(self) -> tuple[bool, str | None]:
        """Start runner for selected spec with provider/model selection."""
        spec = self.app_state.selected_spec
        project = self.app_state.selected_project
        if not spec or not project:
            return True, "Error: No spec selected"

        if spec.runner is not None:
            return True, f"Error: Runner already active for {spec.name}"

        if not spec.has_unfinished_tasks:
            return True, f"Error: No unfinished tasks in {spec.name}"

        # Show provider/model selection dialog
        from ..providers import create_provider, get_supported_models

        # Get default provider/model or use stored defaults
        default_provider = self.app_state.default_provider
        default_model = self.app_state.default_model

        # For now, use the defaults without dialog
        # TODO: Add AskUserQuestion dialog here
        provider_name = default_provider

        # Get available models for the selected provider
        available_models = get_supported_models(provider_name)
        model = default_model if default_model in available_models else available_models[0]

        try:
            # Create provider instance
            if provider_name == "codex":
                provider = create_provider(provider_name, self.config.codex_command, model)
            else:
                provider = create_provider(provider_name, [], model)

            self.runner_manager.start_runner(
                project_path=project.path,
                spec_name=spec.name,
                provider=provider,
                model=model,
                total_tasks=spec.total_tasks,
                completed_tasks=spec.completed_tasks,
                in_progress_tasks=spec.in_progress_tasks,
            )

            return True, f"Started runner for {spec.name} ({provider.get_provider_name()}, {model})"
        except Exception as err:
            logger.error(f"Failed to start runner: {err}", exc_info=True)
            return True, f"Error starting runner: {err}"

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

    def _handle_cleanup_dead_runners(self) -> tuple[bool, str | None]:
        """Cleanup all dead/crashed runners from state."""
        import os
        from dataclasses import replace

        from ..tui.models import RunnerStatus

        cleaned = 0
        for runner_id, runner in list(self.runner_manager.runners.items()):
            # Check if it's marked as running but PID doesn't exist
            if runner.status == RunnerStatus.RUNNING:
                try:
                    os.kill(runner.pid, 0)  # Check if process exists
                except (OSError, ProcessLookupError):
                    # Process is dead, mark as crashed
                    logger.info(f"Cleaning up dead runner {runner_id} (PID {runner.pid})")
                    crashed = replace(runner, status=RunnerStatus.CRASHED, exit_code=-1)
                    self.runner_manager.runners[runner_id] = crashed
                    cleaned += 1

        if cleaned > 0:
            self.runner_manager._persist_state()
            return True, f"Cleaned up {cleaned} dead runner(s)"
        else:
            return True, "No dead runners found"

    def _handle_restart_runner(self) -> tuple[bool, str | None]:
        """Restart runner for selected spec."""
        spec = self.app_state.selected_spec
        project = self.app_state.selected_project
        if not spec or not project:
            return True, "Error: No spec selected"

        if spec.runner is None:
            return True, f"Error: No runner active for {spec.name}"

        try:
            # Stop the current runner
            runner_id = spec.runner.runner_id
            self.runner_manager.stop_runner(runner_id)

            # Start a new runner with same provider/model
            from ..providers import create_provider, get_supported_models

            provider_name = self.app_state.default_provider
            available_models = get_supported_models(provider_name)
            model = self.app_state.default_model
            if model is None or model not in available_models:
                model = available_models[0]

            if provider_name == "codex":
                provider = create_provider(provider_name, self.config.codex_command, model)
            else:
                provider = create_provider(provider_name, [], model)

            self.runner_manager.start_runner(
                project_path=project.path,
                spec_name=spec.name,
                provider=provider,
                model=model,
                total_tasks=spec.total_tasks,
                completed_tasks=spec.completed_tasks,
                in_progress_tasks=spec.in_progress_tasks,
            )
            return True, f"Restarted runner for {spec.name}"
        except Exception as err:
            logger.error(f"Failed to restart runner: {err}", exc_info=True)
            return True, f"Error restarting runner: {err}"

    def _handle_fix_tasks(self) -> tuple[bool, str | None]:
        """Auto-fix format errors in selected spec's tasks.md file."""
        spec = self.app_state.selected_spec
        project = self.app_state.selected_project
        if not spec or not project:
            return True, "Error: No spec selected"

        try:
            # Build tasks.md file path
            tasks_file = project.path / ".spec-workflow" / "specs" / spec.name / "tasks.md"
            if not tasks_file.exists():
                return True, f"Error: tasks.md not found for {spec.name}"

            # Create provider with sonnet model
            from ..providers import create_provider

            if self.app_state.default_provider == "codex":
                provider = create_provider("codex", self.config.codex_command, "sonnet")
            else:
                provider = create_provider(self.app_state.default_provider, [], "sonnet")

            # Create TaskFixer and run fix (blocking)
            from ..task_fixer import create_task_fixer

            fixer = create_task_fixer(provider, project.path)
            result = fixer.fix_tasks_file(tasks_file, project.path)

            # Check result and return appropriate message
            if not result.success:
                error_msg = result.error_message or "Unknown error"
                return True, f"Error fixing {spec.name}: {error_msg}"

            if not result.has_changes:
                return True, f"No changes needed for {spec.name}"

            # Apply the fix
            if result.fixed_content:
                write_result = fixer.apply_fix(tasks_file, result.fixed_content)
                if not write_result.success:
                    return True, f"Error writing fix: {write_result.error_message}"

                # Show diff summary
                if result.diff_result:
                    summary = result.diff_result.changes_summary
                    return True, f"Fixed {spec.name}: {summary}"

            return True, f"Fixed {spec.name}"

        except Exception as err:
            logger.error(f"Failed to fix tasks: {err}", exc_info=True)
            return True, f"Error fixing tasks: {err}"

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

    def _handle_toggle_task_list(self) -> tuple[bool, str | None]:
        """Toggle task list panel visibility."""
        spec = self.app_state.selected_spec
        if not spec:
            return True, "Error: No spec selected"

        self.app_state.task_list_visible = not self.app_state.task_list_visible
        # Reset scroll position when toggling
        self.app_state.task_scroll_offset = 0
        state = "visible" if self.app_state.task_list_visible else "hidden"
        return True, f"Task list {state}"

    def _handle_toggle_unfinished(self) -> tuple[bool, str | None]:
        """Toggle showing only unfinished specs."""
        self.app_state.show_unfinished_only = not self.app_state.show_unfinished_only
        state = "enabled" if self.app_state.show_unfinished_only else "disabled"
        return True, f"Show unfinished only: {state}"

    def _handle_toggle_remaining_filter(self) -> tuple[bool, str | None]:
        """Toggle filter to show only projects/specs with remaining tasks."""
        self.app_state.show_unfinished_only = not self.app_state.show_unfinished_only
        state = "ON" if self.app_state.show_unfinished_only else "OFF"
        return True, f"Filter remaining tasks: {state}"

    def _handle_show_all_active(self) -> tuple[bool, str | None]:
        """Show all active runners across projects."""
        active_runners = self.runner_manager.get_active_runners()
        count = len(active_runners)
        if count == 0:
            return True, "No active runners"
        runner_list = ", ".join(f"{r.spec_name}" for r in active_runners)
        return True, f"{count} active runner(s): {runner_list}"

    # Provider/Model selection handlers

    def _handle_cycle_provider(self) -> tuple[bool, str | None]:
        """Cycle through available providers."""
        providers = ["codex", "claude", "gemini"]
        current_provider = self.app_state.default_provider

        # Find current index and get next
        try:
            current_index = providers.index(current_provider)
            next_index = (current_index + 1) % len(providers)
        except ValueError:
            next_index = 0

        next_provider = providers[next_index]
        self.app_state.default_provider = next_provider

        # Reset model to None so it uses the provider's first model
        self.app_state.default_model = None

        # Get provider display name
        from ..providers import get_supported_models

        available_models = get_supported_models(next_provider)
        first_model = available_models[0]

        provider_names = {
            "codex": "Codex",
            "claude": "Claude CLI",
            "gemini": "Google Gemini",
        }

        return True, f"Provider: {provider_names[next_provider]} | Model: {first_model}"

    def _handle_cycle_model(self) -> tuple[bool, str | None]:
        """Cycle through available models for current provider."""
        from ..providers import get_supported_models

        provider = self.app_state.default_provider
        available_models = get_supported_models(provider)

        current_model = self.app_state.default_model
        if current_model is None:
            current_model = available_models[0]

        # Find current index and get next
        try:
            current_index = available_models.index(current_model)
            next_index = (current_index + 1) % len(available_models)
        except ValueError:
            next_index = 0

        next_model = available_models[next_index]
        self.app_state.default_model = next_model

        provider_names = {
            "codex": "Codex",
            "claude": "Claude CLI",
            "gemini": "Google Gemini",
        }

        return (
            True,
            f"Provider: {provider_names[provider]} | Model: {next_model}",
        )

    # Meta handlers

    def _handle_help(self) -> tuple[bool, str | None]:
        """Toggle help panel visibility."""
        self.app_state.help_panel_visible = not self.app_state.help_panel_visible
        state = "visible" if self.app_state.help_panel_visible else "hidden"
        return True, f"Help panel {state}"

    def _handle_config(self) -> tuple[bool, str | None]:
        """Show config information."""
        repos_root = str(self.config.repos_root)
        cache_dir = str(self.config.cache_dir)
        return True, f"Repos: {repos_root} | Cache: {cache_dir}"

    def _handle_escape(self) -> tuple[bool, str | None]:
        """Handle ESC key - close help panel if open."""
        if self.app_state.help_panel_visible:
            self.app_state.help_panel_visible = False
            return True, None
        return True, None

    def _handle_quit(self) -> tuple[bool, str | None]:
        """Signal quit action."""
        # This should be handled by the main app loop
        return True, "quit"  # Special message to signal quit
