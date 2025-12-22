"""Unit tests for log viewer component."""

import tempfile
from pathlib import Path

from rich.panel import Panel
from rich.text import Text

from spec_workflow_runner.tui.views.log_viewer import LogViewer


class TestLogViewerInit:
    """Tests for LogViewer initialization."""

    def test_default_initialization(self):
        """Test LogViewer initializes with defaults."""
        viewer = LogViewer()
        assert viewer.max_lines == 200
        assert viewer.log_path is None
        assert viewer.offset == 0
        assert viewer.auto_scroll is True
        assert len(viewer.lines) == 0

    def test_custom_max_lines(self):
        """Test LogViewer with custom max_lines."""
        viewer = LogViewer(max_lines=50)
        assert viewer.max_lines == 50

    def test_lines_property(self):
        """Test that lines property returns list."""
        viewer = LogViewer()
        assert isinstance(viewer.lines, list)
        assert len(viewer.lines) == 0


class TestUpdateLogPath:
    """Tests for update_log_path method."""

    def test_update_to_new_path(self):
        """Test updating to a new log path."""
        viewer = LogViewer()
        new_path = Path("/test/log.txt")
        viewer.update_log_path(new_path)
        assert viewer.log_path == new_path
        assert viewer.offset == 0
        assert len(viewer.lines) == 0

    def test_update_to_same_path_no_reset(self):
        """Test updating to same path doesn't reset state."""
        viewer = LogViewer()
        path = Path("/test/log.txt")
        viewer.update_log_path(path)
        viewer.offset = 100
        viewer._lines.append("test line")

        # Update to same path - should not reset
        viewer.update_log_path(path)
        assert viewer.offset == 100
        assert len(viewer.lines) == 1

    def test_update_to_different_path_resets(self):
        """Test updating to different path resets state."""
        viewer = LogViewer()
        viewer.update_log_path(Path("/test/log1.txt"))
        viewer.offset = 100
        viewer._lines.append("test line")

        # Update to different path - should reset
        viewer.update_log_path(Path("/test/log2.txt"))
        assert viewer.offset == 0
        assert len(viewer.lines) == 0

    def test_update_to_none(self):
        """Test updating to None clears state."""
        viewer = LogViewer()
        viewer.update_log_path(Path("/test/log.txt"))
        viewer.offset = 100
        viewer._lines.append("test line")

        viewer.update_log_path(None)
        assert viewer.log_path is None
        assert viewer.offset == 0
        assert len(viewer.lines) == 0


