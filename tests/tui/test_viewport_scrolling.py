"""Integration tests for viewport scrolling."""

from pathlib import Path

from spec_workflow_runner.tui.models import ProjectState, SpecState
from spec_workflow_runner.tui.views.tree_view import TreeViewport, render_tree


class TestViewportRendering:
    """Test viewport-based rendering of tree view."""

    def test_viewport_with_no_limit(self):
        """Test that viewport without limit renders all items."""
        projects = [
            ProjectState(
                path=Path("/test/proj1"),
                name="project1",
                specs=[
                    SpecState(
                        name="spec1",
                        path=Path("/test/proj1/spec1"),
                        total_tasks=5,
                        completed_tasks=2,
                        in_progress_tasks=1,
                        pending_tasks=2,
                    ),
                ],
            ),
        ]

        tree, viewport = render_tree(
            projects=projects,
            selected_project_index=None,
            selected_spec_index=None,
            viewport_offset=0,
            viewport_limit=None,
        )

        assert isinstance(viewport, TreeViewport)
        assert viewport.total_lines == 2  # 1 project + 1 spec
        assert viewport.visible_lines == 2
        assert viewport.hidden_above == 0
        assert viewport.hidden_below == 0

    def test_viewport_with_offset(self):
        """Test viewport with offset skips initial items."""
        projects = [
            ProjectState(
                path=Path(f"/test/proj{i}"),
                name=f"project{i}",
                specs=[
                    SpecState(
                        name=f"spec{i}",
                        path=Path(f"/test/proj{i}/spec{i}"),
                        total_tasks=5,
                        completed_tasks=2,
                        in_progress_tasks=1,
                        pending_tasks=2,
                    ),
                ],
            )
            for i in range(5)
        ]

        # Render with offset=3 (skip first 3 lines)
        tree, viewport = render_tree(
            projects=projects,
            selected_project_index=None,
            selected_spec_index=None,
            viewport_offset=3,
            viewport_limit=None,
            collapsed_projects=set(),  # All expanded
        )

        assert viewport.total_lines == 10  # 5 projects + 5 specs
        assert viewport.offset == 3
        assert viewport.hidden_above == 3
        # Should render from line 3 onwards
        assert viewport.visible_lines < viewport.total_lines

    def test_viewport_with_limit(self):
        """Test viewport with limit restricts rendered items."""
        projects = [
            ProjectState(
                path=Path(f"/test/proj{i}"),
                name=f"project{i}",
                specs=[
                    SpecState(
                        name=f"spec{i}",
                        path=Path(f"/test/proj{i}/spec{i}"),
                        total_tasks=5,
                        completed_tasks=2,
                        in_progress_tasks=1,
                        pending_tasks=2,
                    ),
                ],
            )
            for i in range(10)
        ]

        # Render with limit=5 (only show 5 lines)
        tree, viewport = render_tree(
            projects=projects,
            selected_project_index=None,
            selected_spec_index=None,
            viewport_offset=0,
            viewport_limit=5,
            collapsed_projects=set(),  # All expanded
        )

        assert viewport.total_lines == 20  # 10 projects + 10 specs
        assert viewport.visible_lines <= 5 + 1  # 5 items + scroll indicator
        assert viewport.hidden_below > 0

    def test_viewport_with_offset_and_limit(self):
        """Test viewport with both offset and limit (scrolling window)."""
        projects = [
            ProjectState(
                path=Path(f"/test/proj{i}"),
                name=f"project{i}",
                specs=[
                    SpecState(
                        name=f"spec{i}",
                        path=Path(f"/test/proj{i}/spec{i}"),
                        total_tasks=5,
                        completed_tasks=2,
                        in_progress_tasks=1,
                        pending_tasks=2,
                    ),
                ],
            )
            for i in range(20)
        ]

        # Render middle section (offset=10, limit=10)
        tree, viewport = render_tree(
            projects=projects,
            selected_project_index=None,
            selected_spec_index=None,
            viewport_offset=10,
            viewport_limit=10,
            collapsed_projects=set(),  # All expanded
        )

        assert viewport.total_lines == 40  # 20 projects + 20 specs
        assert viewport.offset == 10
        assert viewport.hidden_above == 10
        assert viewport.hidden_below > 0
        # Should show scroll indicators
        assert viewport.visible_lines <= 10 + 2  # items + 2 indicators

    def test_viewport_scroll_indicators_shown(self):
        """Test that scroll indicators appear when content is clipped."""
        projects = [
            ProjectState(
                path=Path(f"/test/proj{i}"),
                name=f"project{i}",
                specs=[
                    SpecState(
                        name=f"spec{i}",
                        path=Path(f"/test/proj{i}/spec{i}"),
                        total_tasks=5,
                        completed_tasks=2,
                        in_progress_tasks=1,
                        pending_tasks=2,
                    ),
                ],
            )
            for i in range(50)
        ]

        # Render middle section (collapsed to only show projects)
        tree, viewport = render_tree(
            projects=projects,
            selected_project_index=None,
            selected_spec_index=None,
            viewport_offset=10,
            viewport_limit=10,
            collapsed_projects=set(range(50)),  # Collapse all
        )

        # Check that indicators are reflected in metadata
        assert viewport.hidden_above > 0
        assert viewport.hidden_below > 0

    def test_viewport_with_collapsed_projects(self):
        """Test viewport calculations with collapsed projects."""
        projects = [
            ProjectState(
                path=Path(f"/test/proj{i}"),
                name=f"project{i}",
                specs=[
                    SpecState(
                        name=f"spec{i}-{j}",
                        path=Path(f"/test/proj{i}/spec{j}"),
                        total_tasks=5,
                        completed_tasks=2,
                        in_progress_tasks=1,
                        pending_tasks=2,
                    )
                    for j in range(5)
                ],
            )
            for i in range(10)
        ]

        # Render with some projects collapsed
        tree, viewport = render_tree(
            projects=projects,
            selected_project_index=None,
            selected_spec_index=None,
            viewport_offset=0,
            viewport_limit=None,
            collapsed_projects={0, 2, 4, 6, 8},  # Collapse every other project
        )

        # Collapsed projects: 5 projects * 1 line = 5 lines
        # Expanded projects: 5 projects * (1 + 5 specs) = 30 lines
        # Total: 35 lines
        assert viewport.total_lines == 35

    def test_viewport_empty_projects(self):
        """Test viewport with no projects."""
        tree, viewport = render_tree(
            projects=[],
            selected_project_index=None,
            selected_spec_index=None,
            viewport_offset=0,
            viewport_limit=10,
        )

        assert viewport.total_lines == 0
        assert viewport.visible_lines == 0
        assert viewport.hidden_above == 0
        assert viewport.hidden_below == 0


