"""Unit tests for TUI utility functions."""

import pytest
from spec_workflow_runner.tui.tui_utils import (
    RunnerStatus,
    format_duration,
    truncate_text,
    get_terminal_size,
    get_status_badge,
)


class TestFormatDuration:
    """Tests for format_duration function."""

    def test_zero_seconds(self):
        """Test zero seconds returns 00:00:00."""
        assert format_duration(0) == "00:00:00"

    def test_one_second(self):
        """Test one second returns 00:00:01."""
        assert format_duration(1) == "00:00:01"

    def test_one_minute(self):
        """Test one minute returns 00:01:00."""
        assert format_duration(60) == "00:01:00"

    def test_one_hour(self):
        """Test one hour returns 01:00:00."""
        assert format_duration(3600) == "01:00:00"

    def test_mixed_duration(self):
        """Test 1 hour, 1 minute, 1 second returns 01:01:01."""
        assert format_duration(3661) == "01:01:01"

    def test_large_duration(self):
        """Test large duration (24 hours) returns 24:00:00."""
        assert format_duration(86400) == "24:00:00"

    def test_very_large_duration(self):
        """Test very large duration (100 hours) formats correctly."""
        assert format_duration(360000) == "100:00:00"

    def test_fractional_seconds(self):
        """Test fractional seconds are rounded down."""
        assert format_duration(3661.9) == "01:01:01"

    def test_negative_seconds(self):
        """Test negative seconds are treated as zero."""
        assert format_duration(-10) == "00:00:00"


class TestTruncateText:
    """Tests for truncate_text function."""

    def test_short_text(self):
        """Test text shorter than max_len is returned as-is."""
        assert truncate_text("short", 10) == "short"

    def test_exact_length(self):
        """Test text exactly at max_len is returned as-is."""
        assert truncate_text("exactly10!", 10) == "exactly10!"

    def test_long_text(self):
        """Test long text is truncated with ellipsis."""
        assert truncate_text("this is a long text", 10) == "this is..."

    def test_max_len_three(self):
        """Test max_len of 3 returns only ellipsis."""
        assert truncate_text("hello", 3) == "..."

    def test_max_len_two(self):
        """Test max_len of 2 returns truncated ellipsis."""
        assert truncate_text("hello", 2) == ".."

    def test_max_len_one(self):
        """Test max_len of 1 returns single dot."""
        assert truncate_text("hello", 1) == "."

    def test_max_len_zero(self):
        """Test max_len of 0 returns empty string."""
        assert truncate_text("hello", 0) == ""

    def test_empty_text(self):
        """Test empty text returns empty string."""
        assert truncate_text("", 10) == ""

    def test_preserves_max_len(self):
        """Test truncated text never exceeds max_len."""
        result = truncate_text("a very long string that should be truncated", 15)
        assert len(result) == 15
        assert result == "a very long ..."


class TestGetTerminalSize:
    """Tests for get_terminal_size function."""

    def test_returns_tuple(self):
        """Test returns tuple of two integers."""
        cols, rows = get_terminal_size()
        assert isinstance(cols, int)
        assert isinstance(rows, int)

    def test_positive_values(self):
        """Test returns positive values."""
        cols, rows = get_terminal_size()
        assert cols > 0
        assert rows > 0

    def test_fallback_values(self):
        """Test returns reasonable fallback values."""
        cols, rows = get_terminal_size()
        # Should be at least the fallback values
        assert cols >= 80 or rows >= 24


class TestGetStatusBadge:
    """Tests for get_status_badge function."""

    def test_running_status(self):
        """Test RUNNING status returns play emoji and yellow color."""
        emoji, color = get_status_badge(RunnerStatus.RUNNING)
        assert emoji == "▶"
        assert color == "yellow"

    def test_stopped_status(self):
        """Test STOPPED status returns square emoji and dim color."""
        emoji, color = get_status_badge(RunnerStatus.STOPPED)
        assert emoji == "■"
        assert color == "dim"

    def test_crashed_status(self):
        """Test CRASHED status returns warning emoji and red color."""
        emoji, color = get_status_badge(RunnerStatus.CRASHED)
        assert emoji == "⚠"
        assert color == "red"

    def test_completed_status(self):
        """Test COMPLETED status returns checkmark emoji and green color."""
        emoji, color = get_status_badge(RunnerStatus.COMPLETED)
        assert emoji == "✓"
        assert color == "green"

    def test_all_statuses_mapped(self):
        """Test all RunnerStatus values have a badge mapping."""
        for status in RunnerStatus:
            emoji, color = get_status_badge(status)
            assert emoji is not None
            assert color is not None
            assert emoji != "?"  # Ensure not using default unknown badge


class TestRunnerStatus:
    """Tests for RunnerStatus enum."""

    def test_enum_values(self):
        """Test RunnerStatus has all required values."""
        assert hasattr(RunnerStatus, "RUNNING")
        assert hasattr(RunnerStatus, "STOPPED")
        assert hasattr(RunnerStatus, "CRASHED")
        assert hasattr(RunnerStatus, "COMPLETED")

    def test_enum_value_types(self):
        """Test RunnerStatus values are strings."""
        assert RunnerStatus.RUNNING.value == "running"
        assert RunnerStatus.STOPPED.value == "stopped"
        assert RunnerStatus.CRASHED.value == "crashed"
        assert RunnerStatus.COMPLETED.value == "completed"
