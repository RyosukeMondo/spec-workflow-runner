"""Shared helpers for spec workflow automation scripts."""

from __future__ import annotations

import json
import os
import re
import subprocess
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, TypeVar

if TYPE_CHECKING:
    from .providers import Provider

T = TypeVar("T")


class RunnerError(Exception):
    """Raised when the run needs to abort early."""


def is_context_limit_error(error_message: str) -> bool:
    """Detect if an error is due to context limit/window exceeded.

    Checks for common error patterns from different LLM providers:
    - Claude: "context limit", "exceed context", "context window"
    - OpenAI: "context_length_exceeded", "exceeds the context window"
    - Gemini: "RESOURCE_EXHAUSTED" (context-related)

    Args:
        error_message: The error message string to check

    Returns:
        True if the error is a context limit error, False otherwise
    """
    error_lower = error_message.lower()

    # Claude API error patterns
    if "context limit" in error_lower:
        return True
    if "exceed context" in error_lower or "exceeds context" in error_lower:
        return True
    if "context window" in error_lower:
        return True
    if "hit your limit" in error_lower:
        return True

    # OpenAI error patterns
    if "context_length_exceeded" in error_lower:
        return True
    if "exceeds the context window" in error_lower:
        return True
    if "maximum context length" in error_lower:
        return True

    # Gemini error patterns (be specific to avoid false positives)
    if "resource_exhausted" in error_lower and ("token" in error_lower or "context" in error_lower):
        return True

    return False


def get_current_commit(repo_path: Path) -> str:
    """Return the current HEAD commit id for the repo."""
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_path,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def has_uncommitted_changes(repo_path: Path) -> bool:
    """Check if there are uncommitted changes (staged or unstaged)."""
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=repo_path,
        capture_output=True,
        text=True,
        check=True,
    )
    return bool(result.stdout.strip())


def _install_mcp_server(provider: Provider, project_path: Path, non_interactive: bool) -> None:
    """Install spec-workflow MCP server for the provider.

    Args:
        provider: Provider instance
        project_path: Path to project directory
        non_interactive: If True, install without prompting
    """
    import logging

    logger = logging.getLogger(__name__)

    server_name = "spec-workflow"
    package = "npx @pimzino/spec-workflow-mcp@latest"
    executable = provider.get_mcp_list_command().executable

    # Prompt user for confirmation in interactive mode
    if not non_interactive:
        print(f"\n📦 spec-workflow MCP server not found for {provider.get_provider_name()}.")
        print(f"   Would you like to install it now?")
        print(f"\n   Command: {executable} mcp add {server_name} {package}")

        while True:
            choice = input("\nInstall MCP server? (y/n): ").strip().lower()
            if choice == "n":
                raise RunnerError(
                    f"spec-workflow MCP server is required. "
                    f"Please install it manually: {executable} mcp add {server_name} {package}"
                )
            if choice == "y":
                break
            print("Invalid choice. Please enter 'y' or 'n'.")

    # Install MCP server
    add_cmd = provider.get_mcp_add_command(server_name, package)
    command = add_cmd.to_list()

    logger.info(f"Installing MCP server: {' '.join(command)}")
    print(f"\n📦 Installing spec-workflow MCP server for {provider.get_provider_name()}...")

    try:
        result = subprocess.run(
            command,
            cwd=project_path,
            capture_output=True,
            text=True,
            check=False,
        )

        if result.returncode != 0:
            raise RunnerError(
                f"Failed to install spec-workflow MCP server.\n"
                f"   Command: {' '.join(command)}\n"
                f"   Error: {result.stderr.strip()}"
            )

        print(f"✓ spec-workflow MCP server installed successfully for {provider.get_provider_name()}")
        logger.info("MCP server installation completed successfully")

    except Exception as err:
        raise RunnerError(f"Failed to install spec-workflow MCP server: {err}") from err


