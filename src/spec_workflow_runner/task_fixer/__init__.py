"""Task auto-fix module for spec-workflow-runner.

This module provides functionality to automatically detect and fix format errors
in tasks.md files using Claude AI.
"""

from __future__ import annotations

from pathlib import Path

from ..providers import Provider
from .diff_generator import DiffGenerator, DiffResult
from .file_writer import FileWriter, WriteResult
from .fixer import FixResult, TaskFixer
from .prompt_builder import PromptBuilder
from .validator import TaskValidator, ValidationResult

__all__ = [
    "create_task_fixer",
    "TaskFixer",
    "FixResult",
    "ValidationResult",
    "DiffResult",
    "WriteResult",
]


def create_task_fixer(
    provider: Provider,
    project_path: Path,
    template_path: Path | None = None,
) -> TaskFixer:
    """Factory function to create a TaskFixer with all dependencies.

    Args:
        provider: AI provider (ClaudeProvider, GeminiProvider, etc.)
        project_path: Path to project root
        template_path: Optional custom template path (defaults to .spec-workflow/templates/tasks-template.md)

    Returns:
        Fully initialized TaskFixer instance

    Example:
        >>> from spec_workflow_runner.providers import ClaudeProvider
        >>> from pathlib import Path
        >>>
        >>> provider = ClaudeProvider(model="sonnet")
        >>> project_path = Path("/path/to/project")
        >>> fixer = create_task_fixer(provider, project_path)
        >>> result = fixer.fix_tasks_file(
        ...     project_path / ".spec-workflow/specs/my-spec/tasks.md",
        ...     project_path
        ... )
    """
    # Resolve template path
    if template_path is None:
        template_path = project_path / ".spec-workflow" / "templates" / "tasks-template.md"

    # Create all dependencies
    validator = TaskValidator()
    prompt_builder = PromptBuilder(template_path)
    diff_generator = DiffGenerator(context_lines=3)
    file_writer = FileWriter()

    # Create and return TaskFixer with all dependencies
    return TaskFixer(
        provider=provider,
        validator=validator,
        prompt_builder=prompt_builder,
        diff_generator=diff_generator,
        file_writer=file_writer,
        subprocess_timeout=120,
    )
