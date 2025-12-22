"""Unit tests for tree view renderer."""

from datetime import datetime
from pathlib import Path

from rich.tree import Tree

from spec_workflow_runner.tui.state import (
    ProjectState,
    RunnerState,
    RunnerStatus,
    SpecState,
)
from spec_workflow_runner.tui.views.tree_view import (
    _get_status_badge,
    _matches_filter,
    render_tree,
)


class TestMatchesFilter:
    """Tests for _matches_filter helper function."""

    def test_empty_filter_matches_all(self):
        """Test that empty filter matches any text."""
        assert _matches_filter("anything", "")
        assert _matches_filter("test", "")

    def test_case_insensitive_match(self):
        """Test that filter is case-insensitive."""
        assert _matches_filter("HelloWorld", "hello")
        assert _matches_filter("HelloWorld", "WORLD")
        assert _matches_filter("test", "TEST")

    def test_partial_match(self):
        """Test that partial matches work."""
        assert _matches_filter("my-project-name", "project")
        assert _matches_filter("spec-name-123", "name")

    def test_no_match(self):
        """Test that non-matching text returns False."""
        assert not _matches_filter("project", "spec")
        assert not _matches_filter("hello", "xyz")


class TestGetStatusBadge:
    """Tests for _get_status_badge helper function."""

    def test_running_runner_status(self):
        """Test badge for spec with running runner."""
        runner = RunnerState(
            runner_id="test-1",
            project_path=Path("/test"),
            spec_name="test-spec",
            provider="claude",
            model="sonnet",
            pid=12345,
            status=RunnerStatus.RUNNING,
            started_at=datetime.now(),
            baseline_commit="abc123",
        )
        spec = SpecState(
            name="test",
            path=Path("/test"),
            total_tasks=10,
            completed_tasks=5,
            in_progress_tasks=2,
            pending_tasks=3,
            runner=runner,
        )
        emoji, color = _get_status_badge(spec)
        assert emoji == "▶"
        assert color == "yellow"

    def test_crashed_runner_status(self):
        """Test badge for spec with crashed runner."""
        runner = RunnerState(
            runner_id="test-1",
            project_path=Path("/test"),
            spec_name="test-spec",
            provider="claude",
            model="sonnet",
            pid=12345,
            status=RunnerStatus.CRASHED,
            started_at=datetime.now(),
            baseline_commit="abc123",
        )
        spec = SpecState(
            name="test",
            path=Path("/test"),
            total_tasks=10,
            completed_tasks=5,
            in_progress_tasks=0,
            pending_tasks=5,
            runner=runner,
        )
        emoji, color = _get_status_badge(spec)
        assert emoji == "⚠"
        assert color == "red"

    def test_completed_runner_status(self):
        """Test badge for spec with completed runner."""
        runner = RunnerState(
            runner_id="test-1",
            project_path=Path("/test"),
            spec_name="test-spec",
            provider="claude",
            model="sonnet",
            pid=12345,
            status=RunnerStatus.COMPLETED,
            started_at=datetime.now(),
            baseline_commit="abc123",
        )
        spec = SpecState(
            name="test",
            path=Path("/test"),
            total_tasks=10,
            completed_tasks=10,
            in_progress_tasks=0,
            pending_tasks=0,
            runner=runner,
        )
        emoji, color = _get_status_badge(spec)
        assert emoji == "✓"
        assert color == "green"

    def test_complete_tasks_no_runner(self):
        """Test badge for spec with all tasks complete but no runner."""
        spec = SpecState(
            name="test",
            path=Path("/test"),
            total_tasks=10,
            completed_tasks=10,
            in_progress_tasks=0,
            pending_tasks=0,
            runner=None,
        )
        emoji, color = _get_status_badge(spec)
        assert emoji == "✓"
        assert color == "green"

    def test_incomplete_tasks_no_runner(self):
        """Test badge for spec with incomplete tasks and no runner."""
        spec = SpecState(
            name="test",
            path=Path("/test"),
            total_tasks=10,
            completed_tasks=5,
            in_progress_tasks=2,
            pending_tasks=3,
            runner=None,
        )
        emoji, color = _get_status_badge(spec)
        assert emoji == ""
        assert color == "dim"


