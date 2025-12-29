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
- [ ] Pending task
- [x] Completed task
- [-] In progress
        """,
    )

    stats = read_task_stats(tasks_path)

    assert stats.pending == 1
    assert stats.done == 1
    assert stats.in_progress == 1
    assert stats.total == 3


def test_read_task_stats_is_case_insensitive(tmp_path):
    tasks_path = write_tasks(
        tmp_path,
        """
- [X] Uppercase done
- [x] lowercase done
        """,
    )

    stats = read_task_stats(tasks_path)

    assert stats.done == 2
    assert stats.pending == 0
    assert stats.in_progress == 0


def test_read_task_stats_ignores_non_task_checkboxes(tmp_path):
    tasks_path = write_tasks(
        tmp_path,
        """
Notes about format: [x] means done.
- [x] Actual task
        """,
    )

    stats = read_task_stats(tasks_path)

    assert stats.done == 1
    assert stats.total == 1


def test_read_task_stats_ignores_indented_checklist_items(tmp_path):
    """Indented checklist items (part of task descriptions) should not be counted as tasks."""
    tasks_path = write_tasks(
        tmp_path,
        """
- [x] 1. Main task with checklist
  - [ ] Checklist item 1 (should be ignored)
  - [ ] Checklist item 2 (should be ignored)
  - [x] Checklist item 3 (should be ignored)
- [ ] 2. Another main task
  - [ ] Another checklist item (should be ignored)
        """,
    )

    stats = read_task_stats(tasks_path)

    # Should only count 2 main tasks, not the 4 indented checklist items
    assert stats.done == 1
    assert stats.pending == 1
    assert stats.in_progress == 0
    assert stats.total == 2
