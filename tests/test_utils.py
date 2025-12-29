"""Tests for utility functions."""

from __future__ import annotations

import pytest

from spec_workflow_runner.utils import is_context_limit_error


def test_is_context_limit_error_detects_claude_errors() -> None:
    """Verify detection of Claude context limit errors."""
    # Claude error pattern 1
    assert is_context_limit_error(
        "input length and max_tokens exceed context limit: 197626 + 21333 > 200000"
    )

    # Claude error pattern 2
    assert is_context_limit_error("Request size exceeds model context window")

    # Claude error pattern 3
    assert is_context_limit_error("Error: exceed context limit")

    # Claude error pattern 4 (Rate limit / Daily limit)
    assert is_context_limit_error("You've hit your limit · resets 3am (Asia/Tokyo)")


def test_is_context_limit_error_detects_openai_errors() -> None:
    """Verify detection of OpenAI context limit errors."""
    # OpenAI error pattern 1
    assert is_context_limit_error(
        "Your input exceeds the context window of this model. Please adjust your input and try again."
    )

    # OpenAI error pattern 2
    assert is_context_limit_error("Error: context_length_exceeded")

    # OpenAI error pattern 3
    assert is_context_limit_error(
        "This model's maximum context length is 128000 tokens. "
        "However, your messages resulted in 249114 tokens"
    )


def test_is_context_limit_error_detects_gemini_errors() -> None:
    """Verify detection of Gemini context limit errors."""
    # Gemini error pattern with token mention
    assert is_context_limit_error("Error: RESOURCE_EXHAUSTED - token limit exceeded")

    # Gemini error pattern with context mention
    assert is_context_limit_error("RESOURCE_EXHAUSTED: context window overflow")


def test_is_context_limit_error_case_insensitive() -> None:
    """Verify that error detection is case-insensitive."""
    assert is_context_limit_error("CONTEXT LIMIT EXCEEDED")
    assert is_context_limit_error("Context Limit Exceeded")
    assert is_context_limit_error("context limit exceeded")
    assert is_context_limit_error("EXCEEDS THE CONTEXT WINDOW")


def test_is_context_limit_error_rejects_non_context_errors() -> None:
    """Verify that non-context errors are not detected as context limit errors."""
    # Generic errors
    assert not is_context_limit_error("Connection timeout")
    assert not is_context_limit_error("Invalid API key")
    assert not is_context_limit_error("Rate limit exceeded")

    # RESOURCE_EXHAUSTED without context/token keywords
    assert not is_context_limit_error("RESOURCE_EXHAUSTED: quota exceeded")
    assert not is_context_limit_error("RESOURCE_EXHAUSTED: disk space full")

    # Empty string
    assert not is_context_limit_error("")


def test_is_context_limit_error_handles_multiline_errors() -> None:
    """Verify detection in multiline error messages."""
    multiline_error = """
    API Error occurred:
    Error Code: 400
    Message: input length and max_tokens exceed context limit: 197626 + 21333 > 200000
    Please reduce your input size
    """
    assert is_context_limit_error(multiline_error)
