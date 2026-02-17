"""Tests for prompt builder module."""

from __future__ import annotations

from pathlib import Path

import pytest

from spec_workflow_runner.task_fixer.prompt_builder import PromptBuilder, PromptContext
from spec_workflow_runner.task_fixer.validator import (
    IssueType,
    ValidationIssue,
    ValidationResult,
)

TEMPLATE = "# Tasks\n\n- [ ] 1. First task\n- [ ] 2. Second task\n"
MALFORMED = "# Tasks\n\n- 1. Missing checkbox\n- [*] Invalid\n"

ISSUES = (
    ValidationIssue(
        issue_type=IssueType.MISSING_CHECKBOX,
        line_number=3,
        line_content="- 1. Missing checkbox",
        message="Line 3: Task line is missing valid checkbox",
    ),
    ValidationIssue(
        issue_type=IssueType.INVALID_CHECKBOX,
        line_number=4,
        line_content="- [*] Invalid",
        message="Line 4: Invalid checkbox character '*'",
    ),
)


@pytest.fixture
def template_file(tmp_path: Path) -> Path:
    path = tmp_path / "tasks-template.md"
    path.write_text(TEMPLATE, encoding="utf-8")
    return path


def _build(template_file: Path, *, malformed: str = MALFORMED, valid: bool = False) -> str:
    result = ValidationResult(is_valid=valid, issues=() if valid else ISSUES)
    context = PromptContext(
        template_content=TEMPLATE,
        malformed_content=malformed,
        validation_result=result,
    )
    return PromptBuilder(template_file).build_prompt(context)


class TestBuildPrompt:
    def test_contains_all_sections(self, template_file: Path) -> None:
        prompt = _build(template_file)
        for section in [
            "# INSTRUCTIONS",
            "# TEMPLATE FORMAT",
            "# VALIDATION ISSUES",
            "# MALFORMED CONTENT",
            "# YOUR TASK",
        ]:
            assert section in prompt

    def test_includes_template_and_malformed_content(self, template_file: Path) -> None:
        prompt = _build(template_file)
        assert TEMPLATE in prompt
        assert MALFORMED in prompt

    def test_includes_validation_error_summary(self, template_file: Path) -> None:
        result = ValidationResult(is_valid=False, issues=ISSUES)
        prompt = _build(template_file)
        assert result.error_summary in prompt

    def test_wraps_content_in_markdown_code_blocks(self, template_file: Path) -> None:
        prompt = _build(template_file)
        assert prompt.count("```markdown") == 2

    def test_output_instructions_specify_markdown_only(self, template_file: Path) -> None:
        prompt = _build(template_file)
        assert "Output ONLY the corrected markdown content" in prompt
        assert "ONLY markdown" in prompt

    def test_valid_result_still_builds_prompt(self, template_file: Path) -> None:
        prompt = _build(template_file, valid=True)
        assert "# VALIDATION ISSUES" in prompt
        assert "No validation issues found" in prompt

    def test_empty_malformed_content(self, template_file: Path) -> None:
        prompt = _build(template_file, malformed="")
        assert "# MALFORMED CONTENT" in prompt

    def test_preserves_newlines(self, template_file: Path) -> None:
        multi_line = "Line 1\n\nLine 2\nLine 3"
        prompt = _build(template_file, malformed=multi_line)
        assert multi_line in prompt


class TestTemplateLoading:
    def test_caches_template_across_calls(self, template_file: Path) -> None:
        builder = PromptBuilder(template_file)
        result = ValidationResult(is_valid=False, issues=ISSUES)
        ctx = PromptContext(TEMPLATE, MALFORMED, result)

        p1 = builder.build_prompt(ctx)
        template_file.unlink()  # delete file; cached copy should still work
        p2 = builder.build_prompt(ctx)
        assert p1 == p2

    def test_file_not_found_raises(self) -> None:
        builder = PromptBuilder(Path("/nonexistent/template.md"))
        result = ValidationResult(is_valid=False, issues=())
        ctx = PromptContext(TEMPLATE, MALFORMED, result)
        with pytest.raises(FileNotFoundError, match="Template not found"):
            builder.build_prompt(ctx)

    def test_utf8_content(self, tmp_path: Path) -> None:
        path = tmp_path / "template.md"
        content = "# Tasks 任務\n\n- [ ] 1. Test"
        path.write_text(content, encoding="utf-8")

        builder = PromptBuilder(path)
        result = ValidationResult(is_valid=False, issues=())
        ctx = PromptContext(content, MALFORMED, result)
        prompt = builder.build_prompt(ctx)
        assert "任務" in prompt

    def test_independent_instances(self, tmp_path: Path) -> None:
        p1 = tmp_path / "t1.md"
        p2 = tmp_path / "t2.md"
        p1.write_text("Template 1", encoding="utf-8")
        p2.write_text("Template 2", encoding="utf-8")

        result = ValidationResult(is_valid=False, issues=())
        ctx = PromptContext("", MALFORMED, result)

        prompt1 = PromptBuilder(p1).build_prompt(ctx)
        prompt2 = PromptBuilder(p2).build_prompt(ctx)
        assert "Template 1" in prompt1
        assert "Template 2" in prompt2


class TestPromptContext:
    def test_is_frozen(self) -> None:
        ctx = PromptContext("t", "m", ValidationResult(is_valid=True, issues=()))
        with pytest.raises(AttributeError):
            ctx.template_content = "modified"  # type: ignore
