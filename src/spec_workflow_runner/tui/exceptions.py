"""Custom exceptions for TUI operations.

This module defines a hierarchy of exceptions for different TUI error scenarios,
enabling graceful error handling and specific error messages.
"""


class TUIError(Exception):
    """Base exception for all TUI-related errors."""


class StateError(TUIError):
    """Raised when state operations fail (file I/O, serialization, etc.)."""


class RunnerError(TUIError):
    """Raised when subprocess/runner operations fail."""


class ConfigError(TUIError):
    """Raised when configuration is invalid or cannot be loaded."""
