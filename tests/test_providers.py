"""Tests for provider abstraction module."""

from __future__ import annotations

from pathlib import Path

import pytest

from spec_workflow_runner.providers import (
    ClaudeProvider,
    CodexProvider,
    create_provider,
)


def test_codex_provider_builds_basic_command() -> None:
    provider = CodexProvider()
    cmd = provider.build_command(
        prompt="test prompt",
        project_path=Path("/tmp/project"),
        config_overrides=(),
    )

    assert cmd.executable == "codex"
    assert cmd.args == ("e", "--dangerously-bypass-approvals-and-sandbox", "test prompt")


def test_codex_provider_applies_config_overrides() -> None:
    provider = CodexProvider()
    overrides = (
        ("mcp_servers.demo.tool_timeout_sec", "60"),
        ("features.example", '"value"'),
    )
    cmd = provider.build_command(
        prompt="test prompt",
        project_path=Path("/tmp/project"),
        config_overrides=overrides,
    )

    expected_args = (
        "e",
        "--dangerously-bypass-approvals-and-sandbox",
        "-c",
        "mcp_servers.demo.tool_timeout_sec=60",
        "-c",
        'features.example="value"',
        "test prompt",
    )
    assert cmd.args == expected_args


def test_codex_provider_to_list() -> None:
    provider = CodexProvider()
    cmd = provider.build_command(
        prompt="test",
        project_path=Path("/tmp/project"),
        config_overrides=(),
    )

    assert cmd.to_list() == ["codex", "e", "--dangerously-bypass-approvals-and-sandbox", "test"]


def test_claude_provider_builds_basic_command() -> None:
    provider = ClaudeProvider(executable="claude", skip_permissions=True)
    cmd = provider.build_command(
        prompt="test prompt",
        project_path=Path("/tmp/project"),
        config_overrides=(),
    )

    assert cmd.executable == "claude"
    assert cmd.args == ("-p", "test prompt", "--dangerously-skip-permissions")


def test_claude_provider_with_custom_executable() -> None:
    provider = ClaudeProvider(executable="claude-custom", skip_permissions=True)
    cmd = provider.build_command(
        prompt="test",
        project_path=Path("/tmp/project"),
        config_overrides=(),
    )

    assert cmd.executable == "claude-custom"
    assert "--dangerously-skip-permissions" in cmd.args


def test_claude_provider_without_skip_permissions() -> None:
    provider = ClaudeProvider(executable="claude", skip_permissions=False)
    cmd = provider.build_command(
        prompt="test",
        project_path=Path("/tmp/project"),
        config_overrides=(),
    )

    assert "--dangerously-skip-permissions" not in cmd.args
    assert cmd.args == ("-p", "test")


def test_claude_provider_to_list() -> None:
    provider = ClaudeProvider()
    cmd = provider.build_command(
        prompt="test",
        project_path=Path("/tmp/project"),
        config_overrides=(),
    )

    result = cmd.to_list()
    assert result[0] == "claude"
    assert "-p" in result
    assert "test" in result
    assert "--dangerously-skip-permissions" in result


def test_create_provider_creates_codex() -> None:
    provider = create_provider("codex", base_command=("codex", "e"))
    assert isinstance(provider, CodexProvider)


def test_create_provider_creates_claude() -> None:
    provider = create_provider("claude", base_command=("codex", "e"))
    assert isinstance(provider, ClaudeProvider)


def test_create_provider_raises_on_unknown() -> None:
    with pytest.raises(ValueError, match="Unknown provider: invalid"):
        create_provider("invalid", base_command=("codex", "e"))
