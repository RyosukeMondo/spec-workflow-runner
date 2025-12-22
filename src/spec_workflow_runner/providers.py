"""AI provider abstractions for spec workflow automation."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ProviderCommand:
    """Command to execute for a provider."""

    executable: str
    args: Sequence[str]

    def to_list(self) -> list[str]:
        """Convert to a list of command parts."""
        return [self.executable, *self.args]


class Provider(ABC):
    """Abstract base class for AI providers."""

    @abstractmethod
    def build_command(
        self,
        prompt: str,
        project_path: Path,
        config_overrides: Sequence[tuple[str, str]],
    ) -> ProviderCommand:
        """Build the command to execute for this provider."""

    @abstractmethod
    def get_mcp_list_command(self) -> ProviderCommand:
        """Get command to list available MCP servers."""

    @abstractmethod
    def get_mcp_add_command(self, server_name: str, package: str) -> ProviderCommand:
        """Get command to add an MCP server.

        Args:
            server_name: Name of the MCP server (e.g., 'spec-workflow')
            package: NPX package to run (e.g., 'npx @pimzino/spec-workflow-mcp@latest')

        Returns:
            Command to add the MCP server
        """

    @abstractmethod
    def get_provider_name(self) -> str:
        """Get the human-readable provider name."""


class CodexProvider(Provider):
    """Provider for Codex backend."""

    SUPPORTED_MODELS = (
        "gpt-5.1-codex-max",
        "gpt-5.1-codex",
        "gpt-5.1-codex-mini",
        "gpt-5-codex",
    )

    def __init__(
        self,
        base_command: Sequence[str] = ("codex", "e", "--dangerously-bypass-approvals-and-sandbox"),
        model: str | None = None,
    ) -> None:
        self._base_command = tuple(base_command)
        self._model = model

    def build_command(
        self,
        prompt: str,
        project_path: Path,
        config_overrides: Sequence[tuple[str, str]],
    ) -> ProviderCommand:
        """Build codex command with config overrides and model selection."""
        executable = self._base_command[0]
        args: list[str] = list(self._base_command[1:])
        if self._model:
            args.extend(["--model", self._model])
        for key, value in config_overrides:
            args.extend(["-c", f"{key}={value}"])
        args.append(prompt)
        return ProviderCommand(executable=executable, args=tuple(args))

    def get_mcp_list_command(self) -> ProviderCommand:
        """Get command to list available MCP servers."""
        return ProviderCommand(executable="codex", args=("mcp", "list"))

    def get_mcp_add_command(self, server_name: str, package: str) -> ProviderCommand:
        """Get command to add an MCP server."""
        return ProviderCommand(executable="codex", args=("mcp", "add", server_name, package))

    def get_provider_name(self) -> str:
        """Get the human-readable provider name."""
        return "Codex"


class ClaudeProvider(Provider):
    """Provider for Claude CLI backend."""

    SUPPORTED_MODELS = (
        "sonnet",
        "haiku",
        "opus",
    )

    def __init__(
        self,
        executable: str = "claude",
        skip_permissions: bool = True,
        model: str | None = None,
    ) -> None:
        self._executable = executable
        self._skip_permissions = skip_permissions
        self._model = model

    def build_command(
        self,
        prompt: str,
        project_path: Path,
        config_overrides: Sequence[tuple[str, str]],
    ) -> ProviderCommand:
        """Build claude command with permissions skipped for automation and model selection."""
        args = ["-p", prompt]
        if self._model:
            args.extend(["--model", self._model])
        if self._skip_permissions:
            args.append("--dangerously-skip-permissions")
        return ProviderCommand(executable=self._executable, args=tuple(args))

    def get_mcp_list_command(self) -> ProviderCommand:
        """Get command to list available MCP servers."""
        return ProviderCommand(executable=self._executable, args=("mcp", "list"))

    def get_mcp_add_command(self, server_name: str, package: str) -> ProviderCommand:
        """Get command to add an MCP server."""
        return ProviderCommand(executable=self._executable, args=("mcp", "add", server_name, package))

    def get_provider_name(self) -> str:
        """Get the human-readable provider name."""
        return "Claude CLI"


class GeminiProvider(Provider):
    """Provider for Google Gemini CLI backend with maximum risk/efficiency settings."""

    SUPPORTED_MODELS = (
        "gemini-3-pro-preview",
        "gemini-3-flash-preview",
        "gemini-2.5-pro",
        "gemini-2.5-flash",
        "gemini-2.5-flash-lite",
        "gemini-2.0-flash-exp",
        "gemini-1.5-pro",
        "gemini-1.5-flash",
        "gemini-1.5-flash-8b",
    )

    def __init__(
        self,
        executable: str = "gemini",
        model: str | None = None,
        max_risk: bool = True,
    ) -> None:
        self._executable = executable
        self._model = model
        self._max_risk = max_risk

    def build_command(
        self,
        prompt: str,
        project_path: Path,
        config_overrides: Sequence[tuple[str, str]],
    ) -> ProviderCommand:
        """Build gemini command with maximum risk settings for efficiency."""
        args = ["-p", prompt]

        if self._model:
            args.extend(["--model", self._model])

        if self._max_risk:
            args.extend([
                "--yolo",
                "--output-format", "json",
            ])

        return ProviderCommand(executable=self._executable, args=tuple(args))

    def get_mcp_list_command(self) -> ProviderCommand:
        """Get command to list available MCP servers."""
        return ProviderCommand(executable=self._executable, args=("mcp", "list"))

    def get_mcp_add_command(self, server_name: str, package: str) -> ProviderCommand:
        """Get command to add an MCP server."""
        return ProviderCommand(executable=self._executable, args=("mcp", "add", server_name, package))

    def get_provider_name(self) -> str:
        """Get the human-readable provider name."""
        return "Google Gemini"


def get_supported_models(provider_name: str) -> tuple[str, ...]:
    """Get the list of supported models for a given provider."""
    if provider_name == "codex":
        return CodexProvider.SUPPORTED_MODELS
    if provider_name == "claude":
        return ClaudeProvider.SUPPORTED_MODELS
    if provider_name == "gemini":
        return GeminiProvider.SUPPORTED_MODELS
    raise ValueError(f"Unknown provider: {provider_name}")


def create_provider(
    provider_name: str,
    base_command: Sequence[str],
    model: str | None = None,
) -> Provider:
    """Factory function to create a provider by name."""
    if provider_name == "codex":
        return CodexProvider(base_command=base_command, model=model)
    if provider_name == "claude":
        return ClaudeProvider(model=model)
    if provider_name == "gemini":
        return GeminiProvider(model=model, max_risk=True)
    raise ValueError(f"Unknown provider: {provider_name}")
