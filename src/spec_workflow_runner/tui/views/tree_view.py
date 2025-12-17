"""Tree view renderer for project/spec hierarchy.

This module provides the render_tree function that builds a Rich Tree
component from ProjectState data, showing projects and specs with status
badges and task completion ratios.
"""

from __future__ import annotations

from rich.text import Text
from rich.tree import Tree

from ..state import ProjectState, RunnerStatus, SpecState


def _get_status_badge(spec: SpecState) -> tuple[str, str]:
    """Get status badge emoji and color for a spec.

    Args:
        spec: Spec state to get badge for

    Returns:
        Tuple of (emoji, color) for the spec's status
    """
    # Check runner status first
    if spec.runner:
        if spec.runner.status == RunnerStatus.RUNNING:
            return ("▶", "yellow")
        elif spec.runner.status == RunnerStatus.CRASHED:
            return ("⚠", "red")
        elif spec.runner.status == RunnerStatus.COMPLETED:
            return ("✓", "green")

    # Check task completion
    if spec.is_complete:
        return ("✓", "green")

    # Default for in-progress or pending
    return ("", "dim")


def _matches_filter(text: str, filter_text: str) -> bool:
    """Check if text matches filter (case-insensitive).

    Args:
        text: Text to search in
        filter_text: Filter string to search for

    Returns:
        True if filter_text is found in text (case-insensitive)
    """
    if not filter_text:
        return True
    return filter_text.lower() in text.lower()


def render_tree(
    projects: list[ProjectState],
    selected_project_index: int | None,
    selected_spec_index: int | None,
    filter_text: str = "",
    show_unfinished_only: bool = False,
) -> Tree:
    """Build Rich Tree from ProjectState list with status badges and selection.

    Args:
        projects: List of project states to render
        selected_project_index: Index of selected project, or None
        selected_spec_index: Index of selected spec within selected project, or None
        filter_text: Filter string for project/spec names (case-insensitive)
        show_unfinished_only: If True, only show specs with unfinished tasks

    Returns:
        Rich Tree component ready for rendering
    """
    # Create root tree
    tree = Tree("📁 Projects", guide_style="dim")

    # Track visible project index for selection mapping
    visible_project_idx = 0

    for project_idx, project in enumerate(projects):
        # Apply filter to project name
        if not _matches_filter(project.name, filter_text):
            # Check if any specs match before skipping project
            matching_specs = [
                spec for spec in project.specs
                if _matches_filter(spec.name, filter_text)
            ]
            if not matching_specs:
                continue

        # Filter specs if needed
        visible_specs = project.specs
        if show_unfinished_only:
            visible_specs = [s for s in visible_specs if s.has_unfinished_tasks]
        if filter_text:
            visible_specs = [s for s in visible_specs if _matches_filter(s.name, filter_text)]

        # Skip project if no visible specs
        if not visible_specs:
            continue

        # Build project label
        spec_count = len(visible_specs)
        project_label = f"[bold]{project.name}[/bold] [dim]({spec_count} specs)[/dim]"

        # Highlight if selected
        is_selected_project = selected_project_index == visible_project_idx
        if is_selected_project and selected_spec_index is None:
            project_label = f"[reverse]{project_label}[/reverse]"

        # Add project node
        project_node = tree.add(project_label)

        # Track visible spec index for selection mapping
        visible_spec_idx = 0

        # Add spec children
        for spec_idx, spec in enumerate(project.specs):
            # Apply filters
            if show_unfinished_only and not spec.has_unfinished_tasks:
                continue
            if filter_text and not _matches_filter(spec.name, filter_text):
                continue

            # Get status badge
            badge_emoji, badge_color = _get_status_badge(spec)

            # Build spec label
            task_ratio = f"{spec.completed_tasks}/{spec.total_tasks}"
            spec_label_parts = []

            # Add badge if present
            if badge_emoji:
                spec_label_parts.append(f"[{badge_color}]{badge_emoji}[/{badge_color}]")

            # Add spec name and task ratio
            spec_label_parts.append(spec.name)
            spec_label_parts.append(f"[dim]({task_ratio} tasks)[/dim]")

            spec_label = " ".join(spec_label_parts)

            # Highlight if selected
            is_selected_spec = (
                is_selected_project and selected_spec_index == visible_spec_idx
            )
            if is_selected_spec:
                spec_label = f"[reverse]{spec_label}[/reverse]"

            # Add spec node
            project_node.add(spec_label)

            visible_spec_idx += 1

        visible_project_idx += 1

    return tree
