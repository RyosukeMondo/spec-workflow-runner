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

from .subprocess_helpers import run_command

if TYPE_CHECKING:
    from .providers import Provider

T = TypeVar("T")


class RunnerError(Exception):
    """Raised when the run needs to abort early."""


def is_rate_limit_error(error_message: str) -> bool:
    """Detect if an error is due to rate limit/quota exceeded.

    Checks for common rate limit patterns from different LLM providers:
    - Claude: "hit your limit", "rate limit", "too many requests"
    - OpenAI: "rate_limit_exceeded", "quota exceeded"
    - Gemini: "RESOURCE_EXHAUSTED" (rate-related)

    Args:
        error_message: The error message string to check

    Returns:
        True if the error is a rate limit error, False otherwise
    """
    error_lower = error_message.lower()

    # Rate limit patterns
    if "hit your limit" in error_lower:
        return True
    if "rate limit" in error_lower:
        return True
    if "rate_limit" in error_lower:
        return True
    if "too many requests" in error_lower:
        return True
    if "quota exceeded" in error_lower:
        return True
    if "429" in error_message:  # HTTP 429 Too Many Requests
        return True

    return False


def is_context_limit_error(error_message: str) -> bool:
    """Detect if an error is due to context limit/window exceeded.

    Checks for common error patterns from different LLM providers:
    - Claude: "context limit", "exceed context", "context window", "prompt is too long"
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
    if "prompt is too long" in error_lower:
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


def is_timeout_error(error_message: str) -> bool:
    """Detect if an error is due to iteration timeout.

    Args:
        error_message: The error message string to check

    Returns:
        True if the error is a timeout error, False otherwise
    """
    error_lower = error_message.lower()
    return "timed out after" in error_lower or "timeout exceeded" in error_lower


def is_no_messages_error(error_message: str) -> bool:
    """Detect if an error is the Claude CLI 'No messages returned' error.

    This error often occurs when Claude completes successfully but doesn't output
    anything, or when there's a transient CLI issue. It should be treated as
    potentially successful (check for commits) rather than a hard failure.

    Args:
        error_message: The error message string to check

    Returns:
        True if the error is a 'No messages returned' error, False otherwise
    """
    error_lower = error_message.lower()
    return "no messages returned" in error_lower


def reduce_spec_context(project_path: Path, spec_name: str, cfg: Config) -> bool:
    """Reduce context size by archiving implementation logs and updating .claudeignore.

    Args:
        project_path: Path to the project root
        spec_name: Name of the spec
        cfg: Configuration object

    Returns:
        True if context was reduced, False if no logs to archive
    """
    import logging
    import shutil

    logger = logging.getLogger(__name__)

    spec_dir = project_path / cfg.spec_workflow_dir_name / cfg.specs_subdir / spec_name
    impl_logs_dir = spec_dir / "Implementation Logs"

    if not impl_logs_dir.exists():
        return False

    # Check if there are any logs to archive
    log_files = list(impl_logs_dir.glob("*.md"))
    if not log_files:
        return False

    # Create archive directory
    archive_dir = project_path / cfg.spec_workflow_dir_name / "archived-logs" / spec_name
    archive_dir.mkdir(parents=True, exist_ok=True)

    # Move all logs to archive
    moved_count = 0
    for log_file in log_files:
        try:
            shutil.move(str(log_file), str(archive_dir / log_file.name))
            moved_count += 1
        except Exception as e:
            logger.warning(f"Failed to archive {log_file.name}: {e}")

    logger.info(f"Archived {moved_count} implementation logs to {archive_dir}")

    # Create README in Implementation Logs directory
    readme_path = impl_logs_dir / "README.md"
    readme_path.write_text(
        "# Archived Implementation Logs\n\n"
        "These logs have been moved to reduce context size for the AI runner.\n"
        f"Original logs are in: .spec-workflow/archived-logs/{spec_name}/\n"
    )

    # Update or create .claudeignore
    claudeignore_path = project_path / ".claudeignore"
    ignore_patterns = {
        ".spec-workflow/specs/*/Implementation Logs/",
        ".spec-workflow/archived-logs/",
        "logs/",
    }

    existing_patterns = set()
    if claudeignore_path.exists():
        existing_patterns = set(line.strip() for line in claudeignore_path.read_text().splitlines() if line.strip())

    new_patterns = ignore_patterns - existing_patterns
    if new_patterns:
        with claudeignore_path.open("a") as f:
            if existing_patterns:
                f.write("\n")
            for pattern in sorted(new_patterns):
                f.write(f"{pattern}\n")
        logger.info(f"Updated .claudeignore with {len(new_patterns)} new patterns")

    return True


def get_current_commit(repo_path: Path) -> str:
    """Return the current HEAD commit id for the repo."""
    result = run_command(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_path,
        check=True,
    )
    return result.stdout.strip()


def has_uncommitted_changes(repo_path: Path) -> bool:
    """Check if there are uncommitted changes (staged or unstaged)."""
    result = run_command(
        ["git", "status", "--porcelain"],
        cwd=repo_path,
        check=True,
    )
    return bool(result.stdout.strip())


def _install_mcp_server(provider: Provider, project_path: Path, cfg: Config) -> None:
    """Install spec-workflow MCP server for the provider.

    Args:
        provider: Provider instance
        project_path: Path to project directory
        cfg: Configuration object with MCP settings
    """
    import logging

    logger = logging.getLogger(__name__)

    server_name = cfg.mcp_server_name
    package = cfg.mcp_package

    # Install MCP server automatically
    add_cmd = provider.get_mcp_add_command(server_name, package)
    command = add_cmd.to_list()

    logger.info(f"Installing MCP server: {' '.join(command)}")
    print(f"\n📦 Auto-installing spec-workflow MCP server for {provider.get_provider_name()}...")

    try:
        result = run_command(
            command,
            cwd=project_path,
            check=False,
        )

        if result.returncode != 0:
            raise RunnerError(
                f"Failed to install spec-workflow MCP server.\n"
                f"   Command: {' '.join(command)}\n"
                f"   Error: {result.stderr.strip()}"
            )

        print(f"[OK] spec-workflow MCP server installed successfully for {provider.get_provider_name()}")
        logger.info("MCP server installation completed successfully")

    except Exception as err:
        raise RunnerError(f"Failed to install spec-workflow MCP server: {err}") from err


def check_clean_working_tree(repo_path: Path) -> None:
    """Check working tree status and warn if uncommitted changes exist.

    Args:
        repo_path: Path to git repository
    """
    if not has_uncommitted_changes(repo_path):
        return

    print("\n[!]  Warning: Uncommitted changes detected in the repository.")
    print("   Commit detection may be unreliable during this run.")


def check_mcp_server_exists(
    provider: Provider,
    project_path: Path,
    cfg: Config,
) -> None:
    """Ensure spec-workflow MCP server is configured for the provider.

    Auto-installs the MCP server if not found.

    Args:
        provider: Provider instance
        project_path: Path to project directory
        cfg: Configuration object with MCP settings
    """
    mcp_cmd = provider.get_mcp_list_command()
    command = mcp_cmd.to_list()
    server_name = cfg.mcp_server_name

    try:
        result = run_command(
            command,
            cwd=project_path,
            check=False,
        )

        if result.returncode != 0:
            print(f"\n[!]  Warning: Could not list MCP servers for {provider.get_provider_name()}.")
            print(f"   Command failed: {' '.join(command)}")
            print(f"   Error: {result.stderr.strip()}")
            print(f"\n   Task tracking may not work properly without the {server_name} MCP server.")
            return

        output = result.stdout.lower()
        if server_name.lower() not in output:
            # MCP server not found - auto-install
            _install_mcp_server(provider, project_path, cfg)
            return

        print(f"[OK] {server_name} MCP server detected for {provider.get_provider_name()}")

    except FileNotFoundError as err:
        executable = provider.get_mcp_list_command().executable
        raise RunnerError(
            f"{executable} command not found.\n"
            f"   Please ensure {provider.get_provider_name()} is installed and available in PATH."
        ) from err


def get_active_claude_account() -> str | None:
    """Get the currently active Claude account name.

    Returns:
        The name of the active account, or None if not found.
    """
    try:
        result = run_command(
            ["claude-account"],
            check=False,
        )
        if result.returncode == 0:
            return result.stdout.strip()
        return None
    except FileNotFoundError:
        return None


def rotate_claude_account() -> bool:
    """Rotate to the next available Claude account.

    Runs 'claude-rotate' command to switch to the next authenticated account.

    Returns:
        True if rotation was successful, False otherwise.
    """
    import logging

    logger = logging.getLogger(__name__)

    try:
        result = run_command(
            ["claude-rotate"],
            check=False,
        )

        if result.returncode == 0:
            new_account = get_active_claude_account()
            logger.info(f"Rotated to Claude account: {new_account}")
            print(f"✓ Rotated to Claude account: {new_account}")
            return True

        logger.warning(f"Failed to rotate Claude account: {result.stderr.strip()}")
        print(f"[!]  Failed to rotate Claude account: {result.stderr.strip()}")
        return False

    except FileNotFoundError:
        logger.info(
            "claude-rotate command not found. "
            "Install it to enable automatic account rotation for rate limit handling. "
            "See: https://github.com/anthropics/claude-code#account-rotation"
        )
        return False


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
    activity_timeout_seconds: int = 300
    activity_check_interval_seconds: int = 300
    mcp_server_name: str = "spec-workflow"
    mcp_package: str = "npx @pimzino/spec-workflow-mcp@latest"

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
        activity_timeout_seconds = int(payload.get("activity_timeout_seconds", 300))
        activity_check_interval_seconds = int(payload.get("activity_check_interval_seconds", 300))

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
        if activity_timeout_seconds <= 0:
            raise ValueError(
                f"activity_timeout_seconds must be positive, got {activity_timeout_seconds}"
            )
        if activity_check_interval_seconds <= 0:
            raise ValueError(
                f"activity_check_interval_seconds must be positive, got {activity_check_interval_seconds}"
            )

        # MCP config: env vars take precedence over config.json, with defaults
        mcp_server_name = os.environ.get(
            "MCP_SERVER_NAME",
            payload.get("mcp_server_name", "spec-workflow"),
        )
        mcp_package = os.environ.get(
            "MCP_PACKAGE",
            payload.get("mcp_package", "npx @pimzino/spec-workflow-mcp@latest"),
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
            activity_timeout_seconds=activity_timeout_seconds,
            activity_check_interval_seconds=activity_check_interval_seconds,
            mcp_server_name=mcp_server_name,
            mcp_package=mcp_package,
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

    # Only count tasks in the "## Tasks" section
    # Stop counting at "## Task Validation Checklist" or similar
    tasks_section_start = text.find("## Tasks")
    if tasks_section_start == -1:
        # Fallback: use entire file if no Tasks section found
        task_text = text
    else:
        # Find the end of Tasks section (next ## heading or end of file)
        task_text_start = tasks_section_start + len("## Tasks")
        next_section = text.find("\n## ", task_text_start)
        if next_section == -1:
            task_text = text[tasks_section_start:]
        else:
            task_text = text[tasks_section_start:next_section]

    pending = done = in_progress = 0
    for match in TASK_PATTERN.finditer(task_text):
        state = match.group("state").lower()
        if state == "x":
            done += 1
        elif state == "-":
            in_progress += 1
        else:
            pending += 1
    return TaskStats(done=done, pending=pending, in_progress=in_progress)


def list_unfinished_specs(project: Path, cfg: Config) -> list[tuple[str, Path]]:
    """Return specs with unfinished tasks, sorted by requirements.md creation time (oldest first)."""
    unfinished_with_ctime: list[tuple[float, str, Path]] = []
    for name, spec_path in discover_specs(project, cfg):
        tasks_path = spec_path / cfg.tasks_filename
        if not tasks_path.exists():
            continue
        stats = read_task_stats(tasks_path)
        if stats.total == 0:
            continue
        if stats.done < stats.total:
            # Use requirements.md creation time, fallback to directory creation time
            requirements_path = spec_path / "requirements.md"
            if requirements_path.exists():
                ctime = requirements_path.stat().st_ctime
            else:
                ctime = spec_path.stat().st_ctime
            unfinished_with_ctime.append((ctime, name, spec_path))

    # Sort by creation time (oldest first)
    unfinished_with_ctime.sort(key=lambda x: x[0])

    # Return without the timestamp
    return [(name, spec_path) for _, name, spec_path in unfinished_with_ctime]


def display_spec_queue(project: Path, cfg: Config) -> None:
    """Display all specs with indices, timestamps, and completion status."""
    from datetime import datetime

    # Get all specs first
    all_specs = discover_specs(project, cfg)

    # Build list with metadata
    specs_with_metadata: list[tuple[int, str, Path, float, bool]] = []
    for idx, (name, spec_path) in enumerate(all_specs, start=1):
        tasks_path = spec_path / cfg.tasks_filename
        # Use requirements.md creation time, fallback to directory creation time
        requirements_path = spec_path / "requirements.md"
        if requirements_path.exists():
            ctime = requirements_path.stat().st_ctime
        else:
            ctime = spec_path.stat().st_ctime

        if tasks_path.exists():
            stats = read_task_stats(tasks_path)
            has_work = stats.total > 0 and stats.done < stats.total
        else:
            has_work = False

        specs_with_metadata.append((idx, name, spec_path, ctime, has_work))

    # Sort by creation time (oldest first) but keep original indices
    unfinished = [(idx, name, path, ctime) for idx, name, path, ctime, has_work
                  in specs_with_metadata if has_work]
    unfinished.sort(key=lambda x: x[3])  # Sort by ctime

    if not unfinished:
        print("\n✓ No unfinished specs found. All specs are complete!")
        return

    print(f"\n{'='*90}")
    print(f"Unfinished Specs Queue (sorted by creation time, oldest first)")
    print(f"{'='*90}")
    print(f"{'#':<6}{'Spec Name':<40}{'Status':<25}{'Created'}")
    print(f"{'-'*90}")

    for idx, name, spec_path, ctime in unfinished:
        tasks_path = spec_path / cfg.tasks_filename
        stats = read_task_stats(tasks_path)
        created_date = datetime.fromtimestamp(ctime).strftime("%Y-%m-%d %H:%M")
        status = f"{stats.done}/{stats.total} tasks ({stats.in_progress} in progress)"
        print(f"{idx:<6}{name:<40}{status:<25}{created_date}")

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