class TestPoll:
    """Tests for poll method."""

    def test_poll_with_no_path(self):
        """Test polling when no log path is set."""
        viewer = LogViewer()
        viewer.poll()
        assert viewer.offset == 0
        assert len(viewer.lines) == 0

    def test_poll_with_nonexistent_file(self):
        """Test polling when log file doesn't exist."""
        viewer = LogViewer()
        viewer.update_log_path(Path("/nonexistent/log.txt"))
        viewer.poll()
        assert viewer.offset == 0
        assert len(viewer.lines) == 0

    def test_poll_reads_new_content(self):
        """Test polling reads new content from file."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".log") as f:
            f.write("line 1\nline 2\nline 3\n")
            f.flush()
            temp_path = Path(f.name)

        try:
            viewer = LogViewer()
            viewer.update_log_path(temp_path)
            viewer.poll()

            assert len(viewer.lines) == 3
            assert viewer.lines[0] == "line 1"
            assert viewer.lines[1] == "line 2"
            assert viewer.lines[2] == "line 3"
            assert viewer.offset > 0
        finally:
            temp_path.unlink()

    def test_poll_incremental_reads(self):
        """Test polling reads only new content incrementally."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".log") as f:
            f.write("line 1\n")
            f.flush()
            temp_path = Path(f.name)

        try:
            viewer = LogViewer()
            viewer.update_log_path(temp_path)
            viewer.poll()
            assert len(viewer.lines) == 1
            first_offset = viewer.offset

            # Append more content
            with temp_path.open("a") as f:
                f.write("line 2\nline 3\n")

            viewer.poll()
            assert len(viewer.lines) == 3
            assert viewer.offset > first_offset
            assert viewer.lines[0] == "line 1"
            assert viewer.lines[1] == "line 2"
            assert viewer.lines[2] == "line 3"
        finally:
            temp_path.unlink()

    def test_poll_handles_log_rotation(self):
        """Test polling detects and handles log rotation."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".log") as f:
            f.write("line 1\nline 2\n")
            f.flush()
            temp_path = Path(f.name)

        try:
            viewer = LogViewer()
            viewer.update_log_path(temp_path)
            viewer.poll()
            assert len(viewer.lines) == 2

            # Simulate rotation: write new smaller file
            with temp_path.open("w") as f:
                f.write("new line 1\n")

            viewer.poll()
            # Should detect rotation and reset
            assert viewer.offset > 0
            # Lines should be reset and new content read
            assert "new line 1" in viewer.lines
        finally:
            temp_path.unlink()

    def test_poll_respects_max_lines(self):
        """Test polling respects max_lines buffer limit."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".log") as f:
            for i in range(250):
                f.write(f"line {i}\n")
            f.flush()
            temp_path = Path(f.name)

        try:
            viewer = LogViewer(max_lines=100)
            viewer.update_log_path(temp_path)
            viewer.poll()

            # Should only keep last 100 lines
            assert len(viewer.lines) == 100
            # Should have the newest lines (150-249)
            assert "line 249" in viewer.lines
            assert "line 150" in viewer.lines
            assert "line 0" not in viewer.lines
        finally:
            temp_path.unlink()

    def test_poll_handles_unicode(self):
        """Test polling handles unicode content correctly."""
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", delete=False, suffix=".log"
        ) as f:
            f.write("Hello 世界\n")
            f.write("Привет мир\n")
            f.flush()
            temp_path = Path(f.name)

        try:
            viewer = LogViewer()
            viewer.update_log_path(temp_path)
            viewer.poll()

            assert len(viewer.lines) == 2
            assert viewer.lines[0] == "Hello 世界"
            assert viewer.lines[1] == "Привет мир"
        finally:
            temp_path.unlink()

    def test_poll_handles_empty_file(self):
        """Test polling handles empty log file."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".log") as f:
            temp_path = Path(f.name)

        try:
            viewer = LogViewer()
            viewer.update_log_path(temp_path)
            viewer.poll()

            assert len(viewer.lines) == 0
            assert viewer.offset == 0
        finally:
            temp_path.unlink()

    def test_poll_continues_after_read_error(self):
        """Test polling handles read errors gracefully."""
        viewer = LogViewer()
        # Set path to a file that exists but will fail to read
        viewer.update_log_path(Path("/dev/null"))
        viewer.poll()
        # Should not crash, just log warning


class TestRenderPanel:
    """Tests for render_panel method."""

    def test_render_with_no_path(self):
        """Test rendering when no log path is set."""
        viewer = LogViewer()
        panel = viewer.render_panel()

        assert isinstance(panel, Panel)
        assert panel.title == "Logs"
        assert isinstance(panel.renderable, Text)
        assert "Waiting for logs" in str(panel.renderable)

    def test_render_with_empty_log(self):
        """Test rendering with empty log file."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".log") as f:
            temp_path = Path(f.name)

        try:
            viewer = LogViewer()
            viewer.update_log_path(temp_path)
            viewer.poll()
            panel = viewer.render_panel()

            assert isinstance(panel, Panel)
            assert temp_path.name in panel.title
        finally:
            temp_path.unlink()

    def test_render_with_content(self):
        """Test rendering with log content."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".log") as f:
            f.write("line 1\nline 2\nline 3\n")
            f.flush()
            temp_path = Path(f.name)

        try:
            viewer = LogViewer()
            viewer.update_log_path(temp_path)
            viewer.poll()
            panel = viewer.render_panel()

            assert isinstance(panel, Panel)
            assert temp_path.name in panel.title
            assert isinstance(panel.renderable, Text)
            content = str(panel.renderable)
            assert "line 1" in content
            assert "line 2" in content
            assert "line 3" in content
        finally:
            temp_path.unlink()

    def test_render_auto_scroll_indicator(self):
        """Test that auto-scroll indicator appears in title."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".log") as f:
            f.write("test\n")
            f.flush()
            temp_path = Path(f.name)

        try:
            viewer = LogViewer()
            viewer.update_log_path(temp_path)
            viewer.poll()

            # Test with auto_scroll enabled
            panel = viewer.render_panel(auto_scroll=True)
            assert "[Auto]" in panel.title

            # Test with auto_scroll disabled
            panel = viewer.render_panel(auto_scroll=False)
            assert "[Manual]" in panel.title

            # Test with default (should use instance value)
            viewer.auto_scroll = True
            panel = viewer.render_panel()
            assert "[Auto]" in panel.title
        finally:
            temp_path.unlink()

    def test_render_uses_instance_auto_scroll_default(self):
        """Test that render_panel uses instance auto_scroll when not specified."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".log") as f:
            f.write("test\n")
            f.flush()
            temp_path = Path(f.name)

        try:
            viewer = LogViewer()
            viewer.update_log_path(temp_path)
            viewer.poll()

            viewer.auto_scroll = False
            panel = viewer.render_panel()
            assert "[Manual]" in panel.title

            viewer.auto_scroll = True
            panel = viewer.render_panel()
            assert "[Auto]" in panel.title
        finally:
            temp_path.unlink()

    def test_render_preserves_ansi_colors(self):
        """Test that ANSI color codes are preserved in rendering."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".log") as f:
            # Write ANSI colored text
            f.write("\033[32mGreen text\033[0m\n")
            f.write("\033[31mRed text\033[0m\n")
            f.flush()
            temp_path = Path(f.name)

        try:
            viewer = LogViewer()
            viewer.update_log_path(temp_path)
            viewer.poll()
            panel = viewer.render_panel()

            assert isinstance(panel, Panel)
            # ANSI codes should be preserved in the text
            content = str(panel.renderable)
            assert "Green text" in content or "\033[32m" in content
        finally:
            temp_path.unlink()

    def test_render_panel_border_style(self):
        """Test that panel has correct border style."""
        viewer = LogViewer()
        panel = viewer.render_panel()
        assert panel.border_style == "blue"

    def test_render_nonexistent_file_shows_waiting(self):
        """Test rendering when log file path is set but doesn't exist."""
        viewer = LogViewer()
        viewer.update_log_path(Path("/nonexistent/log.txt"))
        panel = viewer.render_panel()

        assert isinstance(panel, Panel)
        assert "Waiting for logs" in str(panel.renderable)


