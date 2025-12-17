"""Footer bar renderer for status indicators.

This module provides the render_footer_bar function that displays
a status bar with active runner count, error messages, and help hints.
"""

from __future__ import annotations

from rich.text import Text


def _truncate_text(text: str, max_length: int) -> str:
    """Truncate text with ellipsis if it exceeds max length.

    Args:
        text: Text to truncate
        max_length: Maximum length including ellipsis

    Returns:
        Truncated text with "..." suffix if needed
    """
    if len(text) <= max_length:
        return text
    if max_length <= 3:
        return "..."[:max_length]
    return text[: max_length - 3] + "..."


def render_footer_bar(
    active_runner_count: int,
    error_message: str | None = None,
    terminal_width: int = 80,
) -> Text:
    """Build Rich Text displaying footer status bar.

    Args:
        active_runner_count: Number of currently active runners
        error_message: Current error message to display, if any
        terminal_width: Terminal width for truncation calculations

    Returns:
        Rich Text component ready for rendering
    """
    parts = []

    # Active runners count
    if active_runner_count > 0:
        runner_text = (
            f"{active_runner_count} runner active"
            if active_runner_count == 1
            else f"{active_runner_count} runners active"
        )
        parts.append((runner_text, "green"))
    else:
        parts.append(("No runners active", "dim"))

    # Error message (truncated if needed)
    if error_message:
        # Reserve space for runner count, separators, and help hint
        # Format: "[runner count] | [error] | Press ? for help"
        help_hint = " | Press ? for help"
        runner_part = parts[0][0] + " | "
        available_width = terminal_width - len(runner_part) - len(help_hint)

        if available_width > 10:  # Minimum space for meaningful error
            truncated_error = _truncate_text(error_message, available_width)
            parts.append((" | ", "dim"))
            parts.append((truncated_error, "red"))

    # Help hint
    parts.append((" | ", "dim"))
    parts.append(("Press ? for help", "cyan"))

    # Build the Rich Text object
    footer = Text()
    for text, style in parts:
        footer.append(text, style=style)

    return footer