def check_clean_working_tree(repo_path: Path, non_interactive: bool = False) -> None:
    """Ensure working tree is clean before starting, prompting user if needed.

    Args:
        repo_path: Path to git repository
        non_interactive: If True, skip interactive prompt and raise error immediately.
                         Use this for non-interactive environments like TUI.
    """
    if not has_uncommitted_changes(repo_path):
        return

    # In non-interactive mode (TUI), just raise an error
    if non_interactive:
        raise RunnerError(
            "Uncommitted changes detected. Please commit or stash changes before starting runner."
        )

    # Interactive mode (CLI) - prompt user
    print("\n⚠️  Warning: Uncommitted changes detected in the repository.")
    print("   This will interfere with commit detection during the run.")
    print("\nOptions:")
    print("  1. Abort and let me commit/stash changes first (recommended)")
    print("  2. Continue anyway (commit detection may be unreliable)")

    while True:
        choice = input("\nSelect option (1 or 2): ").strip()
        if choice == "1":
            raise RunnerError("Aborted. Please commit or stash your changes, then run again.")
        if choice == "2":
            print("\n⚠️  Continuing with uncommitted changes. Commit detection may be unreliable.")
            return
        print("Invalid choice. Please enter 1 or 2.")


def check_mcp_server_exists(
    provider: Provider, project_path: Path, auto_install: bool = False, non_interactive: bool = False
) -> None:
    """Ensure spec-workflow MCP server is configured for the provider.

    Args:
        provider: Provider instance
        project_path: Path to project directory
        auto_install: If True, automatically install MCP server if not found
        non_interactive: If True, don't prompt user for installation confirmation
    """
    mcp_cmd = provider.get_mcp_list_command()
    command = mcp_cmd.to_list()

    try:
        result = subprocess.run(
            command,
            cwd=project_path,
            capture_output=True,
            text=True,
            check=False,
        )

        if result.returncode != 0:
            print(f"\n⚠️  Warning: Could not list MCP servers for {provider.get_provider_name()}.")
            print(f"   Command failed: {' '.join(command)}")
            print(f"   Error: {result.stderr.strip()}")
            print("\n   Task tracking may not work properly without the spec-workflow MCP server.")
            return

        output = result.stdout.lower()
        if "spec-workflow" not in output:
            # MCP server not found - attempt to install if enabled
            if auto_install:
                _install_mcp_server(provider, project_path, non_interactive)
                return

            executable = provider.get_mcp_list_command().executable
            print(f"\n🔍 DEBUG: MCP list output (first 300 chars):")
            print(f"   {repr(result.stdout[:300])}")
            print(f"   Lowercase contains 'spec-workflow': {'spec-workflow' in output}")
            raise RunnerError(
                f"spec-workflow MCP server not found for {provider.get_provider_name()}.\n"
                f"   The spec-workflow MCP server is required for automatic task tracking.\n"
                f"   Please configure it by running: {executable} mcp add spec-workflow npx @pimzino/spec-workflow-mcp@latest\n"
                f"   Or check your MCP server configuration."
            )

        print(f"✓ spec-workflow MCP server detected for {provider.get_provider_name()}")

    except FileNotFoundError as err:
        executable = provider.get_mcp_list_command().executable
        raise RunnerError(
            f"{executable} command not found.\n"
            f"   Please ensure {provider.get_provider_name()} is installed and available in PATH."
        ) from err


def _encode_override_value(value: object) -> str:
    """Convert arbitrary JSON-friendly values into TOML literals."""

    if value is None:
        raise ValueError("codex_config_overrides values cannot be null")
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    return json.dumps(value)


