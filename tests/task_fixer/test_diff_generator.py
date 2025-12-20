"""Tests for diff generator module."""

from __future__ import annotations

import pytest

from spec_workflow_runner.task_fixer.diff_generator import DiffGenerator, DiffResult


@pytest.fixture
def diff_gen() -> DiffGenerator:
    """Create a DiffGenerator instance."""
    return DiffGenerator()


def test_identical_content_no_changes(diff_gen: DiffGenerator) -> None:
    """Test that identical content produces no changes."""
    content = "Line 1\nLine 2\nLine 3\n"

    result = diff_gen.generate_diff(content, content)

    assert not result.has_changes
    assert result.diff_text == ""
    assert result.lines_added == 0
    assert result.lines_removed == 0
    assert result.lines_modified == 0
    assert result.changes_summary == "No changes"


def test_addition_only(diff_gen: DiffGenerator) -> None:
    """Test diff with only additions."""
    original = "Line 1\nLine 2\n"
    fixed = "Line 1\nLine 2\nLine 3\n"

    result = diff_gen.generate_diff(original, fixed)

    assert result.has_changes
    assert result.lines_added == 1
    assert result.lines_removed == 0
    assert result.lines_modified == 0
    assert "+Line 3" in result.diff_text
    assert result.changes_summary == "+1 added"


def test_removal_only(diff_gen: DiffGenerator) -> None:
    """Test diff with only removals."""
    original = "Line 1\nLine 2\nLine 3\n"
    fixed = "Line 1\nLine 3\n"

    result = diff_gen.generate_diff(original, fixed)

    assert result.has_changes
    assert result.lines_added == 0
    assert result.lines_removed == 1
    assert result.lines_modified == 0
    assert "-Line 2" in result.diff_text
    assert result.changes_summary == "-1 removed"


def test_modification_only(diff_gen: DiffGenerator) -> None:
    """Test diff with modifications (paired additions and removals)."""
    original = "Line 1\nLine 2\nLine 3\n"
    fixed = "Line 1\nLine Two\nLine 3\n"

    result = diff_gen.generate_diff(original, fixed)

    assert result.has_changes
    assert result.lines_modified == 1
    assert "-Line 2" in result.diff_text
    assert "+Line Two" in result.diff_text
    assert result.changes_summary == "~1 modified"


def test_mixed_changes(diff_gen: DiffGenerator) -> None:
    """Test diff with additions, removals, and modifications."""
    original = "Line 1\nLine 2\nLine 3\nLine 4\n"
    fixed = "Line 1\nLine Two\nLine 3\nLine 5\nLine 6\n"

    result = diff_gen.generate_diff(original, fixed)

    assert result.has_changes
    # Should detect modifications and additions
    assert result.lines_added + result.lines_removed + result.lines_modified > 0
    assert "-Line 2" in result.diff_text or "~" in result.changes_summary
    assert "+Line 5" in result.diff_text or "+Line 6" in result.diff_text


def test_custom_context_lines(diff_gen: DiffGenerator) -> None:
    """Test that context lines parameter works."""
    gen_with_1_context = DiffGenerator(context_lines=1)

    original = "Line 1\nLine 2\nLine 3\nLine 4\nLine 5\n"
    fixed = "Line 1\nLine 2\nLine Three\nLine 4\nLine 5\n"

    result = gen_with_1_context.generate_diff(original, fixed)

    assert result.has_changes
    # With 1 context line, we should see fewer unchanged lines
    assert result.diff_text


def test_custom_labels(diff_gen: DiffGenerator) -> None:
    """Test custom labels appear in diff output."""
    original = "Line 1\n"
    fixed = "Line 2\n"

    result = diff_gen.generate_diff(
        original, fixed, original_label="before.md", fixed_label="after.md"
    )

    assert result.has_changes
    assert "before.md" in result.diff_text
    assert "after.md" in result.diff_text


def test_empty_to_content(diff_gen: DiffGenerator) -> None:
    """Test diff from empty to non-empty content."""
    original = ""
    fixed = "Line 1\nLine 2\n"

    result = diff_gen.generate_diff(original, fixed)

    assert result.has_changes
    assert result.lines_added == 2
    assert result.lines_removed == 0


