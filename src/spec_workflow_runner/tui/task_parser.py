"""Task parser for reading and parsing tasks.md files.

This module parses tasks.md files following the tasks-template.md format.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class TaskStatus(Enum):
    """Status of a task."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


@dataclass
class Task:
    """Represents a single task from tasks.md."""

    id: str  # Task number (e.g., "1", "4.2")
    title: str  # Task title
    status: TaskStatus  # Task status
    description: list[str]  # Task description lines (indented bullets)

    @property
    def display_title(self) -> str:
        """Get display-ready task title."""
        return f"{self.id}. {self.title}"


def parse_tasks_file(file_path: Path) -> tuple[list[Task], list[str]]:
    """Parse tasks.md file and extract tasks.

    Args:
        file_path: Path to tasks.md file

    Returns:
        Tuple of (task_list, warnings)
        - task_list: List of parsed Task objects
        - warnings: List of warning messages about format issues
    """
    if not file_path.exists():
        return [], [f"File not found: {file_path}"]

    tasks: list[Task] = []
    warnings: list[str] = []

    try:
        content = file_path.read_text(encoding="utf-8")
        lines = content.splitlines()

        # Pattern for task line: - [ ] 1. Task title or - [x] 4.2 Task title
        task_pattern = re.compile(r"^-\s+\[([ x\-])\]\s+(\d+(?:\.\d+)?)\.\s+(.+)$")

        current_task: Task | None = None

        for line_num, line in enumerate(lines, start=1):
            # Check for task header
            match = task_pattern.match(line)
            if match:
                # Save previous task if exists
                if current_task:
                    tasks.append(current_task)

                # Parse new task
                status_char = match.group(1)
                task_id = match.group(2)
                task_title = match.group(3)

                # Map status character to enum
                if status_char == "x":
                    status = TaskStatus.COMPLETED
                elif status_char == "-":
                    status = TaskStatus.IN_PROGRESS
                else:  # space
                    status = TaskStatus.PENDING

                current_task = Task(
                    id=task_id, title=task_title, status=status, description=[]
                )

            elif current_task and line.strip().startswith("-"):
                # This is a description line for the current task
                current_task.description.append(line.strip())

        # Don't forget the last task
        if current_task:
            tasks.append(current_task)

        # Validate format
        if not tasks:
            warnings.append("No tasks found in file. Expected format: '- [ ] 1. Task title'")

    except Exception as err:
        warnings.append(f"Error parsing file: {err}")

    return tasks, warnings
