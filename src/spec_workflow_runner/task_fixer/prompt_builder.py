"""Prompt builder for generating Claude prompts to fix tasks.md files."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .validator import ValidationResult


@dataclass(frozen=True)
class PromptContext:
    """Context for building a fix prompt."""

    template_content: str
    malformed_content: str
    validation_result: ValidationResult


class PromptBuilder:
    """Builds prompts for Claude to fix tasks.md format issues."""

    def __init__(self, template_path: Path) -> None:
        """Initialize the prompt builder.

        Args:
            template_path: Path to tasks-template.md file
        """
        self._template_path = template_path
        self._template_content: str | None = None

    def build_prompt(self, context: PromptContext) -> str:
        """Build a prompt for Claude to fix the tasks.md file.

        Args:
            context: PromptContext with template, malformed content, and validation issues

        Returns:
            Complete prompt string for Claude
        """
        template = self._load_template()

        # Build the prompt with all necessary context
        prompt_parts = [
            "You are a format correction assistant. Your task is to fix format errors in a tasks.md file.",
            "",
            "# INSTRUCTIONS",
            "",
            "1. Review the TEMPLATE FORMAT below to understand the correct format",
            "2. Review the VALIDATION ISSUES to understand what is wrong",
            "3. Review the MALFORMED CONTENT that needs to be fixed",
            "4. Output ONLY the corrected markdown content - no explanations, no code blocks, no extra text",
            "5. Preserve all task content and structure - only fix format issues",
            "",
            "# TEMPLATE FORMAT",
            "",
            "```markdown",
            template,
            "```",
            "",
            "# VALIDATION ISSUES",
            "",
            context.validation_result.error_summary,
            "",
            "# MALFORMED CONTENT",
            "",
            "```markdown",
            context.malformed_content,
            "```",
            "",
            "# YOUR TASK",
            "",
            "Output the corrected tasks.md content following the template format exactly.",
            "Fix all validation issues while preserving task information.",
            "Output ONLY markdown - no explanations, no code fences, just the corrected content.",
        ]

        return "\n".join(prompt_parts)

    def _load_template(self) -> str:
        """Load the template content, caching it after first load.

        Returns:
            Template content string

        Raises:
            FileNotFoundError: If template file doesn't exist
            OSError: If template file cannot be read
        """
        if self._template_content is None:
            if not self._template_path.exists():
                raise FileNotFoundError(f"Template not found: {self._template_path}")

            self._template_content = self._template_path.read_text(encoding="utf-8")

        return self._template_content