@dataclass(frozen=True)
class Config:
    """Runtime configuration loaded from config.json."""

    repos_root: Path
    spec_workflow_dir_name: str
    specs_subdir: str
    tasks_filename: str
    codex_command: Sequence[str]
    prompt_template: str
    no_commit_limit: int
    log_dir_name: str
    log_file_template: str
    ignore_dirs: tuple[str, ...]
    monitor_refresh_seconds: int
    cache_dir: Path
    cache_max_age_days: int
    codex_config_overrides: tuple[tuple[str, str], ...] = ()
    tui_refresh_seconds: int = 2
    tui_log_tail_lines: int = 200
    tui_min_terminal_cols: int = 80
    tui_min_terminal_rows: int = 24
    max_retries: int = 3
    context_limit_wait_seconds: int = 600

    @classmethod
    def from_dict(cls, payload: dict) -> Config:
        """Create a Config object from a raw dictionary."""
        repos_root = Path(os.path.expanduser(payload["repos_root"])).resolve()
        cache_dir = Path(
            os.path.expanduser(payload.get("cache_dir", "~/.cache/spec-workflow-runner"))
        ).resolve()
        overrides_raw = payload.get("codex_config_overrides", {})
        overrides: list[tuple[str, str]] = []
        if overrides_raw:
            if not isinstance(overrides_raw, dict):
                raise TypeError("codex_config_overrides must be an object")
            for key, value in overrides_raw.items():
                overrides.append((str(key), _encode_override_value(value)))

        # Parse and validate TUI config values
        tui_refresh_seconds = int(payload.get("tui_refresh_seconds", 2))
        tui_log_tail_lines = int(payload.get("tui_log_tail_lines", 200))
        tui_min_terminal_cols = int(payload.get("tui_min_terminal_cols", 80))
        tui_min_terminal_rows = int(payload.get("tui_min_terminal_rows", 24))
        max_retries = int(payload.get("max_retries", 3))
        context_limit_wait_seconds = int(payload.get("context_limit_wait_seconds", 600))

        if tui_refresh_seconds <= 0:
            raise ValueError(f"tui_refresh_seconds must be positive, got {tui_refresh_seconds}")
        if tui_log_tail_lines <= 0:
            raise ValueError(f"tui_log_tail_lines must be positive, got {tui_log_tail_lines}")
        if tui_min_terminal_cols <= 0:
            raise ValueError(
                f"tui_min_terminal_cols must be positive, got {tui_min_terminal_cols}"
            )
        if tui_min_terminal_rows <= 0:
            raise ValueError(
                f"tui_min_terminal_rows must be positive, got {tui_min_terminal_rows}"
            )
        if max_retries <= 0:
            raise ValueError(f"max_retries must be positive, got {max_retries}")
        if context_limit_wait_seconds <= 0:
            raise ValueError(
                f"context_limit_wait_seconds must be positive, got {context_limit_wait_seconds}"
            )

        return cls(
            repos_root=repos_root,
            spec_workflow_dir_name=payload["spec_workflow_dir_name"],
            specs_subdir=payload["specs_subdir"],
            tasks_filename=payload["tasks_filename"],
            codex_command=tuple(payload["codex_command"]),
            prompt_template=payload["prompt_template"],
            no_commit_limit=int(payload["no_commit_limit"]),
            log_dir_name=payload["log_dir_name"],
            log_file_template=payload["log_file_template"],
            ignore_dirs=tuple(payload.get("ignore_dirs", [])),
            monitor_refresh_seconds=int(payload.get("monitor_refresh_seconds", 5)),
            cache_dir=cache_dir,
            cache_max_age_days=int(payload.get("cache_max_age_days", 7)),
            codex_config_overrides=tuple(overrides),
            tui_refresh_seconds=tui_refresh_seconds,
            tui_log_tail_lines=tui_log_tail_lines,
            tui_min_terminal_cols=tui_min_terminal_cols,
            tui_min_terminal_rows=tui_min_terminal_rows,
            max_retries=max_retries,
            context_limit_wait_seconds=context_limit_wait_seconds,
        )


@dataclass(frozen=True)
class TaskStats:
    """Simple container for parsed task statistics."""

    done: int
    pending: int
    in_progress: int

    @property
    def total(self) -> int:
        return self.done + self.pending + self.in_progress

    def summary(self) -> str:
        return (
            f"{self.done}/{self.total} complete "
            f"({self.in_progress} in progress, {self.pending} pending)"
        )


def load_config(path: Path) -> Config:
    """Load configuration from the provided path."""
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    return Config.from_dict(data)


@dataclass(frozen=True)
class ProjectCache:
    """Cache data for discovered projects."""

    repos_root: str
    last_scan: float
    projects: list[str]

    def to_dict(self) -> dict:
        return {
            "repos_root": self.repos_root,
            "last_scan": self.last_scan,
            "projects": self.projects,
        }

    @classmethod
    def from_dict(cls, data: dict) -> ProjectCache:
        return cls(
            repos_root=str(data["repos_root"]),
            last_scan=float(data["last_scan"]),
            projects=[str(p) for p in data["projects"]],
        )


def _get_cache_path(cfg: Config) -> Path:
    """Return the path to the projects cache file."""
    return cfg.cache_dir / "projects.json"


def _read_cache(cfg: Config) -> ProjectCache | None:
    """Read cache from disk, returning None if unavailable or invalid."""
    cache_path = _get_cache_path(cfg)
    if not cache_path.exists():
        return None
    try:
        with cache_path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        return ProjectCache.from_dict(data)
    except (OSError, ValueError, KeyError, TypeError):
        return None


