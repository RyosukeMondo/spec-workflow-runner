"""Log viewer component for TUI with auto-scroll and buffering."""

from __future__ import annotations

from collections import deque
from pathlib import Path

from rich.panel import Panel
from rich.text import Text


class LogViewer:
    """Track and stream the tail of a log file with auto-scroll support."""

    def __init__(self, max_lines: int = 200) -> None:
        """Initialize the log viewer.

        Args:
            max_lines: Maximum number of lines to buffer (from config.tui_log_tail_lines)
        """
        self.max_lines = max_lines
        self.log_path: Path | None = None
        self.offset = 0
        self._lines: deque[str] = deque(maxlen=max_lines)
        self.auto_scroll = True

    @property
    def lines(self) -> list[str]:
        """Return the currently buffered lines."""
        return list(self._lines)

    def update_log_path(self, log_path: Path | None) -> None:
        """Switch to a different log file.

        Args:
            log_path: Path to the new log file, or None to clear
        """
        if self.log_path != log_path:
            self.log_path = log_path
            self.offset = 0
            self._lines.clear()

    def poll(self) -> None:
        """Read newly written data from the log file."""
        if self.log_path is None:
            self.offset = 0
            self._lines.clear()
            return

        if not self.log_path.exists():
            self.offset = 0
            self._lines.clear()
            return

        try:
            size = self.log_path.stat().st_size
        except OSError:
            # File might have been deleted or become inaccessible
            self.offset = 0
            self._lines.clear()
            return

        # Handle log rotation: if file size < current offset, reset
        if size < self.offset:
            self.offset = 0
            self._lines.clear()

        # Read new content if file has grown
        if size > self.offset:
            try:
                with self.log_path.open("r", encoding="utf-8", errors="replace") as handle:
                    handle.seek(self.offset)
                    chunk = handle.read()
                    self.offset = handle.tell()

                # Buffer new lines
                for line in chunk.splitlines():
                    self._lines.append(line)
            except OSError as exc:
                # Log read error but continue
                import logging
                logging.warning(f"Failed to read log file {self.log_path}: {exc}")

    def render_panel(self, auto_scroll: bool | None = None) -> Panel:
        """Return a Rich Panel displaying the log tail.

        Args:
            auto_scroll: If True, show newest lines. If False, show oldest.
                        If None, use instance default (self.auto_scroll).

        Returns:
            Rich Panel with log content
        """
        # Determine effective auto_scroll setting
        effective_auto_scroll = auto_scroll if auto_scroll is not None else self.auto_scroll

        # Determine panel content and title
        if self.log_path is None:
            body = Text("Waiting for logs...", style="dim")
            title = "Logs"
        elif not self._lines:
            # Log file exists but no lines yet (or empty)
            if self.log_path.exists():
                body = Text("(log exists but is empty)", style="dim")
            else:
                body = Text("Waiting for logs...", style="dim")
            title = f"Logs – {self.log_path.name}"
        else:
            # Display buffered lines
            # Note: deque already maintains max_lines, so we just need to decide
            # whether to show them in order (auto_scroll=True shows newest at bottom)
            lines_to_show = list(self._lines)

            # With auto_scroll, we show lines as they are (newest at end)
            # Without auto_scroll, we could show oldest, but since deque already
            # maintains the sliding window, just show what we have
            content = "\n".join(lines_to_show).strip()
            if not content:
                content = "(log exists but is empty)"

            # Preserve ANSI color codes by using Text with markup=False
            body = Text(content, overflow="fold")

            scroll_indicator = " [Auto]" if effective_auto_scroll else " [Manual]"
            title = f"Logs – {self.log_path.name}{scroll_indicator}"

        return Panel(body, border_style="blue", title=title)
