"""Platform-agnostic subprocess helpers for Windows/Linux/macOS compatibility.

This module centralizes platform-specific subprocess logic to eliminate scattered
platform checks throughout the codebase.
"""

from __future__ import annotations

import logging
import os
import platform
import shlex
import subprocess
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


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
        command_str = format_command_string(command)
        return subprocess.run(
            command_str,
            cwd=cwd,
            timeout=timeout,
            check=check,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
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
            encoding="utf-8",
            errors="replace",
            shell=False,
            env=env,
        )


def popen_command(
    command: list[str] | tuple[str, ...],
    *,
    cwd: Path | str | None = None,
    stdin: Any = None,
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
        command_str = format_command_string(command)
        return subprocess.Popen(
            command_str,
            cwd=cwd,
            stdin=stdin,
            stdout=stdout,
            stderr=stderr,
            bufsize=0,
            shell=True,
            env=env,
            text=text_mode,
            encoding="utf-8" if text_mode else None,
            errors="replace" if text_mode else None,
        )
    else:
        # On Linux/macOS, use command list with shell=False for security
        return subprocess.Popen(
            command,
            cwd=cwd,
            stdin=stdin,
            stdout=stdout,
            stderr=stderr,
            bufsize=0,
            shell=False,
            env=env,
            text=text_mode,
            encoding="utf-8" if text_mode else None,
            errors="replace" if text_mode else None,
        )


def monitor_process_with_timeout(
    process: subprocess.Popen[str],
    timeout_seconds: int,
    on_activity: Callable[[str], None] | None = None,
) -> tuple[int | None, str | None]:
    """Monitor a subprocess with activity timeout detection.

    Args:
        process: The subprocess to monitor
        timeout_seconds: Maximum seconds of inactivity before timeout
        on_activity: Optional callback for each line of output

    Returns:
        Tuple of (exit_code, error_message)
        - exit_code is None if process timed out
        - error_message is None if process completed successfully
    """
    last_activity = time.time()
    output_buffer = []

    while True:
        # Check if process has exited
        if process.poll() is not None:
            # Process has exited
            exit_code = process.returncode

            # Collect any remaining output
            if process.stdout:
                try:
                    remaining = process.stdout.read()
                    if remaining:
                        output_buffer.append(remaining)
                        if on_activity:
                            on_activity(remaining)
                except Exception as e:
                    logger.warning(f"Error reading remaining output: {e}")

            # Check for error
            if exit_code != 0:
                error_msg = "".join(output_buffer[-100:])  # Last 100 lines
                return exit_code, error_msg

            return exit_code, None

        # Check for output (activity)
        if process.stdout:
            try:
                line = process.stdout.readline()
                if line:
                    output_buffer.append(line)
                    last_activity = time.time()
                    if on_activity:
                        on_activity(line)
            except Exception as e:
                logger.warning(f"Error reading stdout: {e}")

        # Check for timeout
        if time.time() - last_activity > timeout_seconds:
            logger.warning(
                f"Process {process.pid} timed out after {timeout_seconds}s of inactivity"
            )
            try:
                process.terminate()
                time.sleep(5)  # Wait 5s for graceful shutdown
                if process.poll() is None:
                    process.kill()  # Force kill if still running
            except Exception as e:
                logger.error(f"Error terminating process: {e}")

            return None, f"Process timed out after {timeout_seconds}s of inactivity"

        # Small sleep to prevent busy-waiting
        time.sleep(0.1)


def safe_terminate_process(process: subprocess.Popen[Any], timeout: int = 5) -> None:
    """Safely terminate a subprocess with graceful fallback to kill.

    Args:
        process: The subprocess to terminate
        timeout: Seconds to wait for graceful termination before force kill
    """
    try:
        process.terminate()
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        logger.warning(f"Process {process.pid} did not terminate gracefully, forcing kill")
        try:
            process.kill()
            process.wait(timeout=2)
        except Exception as e:
            logger.error(f"Failed to kill process {process.pid}: {e}")
    except Exception as e:
        logger.error(f"Error terminating process {process.pid}: {e}")
