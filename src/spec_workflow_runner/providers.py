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
    def get_provider_name(self) -> str:
        """Get the human-readable provider name."""


class CodexProvider(Provider):
    """Provider for Codex backend."""

    def __init__(
        self,
        base_command: Sequence[str] = ("codex", "e", "--dangerously-bypass-approvals-and-sandbox"),
    ) -> None:
        self._base_command = tuple(base_command)

    def build_command(
        self,
        prompt: str,
        project_path: Path,
        config_overrides: Sequence[tuple[str, str]],
    ) -> ProviderCommand:
        """Build codex command with config overrides."""
        executable = self._base_command[0]
        args: list[str] = list(self._base_command[1:])
        for key, value in config_overrides:
            args.extend(["-c", f"{key}={value}"])
        args.append(prompt)
        return ProviderCommand(executable=executable, args=tuple(args))

    def get_mcp_list_command(self) -> ProviderCommand:
        """Get command to list available MCP servers."""
        return ProviderCommand(executable="codex", args=("mcp", "list"))

    def get_provider_name(self) -> str:
        """Get the human-readable provider name."""
        return "Codex"


class ClaudeProvider(Provider):
    """Provider for Claude CLI backend."""

    def __init__(
        self,
        executable: str = "claude",
        skip_permissions: bool = True,
    ) -> None:
        self._executable = executable
        self._skip_permissions = skip_permissions

    def build_command(
        self,
        prompt: str,
        project_path: Path,
        config_overrides: Sequence[tuple[str, str]],
    ) -> ProviderCommand:
        """Build claude command with permissions skipped for automation."""
        args = ["-p", prompt]
        if self._skip_permissions:
            args.append("--dangerously-skip-permissions")
        return ProviderCommand(executable=self._executable, args=tuple(args))

    def get_mcp_list_command(self) -> ProviderCommand:
        """Get command to list available MCP servers."""
        return ProviderCommand(executable=self._executable, args=("mcp", "list"))

    def get_provider_name(self) -> str:
        """Get the human-readable provider name."""
        return "Claude CLI"


def create_provider(provider_name: str, base_command: Sequence[str]) -> Provider:
    """Factory function to create a provider by name."""
    if provider_name == "codex":
        return CodexProvider(base_command=base_command)
    if provider_name == "claude":
        return ClaudeProvider()
    raise ValueError(f"Unknown provider: {provider_name}")
