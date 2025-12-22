"""Tests for footer bar rendering."""

from __future__ import annotations

from rich.text import Text

from spec_workflow_runner.tui.views.footer_bar import _truncate_text, render_footer_bar


class TestTruncateText:
    """Tests for text truncation helper."""

    def test_short_text_no_truncation(self) -> None:
        """Short text should not be truncated."""
        result = _truncate_text("hello", 10)
        assert result == "hello"

    def test_exact_length_no_truncation(self) -> None:
        """Text exactly at max_length should not be truncated."""
        result = _truncate_text("hello", 5)
        assert result == "hello"

    def test_long_text_truncated(self) -> None:
        """Long text should be truncated with ellipsis."""
        result = _truncate_text("hello world", 8)
        assert result == "hello..."
        assert len(result) == 8

    def test_very_short_max_length_3(self) -> None:
        """Max length of 3 should return only ellipsis."""
        result = _truncate_text("hello", 3)
        assert result == "..."

    def test_very_short_max_length_2(self) -> None:
        """Max length of 2 should return truncated ellipsis."""
        result = _truncate_text("hello", 2)
        assert result == ".."

    def test_very_short_max_length_1(self) -> None:
        """Max length of 1 should return single dot."""
        result = _truncate_text("hello", 1)
        assert result == "."

    def test_very_short_max_length_0(self) -> None:
        """Max length of 0 should return empty string."""
        result = _truncate_text("hello", 0)
        assert result == ""

    def test_empty_text(self) -> None:
        """Empty text should remain empty."""
        result = _truncate_text("", 10)
        assert result == ""


class TestRenderFooterBar:
    """Tests for footer bar rendering."""

    def test_no_runners_no_error(self) -> None:
        """Render footer with no active runners and no error."""
        footer = render_footer_bar(active_runner_count=0)

        assert isinstance(footer, Text)
        text_str = footer.plain
        assert "No runners active" in text_str
        assert "Press ? for help" in text_str

    def test_single_runner_active(self) -> None:
        """Render footer with one active runner."""
        footer = render_footer_bar(active_runner_count=1)

        text_str = footer.plain
        assert "1 runner active" in text_str
        assert "runners" not in text_str  # Should be singular
        assert "Press ? for help" in text_str

    def test_multiple_runners_active(self) -> None:
        """Render footer with multiple active runners."""
        footer = render_footer_bar(active_runner_count=5)

        text_str = footer.plain
        assert "5 runners active" in text_str
        assert "Press ? for help" in text_str

    def test_with_error_message(self) -> None:
        """Render footer with error message."""
        footer = render_footer_bar(
            active_runner_count=2,
            error_message="Connection failed",
        )

        text_str = footer.plain
        assert "2 runners active" in text_str
        assert "Connection failed" in text_str
        assert "Press ? for help" in text_str

    def test_with_long_error_message(self) -> None:
        """Render footer with long error that needs truncation."""
        long_error = "This is a very long error message that will definitely need to be truncated for display"
        footer = render_footer_bar(
            active_runner_count=1,
            error_message=long_error,
            terminal_width=80,
        )

        text_str = footer.plain
        assert "1 runner active" in text_str
        # Error should be truncated
        assert "..." in text_str
        assert len(text_str) <= 80
        assert "Press ? for help" in text_str

    def test_with_very_narrow_terminal(self) -> None:
        """Render footer with narrow terminal."""
        footer = render_footer_bar(
            active_runner_count=1,
            error_message="Error message",
            terminal_width=40,
        )

        text_str = footer.plain
        # Should still show essential info
        assert "runner" in text_str.lower()
        assert "help" in text_str.lower()

    def test_error_too_short_space_omitted(self) -> None:
        """Error message omitted if not enough space."""
        footer = render_footer_bar(
            active_runner_count=10,
            error_message="This error won't fit",
            terminal_width=35,  # Very narrow
        )

        text_str = footer.plain
        assert "10 runners active" in text_str
        assert "Press ? for help" in text_str
        # Error might be omitted if space < 10 chars

    def test_no_error_message_none(self) -> None:
        """None error message should be handled gracefully."""
        footer = render_footer_bar(
            active_runner_count=3,
            error_message=None,
        )

        text_str = footer.plain
        assert "3 runners active" in text_str
        assert "Press ? for help" in text_str
        # Should not contain error-related text

    def test_default_terminal_width(self) -> None:
        """Default terminal width should be 80."""
        footer = render_footer_bar(active_runner_count=0)

        # Should render without errors
        assert isinstance(footer, Text)
        assert "Press ? for help" in footer.plain

    def test_zero_runners_with_error(self) -> None:
        """Render with no runners but with error."""
        footer = render_footer_bar(
            active_runner_count=0,
            error_message="Initialization failed",
        )

        text_str = footer.plain
        assert "No runners active" in text_str
        assert "Initialization failed" in text_str

    def test_returns_rich_text_object(self) -> None:
        """Verify return type is Rich Text."""
        footer = render_footer_bar(active_runner_count=1)
        assert isinstance(footer, Text)

    def test_has_styled_components(self) -> None:
        """Verify that footer contains styled spans."""
        footer = render_footer_bar(active_runner_count=1, error_message="Error")

        # Rich Text with styles will have spans
        assert len(footer.spans) > 0

    def test_with_status_message(self) -> None:
        """Render footer with status message."""
        footer = render_footer_bar(
            active_runner_count=2,
            status_message="Runner started successfully",
        )

        text_str = footer.plain
        assert "2 runners active" in text_str
        assert "Runner started successfully" in text_str
        assert "Press ? for help" in text_str

    def test_error_takes_priority_over_status(self) -> None:
        """Error message should take priority over status message."""
        footer = render_footer_bar(
            active_runner_count=1,
            error_message="Error: Failed to start",
            status_message="This should not appear",
        )

        text_str = footer.plain
        assert "Error: Failed to start" in text_str
        assert "This should not appear" not in text_str
        assert "Press ? for help" in text_str

    def test_status_message_truncated(self) -> None:
        """Long status message should be truncated."""
        long_status = (
            "This is a very long status message that will need to be truncated for display"
        )
        footer = render_footer_bar(
            active_runner_count=1,
            status_message=long_status,
            terminal_width=80,
        )

        text_str = footer.plain
        assert "1 runner active" in text_str
        # Status should be truncated
        assert "..." in text_str
        assert len(text_str) <= 80
        assert "Press ? for help" in text_str

    def test_status_message_none(self) -> None:
        """None status message should be handled gracefully."""
        footer = render_footer_bar(
            active_runner_count=1,
            status_message=None,
        )

        text_str = footer.plain
        assert "1 runner active" in text_str
        assert "Press ? for help" in text_str

    def test_last_key_parameter_accepted(self) -> None:
        """Last key parameter should be accepted (for debugging)."""
        footer = render_footer_bar(
            active_runner_count=1,
            last_key="s",
        )

        # Should render without errors
        assert isinstance(footer, Text)
        assert "Press ? for help" in footer.plain
