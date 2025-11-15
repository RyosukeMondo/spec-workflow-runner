from __future__ import annotations

from pathlib import Path

from spec_workflow_runner.utils import read_task_stats


def write_tasks(tmp_path: Path, content: str) -> Path:
    path = tmp_path / "tasks.md"
    path.write_text(content, encoding="utf-8")
    return path


def test_read_task_stats_counts_states(tmp_path):
    tasks_path = write_tasks(
        tmp_path,
        """
        [ ] Pending task
        [x] Completed task
        [-] In progress
        """,
    )

    stats = read_task_stats(tasks_path)

    assert stats.pending == 1
    assert stats.done == 1
    assert stats.in_progress == 1
    assert stats.total == 3
