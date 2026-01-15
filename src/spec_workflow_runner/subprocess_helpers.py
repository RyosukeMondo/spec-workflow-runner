"""Platform-agnostic subprocess helpers for Windows/Linux/macOS compatibility.

This module centralizes platform-specific subprocess logic to eliminate scattered
platform checks throughout the codebase.
"""

from __future__ import annotations

import os
import platform
import shlex
import subprocess
from pathlib import Path
from typing import Any


def format_command_string(command: list[str] | tuple[str, ...]) -> str:
    """Format command as a properly quoted string for the current platform.

    Uses platform-specific quoting rules:
    - Windows: subprocess.list2cmdline() for cmd.exe/PowerShell compatibility
    - Linux/macOS: shlex.join() for POSIX shell compatibility

    Args:
        command: Command as list or tuple

    Returns:
        Properly quoted command string suitable for display or shell execution

    Examples:
        >>> format_command_string(['echo', 'hello world'])
        # Windows: 'echo "hello world"'
        # Linux: "echo 'hello world'"
    """
    is_windows = platform.system() == "Windows"

    if is_windows:
        # Use Windows-native quoting (handles cmd.exe and PowerShell)
        return subprocess.list2cmdline(command)
    else:
        # Use POSIX shell quoting (bash, zsh, sh)
        return shlex.join(command)


def _get_clean_env(additions: dict[str, str] | None = None) -> dict[str, str]:
    """Get environment with CLAUDE_* variables removed and optional additions.

    Prevents nested Claude Code session conflicts by removing all environment
    variables that start with CLAUDE or CLAUDE_.

    Args:
        additions: Optional dict of environment variables to add

    Returns:
        Environment dict with CLAUDE_* vars removed and additions applied
    """
    env = os.environ.copy()
    # Remove all CLAUDE-related env vars to prevent nested session conflicts
    for key in list(env.keys()):
        if key.startswith("CLAUDE") or key.startswith("CLAUDE_"):
            del env[key]
    if additions:
        env.update(additions)
    return env


def run_command(
    command: list[str] | tuple[str, ...],
    *,
    cwd: Path | str | None = None,
    timeout: int | None = None,
    check: bool = False,
    clean_claude_env: bool = False,
    env_additions: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Platform-agnostic subprocess.run() wrapper.

    Automatically handles Windows-specific requirements:
    - Uses shell=True on Windows for .cmd/.bat executable resolution
    - Converts command list to properly quoted string on Windows
    - Forces UTF-8 encoding with error replacement

    Args:
        command: Command as list or tuple
        cwd: Working directory (optional)
        timeout: Timeout in seconds (optional)
        check: Raise CalledProcessError on non-zero exit code
        clean_claude_env: Remove CLAUDE_* env vars to prevent nested sessions
        env_additions: Additional environment variables to set

    Returns:
        CompletedProcess with text output (UTF-8 encoded)

    Raises:
        FileNotFoundError: If executable not found
        subprocess.CalledProcessError: If check=True and returncode != 0
        subprocess.TimeoutExpired: If timeout specified and exceeded
    """
    is_windows = platform.system() == "Windows"

    # Prepare environment if needed
    env = None
    if clean_claude_env or env_additions:
        env = _get_clean_env(env_additions)

    # On Windows with shell=True, subprocess requires a string command
    if is_windows:
        command_str = " ".join(shlex.quote(arg) for arg in command)
        return subprocess.run(
            command_str,
            cwd=cwd,
            timeout=timeout,
            check=check,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            shell=True,
            env=env,
        )
    else:
        # On Linux/macOS, use command list with shell=False for security
        return subprocess.run(
            command,
            cwd=cwd,
            timeout=timeout,
            check=check,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            shell=False,
            env=env,
        )


def popen_command(
    command: list[str] | tuple[str, ...],
    *,
    cwd: Path | str | None = None,
    stdout: Any = subprocess.PIPE,
    stderr: Any = subprocess.STDOUT,
    clean_claude_env: bool = False,
    env_additions: dict[str, str] | None = None,
    text_mode: bool = False,
) -> subprocess.Popen[str] | subprocess.Popen[bytes]:
    """Platform-agnostic subprocess.Popen() wrapper for non-blocking execution.

    Automatically handles Windows-specific requirements:
    - Uses shell=True on Windows for .cmd/.bat executable resolution
    - Converts command list to properly quoted string on Windows
    - Sets bufsize=0 for unbuffered real-time output streaming

    Args:
        command: Command as list or tuple
        cwd: Working directory (optional)
        stdout: stdout redirection (default: PIPE)
        stderr: stderr redirection (default: STDOUT)
        clean_claude_env: Remove CLAUDE_* env vars to prevent nested sessions
        env_additions: Additional environment variables to set
        text_mode: Return Popen[str] with text mode (for file output)

    Returns:
        Popen process object (bytes mode by default, text mode if text_mode=True)

    Notes:
        - Bufsize=0 for unbuffered streaming (important for real-time output)
        - text_mode=False by default (bytes mode) for compatibility with PIPE
        - text_mode=True for direct file output (requires file handle in stdout)
    """
    is_windows = platform.system() == "Windows"

    # Prepare environment if needed
    env = None
    if clean_claude_env or env_additions:
        env = _get_clean_env(env_additions)

    # On Windows with shell=True, subprocess requires a string command
    if is_windows:
        command_str = " ".join(shlex.quote(arg) for arg in command)
        return subprocess.Popen(
            command_str,
            cwd=cwd,
            stdout=stdout,
            stderr=stderr,
            bufsize=0,
            shell=True,
            env=env,
            text=text_mode,
            encoding='utf-8' if text_mode else None,
            errors='replace' if text_mode else None,
        )
    else:
        # On Linux/macOS, use command list with shell=False for security
        return subprocess.Popen(
            command,
            cwd=cwd,
            stdout=stdout,
            stderr=stderr,
            bufsize=0,
            shell=False,
            env=env,
            text=text_mode,
            encoding='utf-8' if text_mode else None,
            errors='replace' if text_mode else None,
        )
