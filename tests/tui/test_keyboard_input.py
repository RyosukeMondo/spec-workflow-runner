"""Tests for keyboard input handling."""

from __future__ import annotations

import io
import select
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

from spec_workflow_runner.tui.app import TUIApp
from spec_workflow_runner.utils import Config


@pytest.fixture
def config():
    """Create mock config."""
    cfg = MagicMock(spec=Config)
    cfg.repos_root = Path("/tmp/repos")
    cfg.cache_dir = Path("/tmp/cache")
    cfg.codex_command = ["codex"]
    cfg.spec_workflow_dir_name = ".spec-workflow"
    cfg.specs_subdir = "specs"
    cfg.tasks_filename = "tasks.md"
    cfg.log_dir_name = "logs"
    cfg.tui_log_tail_lines = 200
    cfg.tui_min_terminal_cols = 80
    cfg.tui_min_terminal_rows = 24
    return cfg


@pytest.fixture
def tui_app(config):
    """Create TUI app instance."""
    config_path = Path("/tmp/config.json")
    return TUIApp(config, config_path)


class TestArrowKeyHandling:
    """Test arrow key escape sequence handling."""

    def test_poll_keyboard_handles_up_arrow(self, tui_app):
        """Test that up arrow escape sequence is recognized."""
        with patch('select.select') as mock_select, \
             patch('sys.stdin') as mock_stdin:

            # Simulate stdin having data available
            mock_select.side_effect = [
                ([mock_stdin], [], []),  # First char available
                ([mock_stdin], [], []),  # Second char available
                ([mock_stdin], [], []),  # Third char available
            ]

            # Simulate reading escape sequence for up arrow: \x1b[A
            mock_stdin.read.side_effect = ['\x1b', '[', 'A']

            key = tui_app._poll_keyboard(timeout=0.1)
            assert key == 'up'

    def test_poll_keyboard_handles_down_arrow(self, tui_app):
        """Test that down arrow escape sequence is recognized."""
        with patch('select.select') as mock_select, \
             patch('sys.stdin') as mock_stdin:

            mock_select.side_effect = [
                ([mock_stdin], [], []),
                ([mock_stdin], [], []),
                ([mock_stdin], [], []),
            ]

            # Simulate reading escape sequence for down arrow: \x1b[B
            mock_stdin.read.side_effect = ['\x1b', '[', 'B']

            key = tui_app._poll_keyboard(timeout=0.1)
            assert key == 'down'

    def test_poll_keyboard_handles_left_arrow(self, tui_app):
        """Test that left arrow escape sequence is recognized."""
        with patch('select.select') as mock_select, \
             patch('sys.stdin') as mock_stdin:

            mock_select.side_effect = [
                ([mock_stdin], [], []),
                ([mock_stdin], [], []),
                ([mock_stdin], [], []),
            ]

            # Simulate reading escape sequence for left arrow: \x1b[D
            mock_stdin.read.side_effect = ['\x1b', '[', 'D']

            key = tui_app._poll_keyboard(timeout=0.1)
            assert key == 'left'

    def test_poll_keyboard_handles_right_arrow(self, tui_app):
        """Test that right arrow escape sequence is recognized."""
        with patch('select.select') as mock_select, \
             patch('sys.stdin') as mock_stdin:

            mock_select.side_effect = [
                ([mock_stdin], [], []),
                ([mock_stdin], [], []),
                ([mock_stdin], [], []),
            ]

            # Simulate reading escape sequence for right arrow: \x1b[C
            mock_stdin.read.side_effect = ['\x1b', '[', 'C']

            key = tui_app._poll_keyboard(timeout=0.1)
            assert key == 'right'

    def test_poll_keyboard_handles_plain_escape(self, tui_app):
        """Test that plain ESC key is recognized when not part of sequence."""
        with patch('select.select') as mock_select, \
             patch('sys.stdin') as mock_stdin:

            # First call: stdin has data (ESC char)
            # Second call: no more data (not an escape sequence)
            mock_select.side_effect = [
                ([mock_stdin], [], []),
                ([], [], []),  # No more chars
            ]

            mock_stdin.read.side_effect = ['\x1b']

            key = tui_app._poll_keyboard(timeout=0.1)
            assert key == '\x1b'

    def test_poll_keyboard_handles_regular_char(self, tui_app):
        """Test that regular characters are returned as-is."""
        with patch('select.select') as mock_select, \
             patch('sys.stdin') as mock_stdin:

            mock_select.return_value = ([mock_stdin], [], [])
            mock_stdin.read.return_value = 'a'

            key = tui_app._poll_keyboard(timeout=0.1)
            assert key == 'a'

    def test_poll_keyboard_timeout_returns_none(self, tui_app):
        """Test that timeout with no input returns None."""
        with patch('select.select') as mock_select:
            # No data available
            mock_select.return_value = ([], [], [])

            key = tui_app._poll_keyboard(timeout=0.1)
            assert key is None

    def test_poll_keyboard_handles_read_error(self, tui_app):
        """Test that read errors are handled gracefully."""
        with patch('select.select') as mock_select, \
             patch('sys.stdin') as mock_stdin:

            mock_select.return_value = ([mock_stdin], [], [])
            mock_stdin.read.side_effect = IOError("Read error")

            key = tui_app._poll_keyboard(timeout=0.1)
            assert key is None
