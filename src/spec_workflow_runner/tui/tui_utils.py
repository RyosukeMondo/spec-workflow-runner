"""TUI utility functions for formatting and display helpers."""

import shutil
from datetime import timedelta
from enum import Enum


class RunnerStatus(Enum):
    """Runner status enumeration."""

    RUNNING = "running"
    STOPPED = "stopped"
    CRASHED = "crashed"
    COMPLETED = "completed"


def format_duration(seconds: float) -> str:
    """
    Format duration in seconds to HH:MM:SS string.

    Args:
        seconds: Duration in seconds (can be float)

    Returns:
        String formatted as HH:MM:SS (e.g., "01:23:45")

    Examples:
        >>> format_duration(0)
        '00:00:00'
        >>> format_duration(3661)
        '01:01:01'
        >>> format_duration(86400)
        '24:00:00'
    """
    if seconds < 0:
        seconds = 0

    td = timedelta(seconds=int(seconds))
    total_seconds = int(td.total_seconds())
    hours, remainder = divmod(total_seconds, 3600)
    minutes, secs = divmod(remainder, 60)

    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def truncate_text(text: str, max_len: int) -> str:
    """
    Truncate text to max length, adding ellipsis if needed.

    Args:
        text: Text to truncate
        max_len: Maximum length including ellipsis

    Returns:
        Truncated text with "..." suffix if text exceeds max_len

    Examples:
        >>> truncate_text("short", 10)
        'short'
        >>> truncate_text("this is a long text", 10)
        'this is...'
    """
    if len(text) <= max_len:
        return text

    if max_len <= 3:
        return "..."[:max_len]

    return text[: max_len - 3] + "..."


def get_terminal_size() -> tuple[int, int]:
    """
    Get terminal size as (columns, rows) tuple.

    Returns:
        Tuple of (columns, rows), defaults to (80, 24) if unavailable

    Examples:
        >>> cols, rows = get_terminal_size()
        >>> isinstance(cols, int) and isinstance(rows, int)
        True
    """
    try:
        size = shutil.get_terminal_size(fallback=(80, 24))
        return (size.columns, size.lines)
    except Exception:
        return (80, 24)


def get_status_badge(status: RunnerStatus) -> tuple[str, str]:
    """
    Get emoji and color for a RunnerStatus.

    Args:
        status: RunnerStatus enum value

    Returns:
        Tuple of (emoji, color) for the given status

    Examples:
        >>> get_status_badge(RunnerStatus.RUNNING)
        ('▶', 'yellow')
        >>> get_status_badge(RunnerStatus.COMPLETED)
        ('✓', 'green')
    """
    badge_map = {
        RunnerStatus.RUNNING: ("▶", "yellow"),
        RunnerStatus.STOPPED: ("■", "dim"),
        RunnerStatus.CRASHED: ("⚠", "red"),
        RunnerStatus.COMPLETED: ("✓", "green"),
    }

    return badge_map.get(status, ("?", "white"))