class TestViewportAutoScroll:
    """Test viewport auto-scroll behavior."""

    def test_selected_item_in_viewport(self):
        """Test that selected item is included in viewport."""
        projects = [
            ProjectState(
                path=Path(f"/test/proj{i}"),
                name=f"project{i}",
                specs=[
                    SpecState(
                        name=f"spec{i}",
                        path=Path(f"/test/proj{i}/spec{i}"),
                        total_tasks=5,
                        completed_tasks=2,
                        in_progress_tasks=1,
                        pending_tasks=2,
                    ),
                ],
            )
            for i in range(30)
        ]

        # Select item near the end (index 25)
        # Viewport should auto-scroll to show it
        selected_line = 25 * 2  # Each project + spec = 2 lines, select project 25
        viewport_size = 10

        # Calculate offset to center selected item
        ideal_offset = max(0, selected_line - (viewport_size // 2))

        tree, viewport = render_tree(
            projects=projects,
            selected_project_index=25,
            selected_spec_index=None,
            viewport_offset=ideal_offset,
            viewport_limit=viewport_size,
            collapsed_projects=set(),
        )

        # Selected item should be within viewport
        selected_visible = (
            selected_line >= viewport.offset
            and selected_line < viewport.offset + viewport.visible_lines
        )
        assert selected_visible or viewport.visible_lines == viewport.total_lines