class TestLineBuffering:
    """Tests for line buffering behavior."""

    def test_buffer_maintains_sliding_window(self):
        """Test that buffer maintains only last N lines."""
        viewer = LogViewer(max_lines=5)
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".log") as f:
            for i in range(10):
                f.write(f"line {i}\n")
            f.flush()
            temp_path = Path(f.name)

        try:
            viewer.update_log_path(temp_path)
            viewer.poll()

            # Should only have last 5 lines
            assert len(viewer.lines) == 5
            assert viewer.lines[0] == "line 5"
            assert viewer.lines[4] == "line 9"
        finally:
            temp_path.unlink()

    def test_buffer_handles_incremental_overflow(self):
        """Test buffer handles overflow across multiple polls."""
        viewer = LogViewer(max_lines=3)
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".log") as f:
            f.write("line 0\nline 1\n")
            f.flush()
            temp_path = Path(f.name)

        try:
            viewer.update_log_path(temp_path)
            viewer.poll()
            assert len(viewer.lines) == 2

            # Add more lines
            with temp_path.open("a") as f:
                f.write("line 2\nline 3\nline 4\n")

            viewer.poll()
            # Should only keep last 3
            assert len(viewer.lines) == 3
            assert viewer.lines[0] == "line 2"
            assert viewer.lines[2] == "line 4"
        finally:
            temp_path.unlink()


class TestEdgeCases:
    """Tests for edge cases and error conditions."""

    def test_poll_with_file_deleted_during_read(self):
        """Test handling file deletion during operation."""
        viewer = LogViewer()
        viewer.update_log_path(Path("/tmp/will-be-deleted.log"))
        viewer.poll()
        # Should handle gracefully

    def test_multiple_polls_without_changes(self):
        """Test multiple polls when file hasn't changed."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".log") as f:
            f.write("line 1\n")
            f.flush()
            temp_path = Path(f.name)

        try:
            viewer = LogViewer()
            viewer.update_log_path(temp_path)
            viewer.poll()
            first_count = len(viewer.lines)

            # Poll again without changes
            viewer.poll()
            assert len(viewer.lines) == first_count
        finally:
            temp_path.unlink()

    def test_viewer_with_max_lines_zero(self):
        """Test viewer with max_lines=0."""
        viewer = LogViewer(max_lines=0)
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".log") as f:
            f.write("line 1\nline 2\n")
            f.flush()
            temp_path = Path(f.name)

        try:
            viewer.update_log_path(temp_path)
            viewer.poll()
            # With max_lines=0, deque should keep nothing
            assert len(viewer.lines) == 0
        finally:
            temp_path.unlink()

    def test_lines_without_trailing_newline(self):
        """Test handling file without trailing newline."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".log") as f:
            f.write("line 1\nline 2")  # No trailing newline
            f.flush()
            temp_path = Path(f.name)

        try:
            viewer = LogViewer()
            viewer.update_log_path(temp_path)
            viewer.poll()

            assert len(viewer.lines) == 2
            assert viewer.lines[0] == "line 1"
            assert viewer.lines[1] == "line 2"
        finally:
            temp_path.unlink()
