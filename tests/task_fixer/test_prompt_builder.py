"""Tests for prompt builder module."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from spec_workflow_runner.task_fixer.prompt_builder import PromptBuilder, PromptContext
from spec_workflow_runner.task_fixer.validator import (
    IssueType,
    ValidationIssue,
    ValidationResult,
)


@pytest.fixture
def template_content() -> str:
    """Sample template content for testing."""
    return """# Tasks Document

- [ ] 1. First task
  - Description of task
- [ ] 2. Second task
  - More details
"""


@pytest.fixture
def temp_template_file(template_content: str, tmp_path: Path) -> Path:
    """Create a temporary template file."""
    template_path = tmp_path / "tasks-template.md"
    template_path.write_text(template_content, encoding="utf-8")
    return template_path


@pytest.fixture
def malformed_content() -> str:
    """Sample malformed content for testing."""
    return """# Tasks Document

- 1. Task without checkbox
- [x] 2. Valid task
- [*] Invalid checkbox
"""


@pytest.fixture
def validation_issues() -> tuple[ValidationIssue, ...]:
    """Sample validation issues for testing."""
    return (
        ValidationIssue(
            issue_type=IssueType.MISSING_CHECKBOX,
            line_number=3,
            line_content="- 1. Task without checkbox",
            message="Line 3: Task line is missing valid checkbox",
        ),
        ValidationIssue(
            issue_type=IssueType.INVALID_CHECKBOX,
            line_number=5,
            line_content="- [*] Invalid checkbox",
            message="Line 5: Invalid checkbox character '*'",
        ),
    )


@pytest.fixture
def validation_result(validation_issues: tuple[ValidationIssue, ...]) -> ValidationResult:
    """Sample validation result for testing."""
    return ValidationResult(is_valid=False, issues=validation_issues)


@pytest.fixture
def prompt_context(
    template_content: str,
    malformed_content: str,
    validation_result: ValidationResult,
) -> PromptContext:
    """Create a PromptContext for testing."""
    return PromptContext(
        template_content=template_content,
        malformed_content=malformed_content,
        validation_result=validation_result,
    )


def test_prompt_builder_initialization(temp_template_file: Path) -> None:
    """Test PromptBuilder initialization."""
    builder = PromptBuilder(temp_template_file)
    assert builder._template_path == temp_template_file
    assert builder._template_content is None  # Not loaded yet


def test_build_prompt_structure(
    temp_template_file: Path,
    prompt_context: PromptContext,
    template_content: str,
    malformed_content: str,
) -> None:
    """Test that build_prompt includes all required sections."""
    builder = PromptBuilder(temp_template_file)
    prompt = builder.build_prompt(prompt_context)

    # Check that prompt contains all required sections
    assert "You are a format correction assistant" in prompt
    assert "# INSTRUCTIONS" in prompt
    assert "# TEMPLATE FORMAT" in prompt
    assert "# VALIDATION ISSUES" in prompt
    assert "# MALFORMED CONTENT" in prompt
    assert "# YOUR TASK" in prompt

    # Check that template content is included
    assert template_content in prompt

    # Check that malformed content is included
    assert malformed_content in prompt

    # Check that instructions include key points
    assert "Output ONLY the corrected markdown content" in prompt
    assert "no explanations, no code blocks" in prompt
    assert "Preserve all task content and structure" in prompt


def test_build_prompt_includes_validation_issues(
    temp_template_file: Path,
    prompt_context: PromptContext,
) -> None:
    """Test that build_prompt includes validation issues summary."""
    builder = PromptBuilder(temp_template_file)
    prompt = builder.build_prompt(prompt_context)

    # Validation issues should be included via error_summary
    assert prompt_context.validation_result.error_summary in prompt


def test_build_prompt_formats_content_in_code_blocks(
    temp_template_file: Path,
    prompt_context: PromptContext,
) -> None:
    """Test that template and malformed content are wrapped in markdown code blocks."""
    builder = PromptBuilder(temp_template_file)
    prompt = builder.build_prompt(prompt_context)

    # Template should be in markdown code block
    assert "```markdown" in prompt
    assert "```" in prompt

    # Count markdown code blocks (should have at least 2: template and malformed content)
    markdown_blocks = prompt.count("```markdown")
    assert markdown_blocks >= 2


def test_template_lazy_loading(temp_template_file: Path, template_content: str) -> None:
    """Test that template is loaded lazily and cached."""
    builder = PromptBuilder(temp_template_file)

    # Template should not be loaded initially
    assert builder._template_content is None

    # First call should load template
    with patch.object(Path, "read_text", return_value=template_content) as mock_read:
        loaded_template = builder._load_template()
        assert loaded_template == template_content
        assert mock_read.call_count == 1

    # Template should now be cached
    assert builder._template_content == template_content

    # Second call should use cached version (no additional read)
    with patch.object(Path, "read_text", return_value=template_content) as mock_read:
        cached_template = builder._load_template()
        assert cached_template == template_content
        assert mock_read.call_count == 0  # Should not read again


def test_template_loaded_only_once_across_multiple_prompts(
    temp_template_file: Path,
    prompt_context: PromptContext,
) -> None:
    """Test that template is loaded only once even when building multiple prompts."""
    builder = PromptBuilder(temp_template_file)

    # Build first prompt
    prompt1 = builder.build_prompt(prompt_context)
    assert len(prompt1) > 0

    # Template should now be cached
    cached_content = builder._template_content
    assert cached_content is not None

    # Build second prompt
    prompt2 = builder.build_prompt(prompt_context)
    assert len(prompt2) > 0

    # Cached content should be the same
    assert builder._template_content is cached_content


def test_load_template_file_not_found() -> None:
    """Test that FileNotFoundError is raised for non-existent template."""
    non_existent_path = Path("/non/existent/template.md")
    builder = PromptBuilder(non_existent_path)

    with pytest.raises(FileNotFoundError, match="Template not found"):
        builder._load_template()


def test_load_template_encoding(tmp_path: Path) -> None:
    """Test that template is loaded with UTF-8 encoding."""
    template_path = tmp_path / "template.md"
    # Write content with UTF-8 characters
    unicode_content = "# Tasks 任務 📝\n\n- [ ] 1. Test task"
    template_path.write_text(unicode_content, encoding="utf-8")

    builder = PromptBuilder(template_path)
    loaded = builder._load_template()

    assert loaded == unicode_content
    assert "任務" in loaded
    assert "📝" in loaded


def test_build_prompt_with_valid_file(tmp_path: Path) -> None:
    """Test building prompt when validation result is valid."""
    template_path = tmp_path / "template.md"
    template_path.write_text("# Template", encoding="utf-8")

    valid_result = ValidationResult(is_valid=True, issues=())
    context = PromptContext(
        template_content="# Template",
        malformed_content="# Valid Content",
        validation_result=valid_result,
    )

    builder = PromptBuilder(template_path)
    prompt = builder.build_prompt(context)

    # Should still build a prompt even with valid content
    assert "# VALIDATION ISSUES" in prompt
    assert valid_result.error_summary in prompt
    assert "No validation issues found" in prompt


def test_build_prompt_with_empty_malformed_content(tmp_path: Path) -> None:
    """Test building prompt with empty malformed content."""
    template_path = tmp_path / "template.md"
    template_path.write_text("# Template", encoding="utf-8")

    validation_result = ValidationResult(is_valid=False, issues=())
    context = PromptContext(
        template_content="# Template",
        malformed_content="",
        validation_result=validation_result,
    )

    builder = PromptBuilder(template_path)
    prompt = builder.build_prompt(context)

    # Should handle empty content gracefully
    assert "# MALFORMED CONTENT" in prompt
    assert len(prompt) > 0


def test_prompt_context_immutability() -> None:
    """Test that PromptContext is immutable (frozen dataclass)."""
    context = PromptContext(
        template_content="template",
        malformed_content="malformed",
        validation_result=ValidationResult(is_valid=True, issues=()),
    )

    # Should not be able to modify frozen dataclass
    with pytest.raises(AttributeError):
        context.template_content = "modified"  # type: ignore


def test_build_prompt_preserves_newlines_in_content(tmp_path: Path) -> None:
    """Test that newlines in template and malformed content are preserved."""
    template_content = "Line 1\nLine 2\nLine 3"
    malformed_content = "Task 1\n\nTask 2"

    # Write template to file
    template_path = tmp_path / "template.md"
    template_path.write_text(template_content, encoding="utf-8")

    validation_result = ValidationResult(is_valid=False, issues=())
    context = PromptContext(
        template_content=template_content,
        malformed_content=malformed_content,
        validation_result=validation_result,
    )

    builder = PromptBuilder(template_path)
    prompt = builder.build_prompt(context)

    # Template content should be in prompt with newlines preserved
    assert "Line 1\nLine 2\nLine 3" in prompt
    # Malformed content should be in prompt with newlines preserved
    assert "Task 1\n\nTask 2" in prompt


def test_build_prompt_output_instructions_clear(tmp_path: Path) -> None:
    """Test that output instructions clearly specify markdown only."""
    template_path = tmp_path / "template.md"
    template_path.write_text("# Template", encoding="utf-8")

    validation_result = ValidationResult(is_valid=False, issues=())
    context = PromptContext(
        template_content="# Template",
        malformed_content="# Content",
        validation_result=validation_result,
    )

    builder = PromptBuilder(template_path)
    prompt = builder.build_prompt(context)

    # Check for clear output instructions
    assert "Output ONLY the corrected markdown content" in prompt
    assert "no explanations" in prompt.lower()
    assert "no code blocks" in prompt.lower() or "no code fences" in prompt.lower()
    assert "ONLY markdown" in prompt


def test_multiple_builders_independent_caching(tmp_path: Path) -> None:
    """Test that multiple PromptBuilder instances cache independently."""
    template1_path = tmp_path / "template1.md"
    template2_path = tmp_path / "template2.md"

    template1_path.write_text("Template 1", encoding="utf-8")
    template2_path.write_text("Template 2", encoding="utf-8")

    builder1 = PromptBuilder(template1_path)
    builder2 = PromptBuilder(template2_path)

    # Load templates
    content1 = builder1._load_template()
    content2 = builder2._load_template()

    # Each builder should have its own cached content
    assert content1 == "Template 1"
    assert content2 == "Template 2"
    assert builder1._template_content == "Template 1"
    assert builder2._template_content == "Template 2"