def test_content_to_empty(diff_gen: DiffGenerator) -> None:
    """Test diff from content to empty."""
    original = "Line 1\nLine 2\n"
    fixed = ""

    result = diff_gen.generate_diff(original, fixed)

    assert result.has_changes
    assert result.lines_added == 0
    assert result.lines_removed == 2


def test_changes_summary_with_all_types(diff_gen: DiffGenerator) -> None:
    """Test changes summary includes all change types."""
    # Create a scenario with distinct additions and removals
    original = "A\nB\nC\nD\nE\n"
    fixed = "A\nB Modified\nC\nF\nG\nH\n"

    result = diff_gen.generate_diff(original, fixed)

    assert result.has_changes
    summary = result.changes_summary
    # Should have some combination of added/removed/modified
    assert any(marker in summary for marker in ["+", "-", "~"])


def test_multiline_content_with_no_trailing_newline(diff_gen: DiffGenerator) -> None:
    """Test diff handles content without trailing newlines."""
    original = "Line 1\nLine 2"
    fixed = "Line 1\nLine 3"

    result = diff_gen.generate_diff(original, fixed)

    assert result.has_changes
    assert result.lines_modified == 1


def test_large_diff_performance(diff_gen: DiffGenerator) -> None:
    """Test diff generator handles large files efficiently."""
    # Create large content
    original_lines = [f"Line {i}\n" for i in range(1000)]
    fixed_lines = original_lines.copy()
    # Modify every 10th line
    for i in range(0, 1000, 10):
        fixed_lines[i] = f"Modified Line {i}\n"

    original = "".join(original_lines)
    fixed = "".join(fixed_lines)

    result = diff_gen.generate_diff(original, fixed)

    assert result.has_changes
    # Should have 100 modifications
    assert result.lines_modified > 0


def test_diff_result_immutability() -> None:
    """Test that DiffResult is immutable."""
    result = DiffResult(
        diff_text="test",
        has_changes=True,
        lines_added=1,
        lines_removed=1,
        lines_modified=0,
    )

    # Should not be able to modify frozen dataclass
    with pytest.raises(AttributeError):
        result.has_changes = False  # type: ignore


@pytest.mark.parametrize(
    "lines_added,lines_removed,lines_modified,expected_summary",
    [
        (0, 0, 0, "No changes"),
        (1, 0, 0, "+1 added"),
        (0, 1, 0, "-1 removed"),
        (0, 0, 1, "~1 modified"),
        (1, 1, 0, "+1 added, -1 removed"),
        (1, 0, 1, "+1 added, ~1 modified"),
        (0, 1, 1, "-1 removed, ~1 modified"),
        (2, 3, 1, "+2 added, -3 removed, ~1 modified"),
    ],
)
def test_changes_summary_format(
    lines_added: int,
    lines_removed: int,
    lines_modified: int,
    expected_summary: str,
) -> None:
    """Test changes_summary property formatting."""
    result = DiffResult(
        diff_text="",
        has_changes=lines_added + lines_removed + lines_modified > 0,
        lines_added=lines_added,
        lines_removed=lines_removed,
        lines_modified=lines_modified,
    )

    assert result.changes_summary == expected_summary


def test_unicode_content(diff_gen: DiffGenerator) -> None:
    """Test diff handles unicode content correctly."""
    original = "Hello 世界\nLine 2\n"
    fixed = "Hello 世界\nLine Two\n"

    result = diff_gen.generate_diff(original, fixed)

    assert result.has_changes
    assert "世界" in result.diff_text


def test_whitespace_only_changes(diff_gen: DiffGenerator) -> None:
    """Test diff detects whitespace-only changes."""
    original = "Line 1\nLine 2\n"
    fixed = "Line 1 \nLine 2\n"  # Added trailing space

    result = diff_gen.generate_diff(original, fixed)

    assert result.has_changes
    assert result.lines_modified == 1