def _write_cache(cfg: Config, cache: ProjectCache) -> None:
    """Write cache to disk."""
    cache_path = _get_cache_path(cfg)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    with cache_path.open("w", encoding="utf-8") as handle:
        json.dump(cache.to_dict(), handle, indent=2)


def _is_cache_valid(cfg: Config, cache: ProjectCache) -> bool:
    """Check if cache is still valid based on repos_root and age."""
    if cache.repos_root != str(cfg.repos_root):
        return False
    age_seconds = time.time() - cache.last_scan
    age_days = age_seconds / 86400
    return age_days <= cfg.cache_max_age_days


def _scan_projects(cfg: Config) -> list[Path]:
    """Perform a full filesystem scan for projects."""
    root = cfg.repos_root
    if not root.exists():
        raise FileNotFoundError(f"Repos root not found: {root}")

    found: list[Path] = []
    for dirpath, dirnames, _ in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in cfg.ignore_dirs]
        if cfg.spec_workflow_dir_name in dirnames:
            found.append(Path(dirpath))
    return sorted(found)


def discover_projects(cfg: Config, *, force_refresh: bool = False) -> list[Path]:
    """Return every project directory under repos_root containing a .spec-workflow.

    Uses cache by default unless force_refresh=True or cache is stale.
    """
    cache = None if force_refresh else _read_cache(cfg)

    if cache and _is_cache_valid(cfg, cache):
        age_seconds = time.time() - cache.last_scan
        age_days = int(age_seconds / 86400)
        if age_days == 0:
            print("Using cached projects (scanned today)")
        elif age_days == 1:
            print("Using cached projects (scanned yesterday)")
        else:
            print(f"Using cached projects (scanned {age_days} days ago)")
        return [Path(p) for p in cache.projects]

    if cache and not _is_cache_valid(cfg, cache):
        if cache.repos_root != str(cfg.repos_root):
            print("Cache invalidated: repos_root changed")
        else:
            print("Cache expired: performing fresh scan")

    print("Scanning for projects...")
    projects = _scan_projects(cfg)

    new_cache = ProjectCache(
        repos_root=str(cfg.repos_root),
        last_scan=time.time(),
        projects=[str(p) for p in projects],
    )
    _write_cache(cfg, new_cache)
    print(f"Found {len(projects)} project(s). Cache updated.")

    return projects


def discover_specs(project_path: Path, cfg: Config) -> list[tuple[str, Path]]:
    """List specs for the selected project."""
    specs_root = project_path / cfg.spec_workflow_dir_name / cfg.specs_subdir
    if not specs_root.exists():
        raise FileNotFoundError(f"No specs directory at {specs_root}")
    specs: list[tuple[str, Path]] = []
    for child in sorted(specs_root.iterdir()):
        if child.is_dir():
            specs.append((child.name, child))
    return specs


TASK_PATTERN = re.compile(
    r"^-\s\[(?P<state>[ x-])\]",
    re.MULTILINE | re.IGNORECASE,
)


def read_task_stats(tasks_path: Path) -> TaskStats:
    """Parse task status counts from tasks.md."""
    text = tasks_path.read_text(encoding="utf-8")
    pending = done = in_progress = 0
    for match in TASK_PATTERN.finditer(text):
        state = match.group("state").lower()
        if state == "x":
            done += 1
        elif state == "-":
            in_progress += 1
        else:
            pending += 1
    return TaskStats(done=done, pending=pending, in_progress=in_progress)


def list_unfinished_specs(project: Path, cfg: Config) -> list[tuple[str, Path]]:
    """Return specs with unfinished tasks, sorted by tasks.md modification time (newest first)."""
    unfinished_with_mtime: list[tuple[float, str, Path]] = []
    for name, spec_path in discover_specs(project, cfg):
        tasks_path = spec_path / cfg.tasks_filename
        if not tasks_path.exists():
            continue
        stats = read_task_stats(tasks_path)
        if stats.total == 0:
            continue
        if stats.done < stats.total:
            mtime = tasks_path.stat().st_mtime
            unfinished_with_mtime.append((mtime, name, spec_path))

    # Sort by modification time (newest first)
    unfinished_with_mtime.sort(key=lambda x: x[0], reverse=True)

    # Return without the timestamp
    return [(name, spec_path) for _, name, spec_path in unfinished_with_mtime]


