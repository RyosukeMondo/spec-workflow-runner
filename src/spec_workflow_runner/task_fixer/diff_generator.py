"""Diff generator for creating human-readable diffs of tasks.md changes."""

from __future__ import annotations

import difflib
from dataclasses import dataclass


@dataclass(frozen=True)
class DiffResult:
    """Result of generating a diff between original and fixed content."""

    diff_text: str
    has_changes: bool
    lines_added: int
    lines_removed: int
    lines_modified: int

    @property
    def changes_summary(self) -> str:
        """Get a human-readable summary of changes."""
        if not self.has_changes:
            return "No changes"

        parts = []
        if self.lines_added > 0:
            parts.append(f"+{self.lines_added} added")
        if self.lines_removed > 0:
            parts.append(f"-{self.lines_removed} removed")
        if self.lines_modified > 0:
            parts.append(f"~{self.lines_modified} modified")

        return ", ".join(parts)


class DiffGenerator:
    """Generates unified diffs for tasks.md content changes."""

    def __init__(self, context_lines: int = 3) -> None:
        """Initialize the diff generator.

        Args:
            context_lines: Number of context lines to show around changes (default: 3)
        """
        self._context_lines = context_lines

    def generate_diff(
        self,
        original_content: str,
        fixed_content: str,
        original_label: str = "original",
        fixed_label: str = "fixed",
    ) -> DiffResult:
        """Generate a unified diff between original and fixed content.

        Args:
            original_content: Original file content
            fixed_content: Fixed file content
            original_label: Label for original content in diff
            fixed_label: Label for fixed content in diff

        Returns:
            DiffResult containing diff text and change statistics
        """
        # Handle identical content
        if original_content == fixed_content:
            return DiffResult(
                diff_text="",
                has_changes=False,
                lines_added=0,
                lines_removed=0,
                lines_modified=0,
            )

        # Split into lines for difflib
        original_lines = original_content.splitlines(keepends=True)
        fixed_lines = fixed_content.splitlines(keepends=True)

        # Generate unified diff
        diff_lines = list(
            difflib.unified_diff(
                original_lines,
                fixed_lines,
                fromfile=original_label,
                tofile=fixed_label,
                n=self._context_lines,
            )
        )

        # Count changes
        lines_added = 0
        lines_removed = 0
        lines_modified = 0

        # Track modified lines by looking for pairs of - and +
        removed_indices: set[int] = set()
        added_indices: set[int] = set()

        for i, line in enumerate(diff_lines):
            if line.startswith("+++") or line.startswith("---") or line.startswith("@@"):
                continue

            if line.startswith("-"):
                lines_removed += 1
                removed_indices.add(i)
            elif line.startswith("+"):
                lines_added += 1
                added_indices.add(i)

        # Calculate modified lines (pairs of removed and added lines close together)
        # This is a heuristic: if we have similar numbers of + and - in a hunk,
        # they're likely modifications rather than pure additions/removals
        if lines_added > 0 and lines_removed > 0:
            # Simple heuristic: the smaller number represents modifications
            lines_modified = min(lines_added, lines_removed)
            lines_added -= lines_modified
            lines_removed -= lines_modified

        diff_text = "".join(diff_lines)

        return DiffResult(
            diff_text=diff_text,
            has_changes=True,
            lines_added=lines_added,
            lines_removed=lines_removed,
            lines_modified=lines_modified,
        )
