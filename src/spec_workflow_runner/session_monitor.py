"""Monitor Claude session activity in real-time by tailing session JSONL files."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import TextIO


def get_claude_sessions_dir(project_path: Path) -> Path:
    """Get the Claude sessions directory for a project.

    Args:
        project_path: Path to project directory

    Returns:
        Path to Claude sessions directory for this project
    """
    # Convert project path to Claude's format: C:\Users\... -> C--Users-...
    # Use resolve() to get absolute path and normalize it
    abs_path = project_path.resolve()

    # Convert to string and normalize separators
    path_str = str(abs_path)

    # Replace drive letter colon and all separators with dashes
    # Example: C:\Users\ryosu\repos\keyrx -> C--Users-ryosu-repos-keyrx
    normalized = path_str.replace(":", "").replace("\\", "-").replace("/", "-")

    claude_dir = Path.home() / ".claude" / "projects" / normalized
    return claude_dir


def get_latest_session_file(sessions_dir: Path) -> Path | None:
    """Get the most recently modified session JSONL file.

    Args:
        sessions_dir: Claude sessions directory

    Returns:
        Path to latest session file, or None if not found
    """
    if not sessions_dir.exists():
        return None

    # Find all .jsonl files (excluding sessions-index.json)
    session_files = [
        f for f in sessions_dir.glob("*.jsonl")
        if f.name != "sessions-index.json"
    ]

    if not session_files:
        return None

    # Return the most recently modified
    return max(session_files, key=lambda f: f.stat().st_mtime)


def format_session_update(line: str) -> str | None:
    """Parse and format a session JSONL line for display.

    Args:
        line: JSONL line from session file

    Returns:
        Formatted string to display, or None to skip
    """
    try:
        data = json.loads(line)
        msg_type = data.get("type")
        timestamp = data.get("timestamp", "")

        # Extract time portion (HH:MM:SS)
        time_str = timestamp.split("T")[1].split(".")[0] if "T" in timestamp else ""

        if msg_type == "assistant":
            message = data.get("message", {})
            content = message.get("content", [])

            for item in content:
                item_type = item.get("type")

                if item_type == "thinking":
                    thinking = item.get("thinking", "")
                    # Show first 150 chars of thinking
                    preview = thinking[:150].replace("\n", " ")
                    if len(thinking) > 150:
                        preview += "..."
                    return f"[{time_str}] 🤔 Thinking: {preview}"

                elif item_type == "tool_use":
                    tool_name = item.get("name", "unknown")
                    return f"[{time_str}] 🔧 Using tool: {tool_name}"

                elif item_type == "text":
                    text = item.get("text", "")
                    preview = text[:100].replace("\n", " ")
                    if len(text) > 100:
                        preview += "..."
                    return f"[{time_str}] 💬 Response: {preview}"

        elif msg_type == "user":
            # Skip user messages in automated mode
            return None

        elif msg_type == "tool_result":
            # Show tool results
            tool_use_id = data.get("toolUseId", "")
            return f"[{time_str}] ✅ Tool completed"

    except (json.JSONDecodeError, KeyError, AttributeError):
        # Skip malformed lines
        pass

    return None


class SessionMonitor:
    """Monitor Claude session activity in real-time."""

    def __init__(self, project_path: Path) -> None:
        """Initialize session monitor.

        Args:
            project_path: Path to project directory
        """
        self.project_path = project_path
        self.sessions_dir = get_claude_sessions_dir(project_path)
        self.session_file: Path | None = None
        self.file_handle: TextIO | None = None
        self.last_activity_time = time.time()
        self.last_file_size = 0

    def start(self, wait_seconds: int = 10) -> bool:
        """Start monitoring the latest session file.

        Args:
            wait_seconds: Seconds to wait for session file to be created

        Returns:
            True if session file found and opened, False otherwise
        """
        # Wait for session file to be created (Claude creates it after starting)
        start_time = time.time()
        while time.time() - start_time < wait_seconds:
            self.session_file = get_latest_session_file(self.sessions_dir)

            if self.session_file:
                # Check if file was created recently (within last 30 seconds)
                file_age = time.time() - self.session_file.stat().st_mtime
                if file_age < 30:
                    break

            time.sleep(0.5)

        if not self.session_file:
            return False

        try:
            # Open file and seek to end
            self.file_handle = self.session_file.open("r", encoding="utf-8")
            self.file_handle.seek(0, os.SEEK_END)
            self.last_file_size = self.file_handle.tell()
            self.last_activity_time = time.time()
            return True
        except Exception:
            return False

    def check_activity(self) -> tuple[bool, list[str]]:
        """Check for new session activity.

        Returns:
            Tuple of (has_activity, updates) where updates is list of formatted strings
        """
        if not self.file_handle or not self.session_file:
            return False, []

        try:
            # Check if file has grown
            current_size = self.session_file.stat().st_size

            if current_size <= self.last_file_size:
                # No new data
                return False, []

            # Read new lines
            new_lines = []
            for line in self.file_handle:
                new_lines.append(line.strip())

            self.last_file_size = current_size

            if new_lines:
                self.last_activity_time = time.time()

                # Format updates
                updates = []
                for line in new_lines:
                    formatted = format_session_update(line)
                    if formatted:
                        updates.append(formatted)

                return True, updates

            return False, []

        except Exception:
            return False, []

    def get_seconds_since_activity(self) -> float:
        """Get seconds since last session activity.

        Returns:
            Seconds since last activity
        """
        return time.time() - self.last_activity_time

    def close(self) -> None:
        """Close the session file handle."""
        if self.file_handle:
            try:
                self.file_handle.close()
            except Exception:
                pass
            self.file_handle = None
