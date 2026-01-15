"""TaskFixer orchestrator for coordinating the fix process."""

from __future__ import annotations

import os
import platform
import subprocess
from dataclasses import dataclass
from pathlib import Path

from ..providers import Provider
from .diff_generator import DiffGenerator, DiffResult
from .file_writer import FileWriter, WriteResult
from .prompt_builder import PromptBuilder, PromptContext
from .validator import TaskValidator, ValidationResult


@dataclass(frozen=True)
class FixResult:
    """Result of attempting to fix a tasks.md file."""

    success: bool
    original_validation: ValidationResult
    fixed_validation: ValidationResult | None
    diff_result: DiffResult | None
    write_result: WriteResult | None
    fixed_content: str | None = None
    error_message: str | None = None

    @property
    def has_changes(self) -> bool:
        """Check if any changes were made."""
        return self.diff_result is not None and self.diff_result.has_changes


class TaskFixer:
    """Orchestrates the task fixing process with dependency injection."""

    def __init__(
        self,
        provider: Provider,
        validator: TaskValidator,
        prompt_builder: PromptBuilder,
        diff_generator: DiffGenerator,
        file_writer: FileWriter,
        subprocess_timeout: int = 120,
    ) -> None:
        """Initialize the TaskFixer with all dependencies.

        Args:
            provider: AI provider for Claude execution
            validator: Task validator
            prompt_builder: Prompt builder
            diff_generator: Diff generator
            file_writer: File writer
            subprocess_timeout: Timeout for subprocess calls in seconds (default: 120)
        """
        self._provider = provider
        self._validator = validator
        self._prompt_builder = prompt_builder
        self._diff_generator = diff_generator
        self._file_writer = file_writer
        self._subprocess_timeout = subprocess_timeout

    def fix_tasks_file(
        self,
        file_path: Path,
        project_path: Path,
    ) -> FixResult:
        """Fix a tasks.md file by validating, prompting Claude, and generating a diff.

        This method orchestrates the full fix flow:
        1. Validate the file
        2. If invalid, build prompt and call Claude
        3. Validate the fixed content
        4. Generate diff
        5. Return FixResult (does NOT write the file)

        Args:
            file_path: Path to tasks.md file to fix
            project_path: Path to project root

        Returns:
            FixResult with validation, diff, and any errors
        """
        # Step 1: Validate the file
        original_validation = self._validator.validate_file(file_path)

        # If file is already valid, return early
        if original_validation.is_valid:
            return FixResult(
                success=True,
                original_validation=original_validation,
                fixed_validation=None,
                diff_result=None,
                write_result=None,
                fixed_content=None,
            )

        # Step 2: Read the malformed content
        try:
            malformed_content = file_path.read_text(encoding="utf-8")
        except Exception as err:
            return FixResult(
                success=False,
                original_validation=original_validation,
                fixed_validation=None,
                diff_result=None,
                write_result=None,
                fixed_content=None,
                error_message=f"Failed to read file: {err}",
            )

        # Step 3: Build prompt for Claude
        try:
            context = PromptContext(
                template_content="",  # Will be loaded by prompt builder
                malformed_content=malformed_content,
                validation_result=original_validation,
            )
            prompt = self._prompt_builder.build_prompt(context)
        except Exception as err:
            return FixResult(
                success=False,
                original_validation=original_validation,
                fixed_validation=None,
                diff_result=None,
                write_result=None,
                fixed_content=None,
                error_message=f"Failed to build prompt: {err}",
            )

        # Step 4: Call Claude to fix the content
        try:
            command = self._provider.build_command(
                prompt=prompt,
                project_path=project_path,
                config_overrides=(),
            )

            # Clear Claude-specific env vars to avoid nested Claude Code session conflicts
            env = os.environ.copy()
            for key in list(env.keys()):
                if key.startswith("CLAUDE") or key.startswith("CLAUDE_"):
                    del env[key]

            result = subprocess.run(
                command.to_list(),
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='replace',
                timeout=self._subprocess_timeout,
                cwd=project_path,
                env=env,
                shell=(platform.system() == "Windows"),
            )

            if result.returncode != 0:
                return FixResult(
                    success=False,
                    original_validation=original_validation,
                    fixed_validation=None,
                    diff_result=None,
                    write_result=None,
                    fixed_content=None,
                    error_message=f"Claude command failed: {result.stderr}",
                )

            fixed_content = result.stdout.strip()

        except subprocess.TimeoutExpired:
            return FixResult(
                success=False,
                original_validation=original_validation,
                fixed_validation=None,
                diff_result=None,
                write_result=None,
                fixed_content=None,
                error_message=f"Claude command timed out after {self._subprocess_timeout}s",
            )
        except Exception as err:
            return FixResult(
                success=False,
                original_validation=original_validation,
                fixed_validation=None,
                diff_result=None,
                write_result=None,
                fixed_content=None,
                error_message=f"Failed to execute Claude: {err}",
            )

        # Step 5: Validate the fixed content
        # Write to a temp file for validation
        temp_file = file_path.parent / f".{file_path.name}.tmp_validation"
        try:
            temp_file.write_text(fixed_content, encoding="utf-8")
            fixed_validation = self._validator.validate_file(temp_file)
        except Exception as err:
            return FixResult(
                success=False,
                original_validation=original_validation,
                fixed_validation=None,
                diff_result=None,
                write_result=None,
                fixed_content=None,
                error_message=f"Failed to validate fixed content: {err}",
            )
        finally:
            temp_file.unlink(missing_ok=True)

        # Step 6: Generate diff
        diff_result = self._diff_generator.generate_diff(
            original_content=malformed_content,
            fixed_content=fixed_content,
            original_label=str(file_path),
            fixed_label=f"{file_path} (fixed)",
        )

        return FixResult(
            success=True,
            original_validation=original_validation,
            fixed_validation=fixed_validation,
            diff_result=diff_result,
            write_result=None,
            fixed_content=fixed_content,
        )

    def apply_fix(self, file_path: Path, fixed_content: str) -> WriteResult:
        """Apply the fix by writing the fixed content to the file.

        Args:
            file_path: Path to file to write
            fixed_content: Fixed content to write

        Returns:
            WriteResult from FileWriter
        """
        return self._file_writer.write_with_backup(file_path, fixed_content)
