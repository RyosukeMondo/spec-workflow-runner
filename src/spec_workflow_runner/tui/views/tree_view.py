"""Tree view renderer for project/spec hierarchy.

This module provides the render_tree function that builds a Rich Tree
component from ProjectState data, showing projects and specs with status
badges and task completion ratios.
"""

from __future__ import annotations

from dataclasses import dataclass

from rich.tree import Tree

from ..state import ProjectState, RunnerStatus, SpecState


@dataclass
class TreeViewport:
    """Metadata about tree viewport for scrolling."""

    total_lines: int  # Total number of tree lines
    visible_lines: int  # Number of lines actually rendered
    offset: int  # First visible line index
    hidden_above: int  # Number of lines hidden above viewport
    hidden_below: int  # Number of lines hidden below viewport


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
    collapsed_projects: set[int] | None = None,
    viewport_offset: int = 0,
    viewport_limit: int | None = None,
) -> tuple[Tree, TreeViewport]:
    """Build Rich Tree from ProjectState list with status badges and selection.

    Args:
        projects: List of project states to render
        selected_project_index: Index of selected project, or None
        selected_spec_index: Index of selected spec within selected project, or None
        filter_text: Filter string for project/spec names (case-insensitive)
        show_unfinished_only: If True, only show specs with unfinished tasks
        collapsed_projects: Set of project indices that are collapsed
        viewport_offset: First visible line index (for scrolling)
        viewport_limit: Maximum lines to render (None = no limit)

    Returns:
        Tuple of (Rich Tree component, TreeViewport metadata)
    """
    if collapsed_projects is None:
        collapsed_projects = set()

    # Track line numbers for viewport
    current_line = 0
    total_lines = 0
    lines_rendered = 0

    # Create root tree with navigation hints
    tree = Tree("📁 Projects [dim](↑/↓ j/k: move · Enter: select · Space: collapse · g/G: top/bottom · /: filter)[/dim]", guide_style="dim")

    # Add scroll indicator at top if needed
    if viewport_offset > 0:
        tree.add(f"[dim]↑ {viewport_offset} more above[/dim]")
        lines_rendered += 1

    # Track visible project index for selection mapping
    visible_project_idx = 0

    for _project_idx, project in enumerate(projects):
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

        # Count this project line
        total_lines += 1

        # Check if this line is in viewport
        in_viewport = (current_line >= viewport_offset and
                      (viewport_limit is None or lines_rendered < viewport_limit))

        # Build project label with collapse indicator
        spec_count = len(visible_specs)
        total_specs = len(project.specs)
        completed_specs = sum(1 for s in project.specs if s.is_complete)
        is_collapsed = _project_idx in collapsed_projects
        collapse_indicator = "▶" if is_collapsed else "▼"
        project_label = f"{collapse_indicator} [dim]({completed_specs}/{total_specs})[/dim] [bold]{project.name}[/bold]"

        # Highlight if selected
        is_selected_project = selected_project_index == visible_project_idx
        if is_selected_project and selected_spec_index is None:
            project_label = f"[reverse]{project_label}[/reverse]"

        # Add project node only if in viewport
        if in_viewport:
            project_node = tree.add(project_label)
            lines_rendered += 1
        else:
            project_node = None

        current_line += 1

        # Track visible spec index for selection mapping
        visible_spec_idx = 0

        # Only show specs if project is not collapsed
        if not is_collapsed:
            # Add spec children
            for _spec_idx, spec in enumerate(project.specs):
                # Apply filters
                if show_unfinished_only and not spec.has_unfinished_tasks:
                    continue
                if filter_text and not _matches_filter(spec.name, filter_text):
                    continue

                # Count this spec line
                total_lines += 1

                # Check if this line is in viewport
                spec_in_viewport = (current_line >= viewport_offset and
                                   (viewport_limit is None or lines_rendered < viewport_limit))

                # Get status badge
                badge_emoji, badge_color = _get_status_badge(spec)

                # Build spec label
                task_ratio = f"{spec.completed_tasks}/{spec.total_tasks}"
                spec_label_parts = []

                # Add task ratio first (left side)
                spec_label_parts.append(f"[dim]({task_ratio})[/dim]")

                # Add badge if present
                if badge_emoji:
                    spec_label_parts.append(f"[{badge_color}]{badge_emoji}[/{badge_color}]")

                # Add spec name
                spec_label_parts.append(spec.name)

                spec_label = " ".join(spec_label_parts)

                # Highlight if selected
                is_selected_spec = (
                    is_selected_project and selected_spec_index == visible_spec_idx
                )
                if is_selected_spec:
                    spec_label = f"[reverse]{spec_label}[/reverse]"

                # Add spec node only if in viewport and parent project is rendered
                if spec_in_viewport and project_node is not None:
                    project_node.add(spec_label)
                    lines_rendered += 1

                current_line += 1
                visible_spec_idx += 1

        visible_project_idx += 1

    # Add scroll indicator at bottom if needed
    hidden_below = total_lines - (viewport_offset + lines_rendered - (1 if viewport_offset > 0 else 0))
    if viewport_limit is not None and hidden_below > 0:
        tree.add(f"[dim]↓ {hidden_below} more below[/dim]")

    # Build viewport metadata
    viewport = TreeViewport(
        total_lines=total_lines,
        visible_lines=lines_rendered,
        offset=viewport_offset,
        hidden_above=viewport_offset,
        hidden_below=max(0, hidden_below),
    )

    return tree, viewport