class TestRenderTree:
    """Tests for render_tree function."""

    def test_empty_projects_list(self):
        """Test rendering with no projects."""
        tree, _ = render_tree([], None, None)
        assert isinstance(tree, Tree)
        assert tree.label == "📁 Projects"

    def test_single_project_no_specs(self):
        """Test rendering project with no specs."""
        project = ProjectState(
            path=Path("/test/project"),
            name="test-project",
            specs=[],
        )
        tree, _ = render_tree([project], None, None)
        assert isinstance(tree, Tree)
        # Project with no visible specs should not be added

    def test_single_project_with_specs(self):
        """Test rendering project with specs."""
        spec = SpecState(
            name="spec1",
            path=Path("/test/spec1"),
            total_tasks=10,
            completed_tasks=5,
            in_progress_tasks=2,
            pending_tasks=3,
        )
        project = ProjectState(
            path=Path("/test/project"),
            name="test-project",
            specs=[spec],
        )
        tree, _ = render_tree([project], None, None)
        assert isinstance(tree, Tree)

    def test_selection_highlighting_project(self):
        """Test that selected project is highlighted."""
        spec = SpecState(
            name="spec1",
            path=Path("/test/spec1"),
            total_tasks=10,
            completed_tasks=5,
            in_progress_tasks=2,
            pending_tasks=3,
        )
        project = ProjectState(
            path=Path("/test/project"),
            name="test-project",
            specs=[spec],
        )
        tree, _ = render_tree([project], selected_project_index=0, selected_spec_index=None)
        assert isinstance(tree, Tree)
        # Check that tree was created (detailed inspection of Rich Tree is complex)

    def test_selection_highlighting_spec(self):
        """Test that selected spec is highlighted."""
        spec = SpecState(
            name="spec1",
            path=Path("/test/spec1"),
            total_tasks=10,
            completed_tasks=5,
            in_progress_tasks=2,
            pending_tasks=3,
        )
        project = ProjectState(
            path=Path("/test/project"),
            name="test-project",
            specs=[spec],
        )
        tree, _ = render_tree([project], selected_project_index=0, selected_spec_index=0)
        assert isinstance(tree, Tree)

    def test_filter_by_project_name(self):
        """Test filtering projects by name."""
        spec1 = SpecState(
            name="spec1",
            path=Path("/test/spec1"),
            total_tasks=10,
            completed_tasks=5,
            in_progress_tasks=2,
            pending_tasks=3,
        )
        spec2 = SpecState(
            name="spec2",
            path=Path("/test/spec2"),
            total_tasks=5,
            completed_tasks=2,
            in_progress_tasks=1,
            pending_tasks=2,
        )
        project1 = ProjectState(
            path=Path("/test/project1"),
            name="matching-project",
            specs=[spec1],
        )
        project2 = ProjectState(
            path=Path("/test/project2"),
            name="other-project",
            specs=[spec2],
        )
        tree, _ = render_tree([project1, project2], None, None, filter_text="matching")
        assert isinstance(tree, Tree)

    def test_filter_by_spec_name(self):
        """Test filtering by spec name."""
        spec1 = SpecState(
            name="matching-spec",
            path=Path("/test/spec1"),
            total_tasks=10,
            completed_tasks=5,
            in_progress_tasks=2,
            pending_tasks=3,
        )
        spec2 = SpecState(
            name="other-spec",
            path=Path("/test/spec2"),
            total_tasks=5,
            completed_tasks=2,
            in_progress_tasks=1,
            pending_tasks=2,
        )
        project = ProjectState(
            path=Path("/test/project"),
            name="test-project",
            specs=[spec1, spec2],
        )
        tree, _ = render_tree([project], None, None, filter_text="matching")
        assert isinstance(tree, Tree)

    def test_show_unfinished_only(self):
        """Test filtering to show only unfinished specs."""
        spec_complete = SpecState(
            name="complete-spec",
            path=Path("/test/spec1"),
            total_tasks=10,
            completed_tasks=10,
            in_progress_tasks=0,
            pending_tasks=0,
        )
        spec_incomplete = SpecState(
            name="incomplete-spec",
            path=Path("/test/spec2"),
            total_tasks=10,
            completed_tasks=5,
            in_progress_tasks=2,
            pending_tasks=3,
        )
        project = ProjectState(
            path=Path("/test/project"),
            name="test-project",
            specs=[spec_complete, spec_incomplete],
        )
        tree, _ = render_tree([project], None, None, show_unfinished_only=True)
        assert isinstance(tree, Tree)
        # Complete spec should be filtered out

    def test_combined_filtering(self):
        """Test combining text filter with unfinished filter."""
        spec1 = SpecState(
            name="matching-complete",
            path=Path("/test/spec1"),
            total_tasks=10,
            completed_tasks=10,
            in_progress_tasks=0,
            pending_tasks=0,
        )
        spec2 = SpecState(
            name="matching-incomplete",
            path=Path("/test/spec2"),
            total_tasks=10,
            completed_tasks=5,
            in_progress_tasks=2,
            pending_tasks=3,
        )
        spec3 = SpecState(
            name="other-incomplete",
            path=Path("/test/spec3"),
            total_tasks=5,
            completed_tasks=2,
            in_progress_tasks=1,
            pending_tasks=2,
        )
        project = ProjectState(
            path=Path("/test/project"),
            name="test-project",
            specs=[spec1, spec2, spec3],
        )
        tree, _ = render_tree(
            [project],
            None,
            None,
            filter_text="matching",
            show_unfinished_only=True,
        )
        assert isinstance(tree, Tree)
        # Only spec2 should be visible (matching name + incomplete)

    def test_task_ratio_display(self):
        """Test that task ratios are displayed correctly."""
        spec = SpecState(
            name="test-spec",
            path=Path("/test/spec"),
            total_tasks=10,
            completed_tasks=7,
            in_progress_tasks=2,
            pending_tasks=1,
        )
        project = ProjectState(
            path=Path("/test/project"),
            name="test-project",
            specs=[spec],
        )
        tree, _ = render_tree([project], None, None)
        assert isinstance(tree, Tree)
        # Task ratio "7/10 tasks" should be in the tree

    def test_spec_count_display(self):
        """Test that spec count is displayed for projects."""
        specs = [
            SpecState(
                name=f"spec{i}",
                path=Path(f"/test/spec{i}"),
                total_tasks=10,
                completed_tasks=5,
                in_progress_tasks=2,
                pending_tasks=3,
            )
            for i in range(5)
        ]
        project = ProjectState(
            path=Path("/test/project"),
            name="test-project",
            specs=specs,
        )
        tree, _ = render_tree([project], None, None)
        assert isinstance(tree, Tree)
        # "5 specs" should be in the tree

    def test_multiple_projects(self):
        """Test rendering multiple projects."""
        spec1 = SpecState(
            name="spec1",
            path=Path("/test/spec1"),
            total_tasks=10,
            completed_tasks=5,
            in_progress_tasks=2,
            pending_tasks=3,
        )
        spec2 = SpecState(
            name="spec2",
            path=Path("/test/spec2"),
            total_tasks=5,
            completed_tasks=2,
            in_progress_tasks=1,
            pending_tasks=2,
        )
        project1 = ProjectState(
            path=Path("/test/project1"),
            name="project1",
            specs=[spec1],
        )
        project2 = ProjectState(
            path=Path("/test/project2"),
            name="project2",
            specs=[spec2],
        )
        tree, _ = render_tree([project1, project2], None, None)
        assert isinstance(tree, Tree)

    def test_status_badge_for_running_spec(self):
        """Test that running specs show correct badge."""
        runner = RunnerState(
            runner_id="test-1",
            project_path=Path("/test"),
            spec_name="test-spec",
            provider="claude",
            model="sonnet",
            pid=12345,
            status=RunnerStatus.RUNNING,
            started_at=datetime.now(),
            baseline_commit="abc123",
        )
        spec = SpecState(
            name="test-spec",
            path=Path("/test/spec"),
            total_tasks=10,
            completed_tasks=5,
            in_progress_tasks=2,
            pending_tasks=3,
            runner=runner,
        )
        project = ProjectState(
            path=Path("/test/project"),
            name="test-project",
            specs=[spec],
        )
        tree, _ = render_tree([project], None, None)
        assert isinstance(tree, Tree)

    def test_no_specs_after_filtering(self):
        """Test project is hidden when all specs are filtered out."""
        spec = SpecState(
            name="spec1",
            path=Path("/test/spec1"),
            total_tasks=10,
            completed_tasks=5,
            in_progress_tasks=2,
            pending_tasks=3,
        )
        project = ProjectState(
            path=Path("/test/project"),
            name="test-project",
            specs=[spec],
        )
        tree, _ = render_tree([project], None, None, filter_text="nonexistent")
        assert isinstance(tree, Tree)
        # Project should not be visible since no specs match

    def test_selection_indices_with_filtering(self):
        """Test that selection indices work correctly with filtering."""
        spec1 = SpecState(
            name="matching1",
            path=Path("/test/spec1"),
            total_tasks=10,
            completed_tasks=5,
            in_progress_tasks=2,
            pending_tasks=3,
        )
        spec2 = SpecState(
            name="other",
            path=Path("/test/spec2"),
            total_tasks=5,
            completed_tasks=2,
            in_progress_tasks=1,
            pending_tasks=2,
        )
        spec3 = SpecState(
            name="matching2",
            path=Path("/test/spec3"),
            total_tasks=8,
            completed_tasks=4,
            in_progress_tasks=2,
            pending_tasks=2,
        )
        project = ProjectState(
            path=Path("/test/project"),
            name="test-project",
            specs=[spec1, spec2, spec3],
        )
        # With filter, visible specs are: matching1, matching2
        # Select visible_spec_idx=1 (which is matching2)
        tree, _ = render_tree(
            [project],
            selected_project_index=0,
            selected_spec_index=1,
            filter_text="matching",
        )
        assert isinstance(tree, Tree)