def display_spec_queue(project: Path, cfg: Config) -> None:
    """Display all specs with indices, timestamps, and completion status."""
    from datetime import datetime

    # Get all specs first
    all_specs = discover_specs(project, cfg)

    # Build list with metadata
    specs_with_metadata: list[tuple[int, str, Path, float, bool]] = []
    for idx, (name, spec_path) in enumerate(all_specs, start=1):
        tasks_path = spec_path / cfg.tasks_filename
        
        if tasks_path.exists():
            mtime = tasks_path.stat().st_mtime
            stats = read_task_stats(tasks_path)
            has_work = stats.total > 0 and stats.done < stats.total
        else:
            mtime = 0.0
            has_work = False

        specs_with_metadata.append((idx, name, spec_path, mtime, has_work))

    # Sort by modification time (newest first) but keep original indices
    unfinished = [(idx, name, path, mtime) for idx, name, path, mtime, has_work
                  in specs_with_metadata if has_work]
    unfinished.sort(key=lambda x: x[3], reverse=True)  # Sort by mtime descending

    if not unfinished:
        print("\n✓ No unfinished specs found. All specs are complete!")
        return

    print(f"\n{'='*90}")
    print(f"Unfinished Specs Queue (sorted by last active, newest first)")
    print(f"{'='*90}")
    print(f"{'#':<6}{'Spec Name':<40}{'Status':<25}{'Last Active'}")
    print(f"{'-'*90}")

    for idx, name, spec_path, mtime in unfinished:
        tasks_path = spec_path / cfg.tasks_filename
        stats = read_task_stats(tasks_path)
        last_active = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")
        status = f"{stats.done}/{stats.total} tasks ({stats.in_progress} in progress)"
        print(f"{idx:<6}{name:<40}{status:<25}{last_active}")

    print(f"{'-'*90}")
    print(f"Total: {len(unfinished)} unfinished spec(s)")
    print(f"\nTip: Use indices like '1,3,5' to select multiple specs in custom order\n")


def _is_filter_string(text: str) -> bool:
    """Check if text is a valid filter string (folder-safe characters)."""
    return bool(re.match(r"^[a-zA-Z_\-]+$", text))


def _display_menu(title: str, filtered_options: Sequence[T], label: Callable[[T], str], current_filter: str) -> None:
    """Display the menu with current filter."""
    filter_info = f" [filter: '{current_filter}']" if current_filter else ""
    print(f"\n{title}{filter_info}")
    for idx, option in enumerate(filtered_options, start=1):
        print(f"  {idx}. {label(option)}")
    if not filtered_options:
        print("  (no matches)")


def _build_prompt(current_filter: str, allow_quit: bool) -> str:
    """Build the interactive prompt string."""
    prompt = "Select # or filter text"
    if current_filter:
        prompt += " (Enter to reset)"
    if allow_quit:
        prompt += " (q to quit)"
    prompt += ": "
    return prompt


def choose_option(
    title: str,
    options: Sequence[T],
    label: Callable[[T], str],
    *,
    allow_quit: bool = True,
) -> T:
    """Display a simple numeric menu and return the selected item.

    Supports filtering:
    - Enter text to filter options by partial match
    - Press Enter (empty) to reset filter
    - Enter number to select from current list
    """
    if not options:
        raise ValueError(f"No options available for {title}")

    current_filter = ""
    filtered_options: Sequence[T] = options

    while True:
        _display_menu(title, filtered_options, label, current_filter)
        choice = input(_build_prompt(current_filter, allow_quit)).strip()

        if allow_quit and choice.lower() in {"q", "quit"}:
            raise KeyboardInterrupt("User cancelled selection")

        if choice == "":
            current_filter = ""
            filtered_options = options
            continue

        if _is_filter_string(choice):
            current_filter = choice.lower()
            filtered_options = [opt for opt in options if current_filter in label(opt).lower()]
            continue

        try:
            numeric = int(choice)
        except ValueError:
            print("Invalid input. Use text to filter or number to select.")
            continue

        if 1 <= numeric <= len(filtered_options):
            return filtered_options[numeric - 1]
        print("Choice out of range, try again.")
