"""Interactive runner that loops through spec-workflow tasks via AI providers."""

from __future__ import annotations

import argparse
import logging
import os
import subprocess
import sys
import textwrap
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import TextIO

from .providers import ClaudeProvider, Provider, create_provider, get_supported_models
from .subprocess_helpers import format_command_string, popen_command
from .utils import (
    Config,
    RunnerError,
    TaskStats,
    check_clean_working_tree,
    check_mcp_server_exists,
    choose_option,
    discover_projects,
    discover_specs,
    display_spec_queue,
    get_active_claude_account,
    get_current_commit,
    has_uncommitted_changes,
    is_context_limit_error,
    is_rate_limit_error,
    list_unfinished_specs,
    load_config,
    read_task_stats,
    reduce_spec_context,
    rotate_claude_account,
)

logger = logging.getLogger(__name__)


class AllSpecsSentinel:
    """Marker object representing the 'run all specs' selection."""


class MultipleSpecsSentinel:
    """Marker object representing multiple selected specs."""

    def __init__(self, specs: list[tuple[str, Path]]) -> None:
        self.specs = specs


class PollPendingTasksSentinel:
    """Marker object representing the 'poll for pending tasks' selection."""


ALL_SPECS_SENTINEL = AllSpecsSentinel()
POLL_PENDING_TASKS_SENTINEL = PollPendingTasksSentinel()
SpecOption = tuple[str, Path] | AllSpecsSentinel | MultipleSpecsSentinel | PollPendingTasksSentinel


def parse_args() -> argparse.Namespace:
    """Return CLI arguments for the runner."""
    parser = argparse.ArgumentParser(
        description="Run AI provider against remaining spec tasks until finished.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path.cwd() / "config.json",
        help="Path to config.json (default: ./config.json).",
    )
    parser.add_argument(
        "--project",
        type=Path,
        help="Optional project path to skip project selection.",
    )
    parser.add_argument(
        "--spec",
        type=str,
        help="Optional spec name to skip spec selection.",
    )
    parser.add_argument(
        "--provider",
        type=str,
        choices=["claude", "codex", "gemini"],
        help="AI provider to use (prompts if not specified).",
    )
    parser.add_argument(
        "--model",
        type=str,
        help=(
            "AI model to use (prompts if not specified). "
            "Codex: gpt-5.1-codex-max, gpt-5.1-codex, etc. "
            "Claude: sonnet, haiku, opus. "
            "Gemini: gemini-3-pro-preview, gemini-2.5-pro, gemini-2.5-flash."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Skip execution; useful for smoke testing.",
    )
    parser.add_argument(
        "--refresh-cache",
        action="store_true",
        help="Force refresh of project cache, ignoring existing cache.",
    )
    return parser.parse_args()


def ensure_spec(project: Path, cfg: Config, spec_name: str | None) -> tuple[str, Path]:
    """Return the spec name and directory, optionally prompting the user."""
    specs = discover_specs(project, cfg)
    if spec_name:
        for candidate, path in specs:
            if candidate == spec_name:
                return candidate, path
        raise RunnerError(f"Spec '{spec_name}' not found under {project}")
    name, spec_path = choose_option(
        f"Select spec within {project}",
        specs,
        label=lambda pair: pair[0],
    )
    return name, spec_path


def _label_option(option: SpecOption) -> str:
    if isinstance(option, AllSpecsSentinel):
        return "All unfinished specs"
    if isinstance(option, MultipleSpecsSentinel):
        return "Multiple specs (custom order)"
    if isinstance(option, PollPendingTasksSentinel):
        return "Poll for pending tasks"
    return option[0]


def _parse_spec_indices(input_str: str, specs: list[tuple[str, Path]]) -> list[tuple[str, Path]]:
    """Parse comma-separated indices and return selected specs in order."""
    try:
        indices = [int(idx.strip()) for idx in input_str.split(",")]
    except ValueError:
        raise RunnerError(f"Invalid index format: '{input_str}'. Use comma-separated numbers like '1,3,5'")

    selected = []
    for idx in indices:
        if idx < 1 or idx > len(specs):
            raise RunnerError(f"Index {idx} out of range (1-{len(specs)})")
        selected.append(specs[idx - 1])

    return selected


def _choose_spec_or_all(
    project: Path,
    cfg: Config,
    spec_name: str | None,
) -> SpecOption:
    """Return either a spec tuple, ALL_SPECS_SENTINEL, MultipleSpecsSentinel, or PollPendingTasksSentinel."""
    specs = discover_specs(project, cfg)
    if spec_name:
        if spec_name.lower() == "all":
            return ALL_SPECS_SENTINEL
        if spec_name.lower() == "poll":
            return POLL_PENDING_TASKS_SENTINEL
        # Check if it's comma-separated indices like "1,3,5"
        if "," in spec_name:
            selected_specs = _parse_spec_indices(spec_name, specs)
            return MultipleSpecsSentinel(selected_specs)
        # Single spec by name
        for candidate, path in specs:
            if candidate == spec_name:
                return candidate, path
        raise RunnerError(f"Spec '{spec_name}' not found under {project}")

    # Interactive selection
    print(f"\nAvailable specs in {project}:")
    for idx, (name, _) in enumerate(specs, start=1):
        print(f"  {idx}. {name}")
    print("\nOptions:")
    print("  - Enter 'all' for all unfinished specs (sorted by creation time)")
    print("  - Enter 'poll' to poll every 10s until pending tasks are found")
    print("  - Enter a single number (e.g., '3') for one spec")
    print("  - Enter comma-separated numbers (e.g., '2,5,1') for custom order")
    print("  - Enter spec name directly")

    choice = input("\nYour choice: ").strip()

    if choice.lower() == "all":
        return ALL_SPECS_SENTINEL

    if choice.lower() == "poll":
        return POLL_PENDING_TASKS_SENTINEL

    # Check if it's comma-separated indices
    if "," in choice:
        selected_specs = _parse_spec_indices(choice, specs)
        return MultipleSpecsSentinel(selected_specs)

    # Check if it's a single index
    try:
        idx = int(choice)
        if 1 <= idx <= len(specs):
            return specs[idx - 1]
        raise RunnerError(f"Index {idx} out of range (1-{len(specs)})")
    except ValueError:
        pass

    # Try as spec name
    for candidate, path in specs:
        if candidate == choice:
            return candidate, path

    raise RunnerError(f"Invalid selection: '{choice}'")


def poll_for_pending_tasks(project: Path, cfg: Config) -> None:
    """Poll every 10 seconds until specs with pending tasks are found."""
    print("\n🔍 Polling for specs with pending tasks every 10 seconds...")
    print("Press Ctrl+C to stop polling.\n")

    poll_count = 0
    while True:
        poll_count += 1
        current_time = datetime.now().strftime("%H:%M:%S")
        print(f"[{current_time}] Poll #{poll_count}: Checking for pending tasks...")

        unfinished = list_unfinished_specs(project, cfg)
        if unfinished:
            print(f"\n✓ Found {len(unfinished)} spec(s) with pending tasks!")
            for idx, (name, spec_path) in enumerate(unfinished, start=1):
                tasks_path = spec_path / cfg.tasks_filename
                stats = read_task_stats(tasks_path)
                print(f"  {idx}. {name} - {stats.summary()}")
            return

        print("  No pending tasks found. Waiting 10 seconds...")
        time.sleep(10)


def run_multiple_specs(
    provider: Provider,
    cfg: Config,
    project: Path,
    specs: list[tuple[str, Path]],
    dry_run: bool,
) -> None:
    """Run multiple specs in the specified order."""
    if dry_run:
        print("\n[DRY-RUN MODE] Selected specs in order:")
        print(f"{'='*90}")
        print(f"{'#':<6}{'Spec Name':<40}{'Status':<25}{'Created'}")
        print(f"{'-'*90}")

        for idx, (name, spec_path) in enumerate(specs, start=1):
            tasks_path = spec_path / cfg.tasks_filename
            if tasks_path.exists():
                stats = read_task_stats(tasks_path)
                ctime = spec_path.stat().st_ctime
                created_date = datetime.fromtimestamp(ctime).strftime("%Y-%m-%d %H:%M")
                status = f"{stats.done}/{stats.total} tasks ({stats.in_progress} in progress)"
            else:
                created_date = "N/A"
                status = "No tasks.md found"
            print(f"{idx:<6}{name:<40}{status:<25}{created_date}")

        print(f"{'-'*90}")
        print(f"Total: {len(specs)} spec(s) will be processed in this order\n")
        return

    print(f"\nRunning {len(specs)} specs in specified order...")
    for idx, (spec_name, spec_path) in enumerate(specs, start=1):
        print(f"\n{'='*90}")
        print(f"Processing spec {idx}/{len(specs)}: '{spec_name}'")
        print(f"{'='*90}")
        run_loop(provider, cfg, project, spec_name, spec_path, dry_run)
        print(f"✓ Completed spec '{spec_name}' ({idx}/{len(specs)})")


def run_all_specs(
    provider: Provider,
    cfg: Config,
    project: Path,
    dry_run: bool,
) -> None:
    """Sequentially run provider for every unfinished spec, polling every 10 minutes when all complete."""
    if dry_run:
        print("\n[DRY-RUN MODE] Displaying spec queue without executing...")
        display_spec_queue(project, cfg)
        print("\n[DRY-RUN MODE] Would continuously poll every 10 minutes for new specs after all tasks complete.")
        return

    print("\nRunning unfinished specs in sequence.")
    print("Will poll every 10 minutes for new specs when all tasks are complete.\n")

    while True:
        unfinished = list_unfinished_specs(project, cfg)
        if not unfinished:
            current_time = datetime.now().strftime("%H:%M:%S")
            print(f"\n[{current_time}] No unfinished specs remaining. All caught up!")
            print("Polling every 10 minutes for new specs. Press Ctrl+C to stop.")
            time.sleep(600)  # 10 minutes = 600 seconds
            continue
        spec_name, spec_path = unfinished[0]
        print(f"\n==> Processing spec '{spec_name}'")
        run_loop(provider, cfg, project, spec_name, spec_path, dry_run)


def ensure_project(cfg: Config, explicit_path: Path | None, refresh_cache: bool) -> Path:
    """Resolve the project directory."""
    if explicit_path:
        return explicit_path.resolve()
    projects = discover_projects(cfg, force_refresh=refresh_cache)
    return choose_option(
        "Select project",
        projects,
        label=lambda path: f"{path.name}  ({path})",
    )


def ensure_provider(explicit_provider: str | None) -> str:
    """Resolve the provider to use, prompting if not specified."""
    if explicit_provider:
        return explicit_provider
    providers = [
        ("codex", "Codex with MCP server support"),
        ("claude", "Claude CLI (automation mode, no prompts)"),
        ("gemini", "Google Gemini CLI (maximum risk/efficiency mode)"),
    ]
    return choose_option(
        "Select AI provider",
        providers,
        label=lambda pair: f"{pair[0]:8} - {pair[1]}",
    )[0]


def ensure_model(provider_name: str, explicit_model: str | None) -> str | None:
    """Resolve the model to use for the provider, prompting if not specified."""
    if explicit_model:
        return explicit_model

    supported_models = get_supported_models(provider_name)
    model_descriptions = {
        "gpt-5.1-codex-max": "Latest frontier agentic coding model (recommended)",
        "gpt-5.1-codex": "Reasoning model with strong performance",
        "gpt-5.1-codex-mini": "Smaller, cost-effective version",
        "gpt-5-codex": "Previous generation model",
        "sonnet": "Latest Sonnet - best coding model (recommended)",
        "haiku": "Fast and cost-effective (3x cheaper, 2x faster)",
        "opus": "Most intelligent for complex tasks",
        "gemini-3-pro-preview": "Gemini 3 Pro - Most intelligent, state-of-the-art (recommended)",
        "gemini-3-flash-preview": "Gemini 3 Flash - Fast preview with high intelligence",
        "gemini-2.5-pro": "Gemini 2.5 Pro - 1M token context, advanced reasoning",
        "gemini-2.5-flash": "Gemini 2.5 Flash - Lightning-fast, high capability",
        "gemini-2.5-flash-lite": "Gemini 2.5 Flash Lite - Ultra-fast, lightweight",
        "gemini-2.0-flash-exp": "Gemini 2.0 Flash Experimental - Latest experimental features",
        "gemini-1.5-pro": "Gemini 1.5 Pro - Stable, proven performance",
        "gemini-1.5-flash": "Gemini 1.5 Flash - Fast and reliable",
        "gemini-1.5-flash-8b": "Gemini 1.5 Flash 8B - Compact, efficient model",
    }

    models_with_desc = [(model, model_descriptions.get(model, "")) for model in supported_models]

    return choose_option(
        f"Select model for {provider_name}",
        models_with_desc,
        label=lambda pair: f"{pair[0]:20} - {pair[1]}" if pair[1] else pair[0],
    )[0]


def build_prompt(cfg: Config, spec_name: str, stats: TaskStats) -> str:
    """Format the codex prompt using the config template."""
    remaining = stats.total - stats.done
    context = {
        "spec_name": spec_name,
        "tasks_total": stats.total,
        "tasks_done": stats.done,
        "tasks_remaining": remaining,
        "tasks_in_progress": stats.in_progress,
        "timestamp": datetime.now(UTC).isoformat(),
    }
    return cfg.prompt_template.format(**context)


def _build_log_header(iteration: int, spec_name: str, command: list[str], prompt: str) -> str:
    """Build the log file header with metadata."""
    started = datetime.now(UTC).isoformat()
    formatted_command = format_command_string(command)
    return textwrap.dedent(
        f"""\
        # Iteration {iteration}
        # Started {started}
        # Spec {spec_name}
        # Command
        {formatted_command}

        # Prompt
        {prompt}

        # Output (stdout + stderr)
        """
    )


def _write_dry_run_log(log_path: Path, header: str, command: str) -> None:
    """Write a dry-run simulation to the log file."""
    simulated = f"[dry-run] Would run: {command}\n"
    with log_path.open("w", encoding="utf-8") as handle:
        handle.write(header)
        handle.write(simulated)
        handle.write("# Exit Code\n0\n")
    print(simulated.strip())
    print(f"Saved log: {log_path}")


def _execute_provider_command(command: list[str], project_path: Path, header: str, log_path: Path) -> None:
    """Execute provider command and stream output to log."""
    formatted_command = format_command_string(command)
    print("\nRunning:", formatted_command)

    output_lines: list[str] = []
    with log_path.open("w", encoding="utf-8") as handle:
        handle.write(header)
        proc = popen_command(
            command,
            cwd=project_path,
            stdout=subprocess.PIPE,
            clean_claude_env=True,
            env_additions={"PYTHONUNBUFFERED": "1"},
        )
        assert proc.stdout is not None
        for line in iter(proc.stdout.readline, b""):
            decoded = line.decode("utf-8", errors="replace")
            print(decoded, end="")
            handle.write(decoded)
            handle.flush()
            output_lines.append(decoded)
        proc.wait()
        handle.write(f"\n# Exit Code\n{proc.returncode}\n")

    if proc.returncode != 0:
        # Include output in error message for better error detection
        output_text = "".join(output_lines)
        raise RunnerError(f"Provider command failed. Output: {output_text}")
    print(f"Saved log: {log_path}")


def run_provider(
    provider: Provider,
    cfg: Config,
    project_path: Path,
    prompt: str,
    dry_run: bool,
    *,
    spec_name: str,
    iteration: int,
    log_path: Path,
) -> None:
    """Execute the provider command and stream output into a log file."""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    provider_cmd = provider.build_command(prompt, project_path, cfg.codex_config_overrides)
    command = provider_cmd.to_list()
    header = _build_log_header(iteration, spec_name, command, prompt)
    formatted_command = format_command_string(command)

    if dry_run:
        _write_dry_run_log(log_path, header, formatted_command)
        return

    # Retry loop with exponential backoff
    last_error: Exception | None = None
    attempt = 1
    starting_claude_account: str | None = None  # Track starting account for rotation cycle

    while True:
        try:
            _execute_provider_command(command, project_path, header, log_path)
            if attempt > 1:
                logger.info(
                    "Provider command succeeded on retry",
                    extra={
                        "extra_context": {
                            "attempt": attempt,
                            "spec_name": spec_name,
                            "iteration": iteration,
                        }
                    },
                )
            return  # Success - exit retry loop
        except RunnerError as err:
            last_error = err

            # Check error type
            error_message = str(err)
            is_rate_error = is_rate_limit_error(error_message)
            is_context_error = is_context_limit_error(error_message)

            # Handle rate limit errors
            if is_rate_error:
                logger.warning(
                    "Rate limit exceeded, waiting before retry",
                    extra={
                        "extra_context": {
                            "attempt": attempt,
                            "spec_name": spec_name,
                            "iteration": iteration,
                            "error": error_message,
                        }
                    },
                )

                # For Claude provider: try rotating accounts
                if isinstance(provider, ClaudeProvider):
                    if starting_claude_account is None:
                        starting_claude_account = get_active_claude_account()
                        logger.info(f"Tracking starting Claude account: {starting_claude_account}")

                    print("⚠️  Rate limit exceeded. Rotating Claude account...")
                    if rotate_claude_account():
                        current_account = get_active_claude_account()

                        # Check if we've cycled through all accounts
                        if current_account == starting_claude_account:
                            logger.warning(
                                "All Claude accounts exhausted, waiting before retry",
                                extra={
                                    "extra_context": {
                                        "starting_account": starting_claude_account,
                                        "spec_name": spec_name,
                                        "iteration": iteration,
                                    }
                                },
                            )
                            backoff_seconds = cfg.context_limit_wait_seconds
                            wait_minutes = backoff_seconds // 60
                            print(
                                f"⚠️  All Claude accounts exhausted. "
                                f"Waiting {wait_minutes} minutes ({backoff_seconds}s) before retry..."
                            )
                            time.sleep(backoff_seconds)
                            # Reset starting account for next cycle
                            starting_claude_account = get_active_claude_account()
                        else:
                            logger.info(
                                f"Rotated to Claude account: {current_account}, retrying",
                                extra={
                                    "extra_context": {
                                        "current_account": current_account,
                                        "starting_account": starting_claude_account,
                                        "spec_name": spec_name,
                                        "iteration": iteration,
                                    }
                                },
                            )
                        # Retry with new account
                        continue
                    else:
                        # Rotation failed, fall through to wait
                        print("⚠️  Account rotation not available. Falling back to wait...")

                # For non-Claude providers or if rotation not available: wait before retrying
                backoff_seconds = cfg.context_limit_wait_seconds
                wait_minutes = backoff_seconds // 60
                print(
                    f"⚠️  Rate limit exceeded. "
                    f"Waiting {wait_minutes} minutes ({backoff_seconds}s) before retry..."
                )
                time.sleep(backoff_seconds)
                # Do not increment attempt for rate limits - retry infinitely
                continue

            # Handle context limit errors
            if is_context_error:
                # Try to reduce context by archiving implementation logs
                print("⚠️  Context limit exceeded. Attempting to reduce context...")
                context_reduced = reduce_spec_context(project_path, spec_name, cfg)

                if context_reduced:
                    logger.info(
                        "Context reduced by archiving logs, retrying immediately",
                        extra={
                            "extra_context": {
                                "attempt": attempt,
                                "spec_name": spec_name,
                                "iteration": iteration,
                            }
                        },
                    )
                    print("✓ Context reduced by archiving implementation logs. Retrying...")
                    # Retry immediately after reducing context
                    continue

                # For Claude provider: rotate accounts before waiting
                if isinstance(provider, ClaudeProvider):
                    # Track starting account on first context limit hit
                    if starting_claude_account is None:
                        starting_claude_account = get_active_claude_account()
                        logger.info(f"Tracking starting Claude account: {starting_claude_account}")

                    # Rotate to next account
                    print("⚠️  Context limit exceeded. Rotating Claude account...")
                    if rotate_claude_account():
                        current_account = get_active_claude_account()

                        # Check if we've cycled through all accounts
                        if current_account == starting_claude_account:
                            logger.warning(
                                "All Claude accounts exhausted, waiting before retry",
                                extra={
                                    "extra_context": {
                                        "starting_account": starting_claude_account,
                                        "spec_name": spec_name,
                                        "iteration": iteration,
                                    }
                                },
                            )
                            backoff_seconds = cfg.context_limit_wait_seconds
                            wait_minutes = backoff_seconds // 60
                            print(
                                f"⚠️  All Claude accounts exhausted. "
                                f"Waiting {wait_minutes} minutes ({backoff_seconds}s) before retry..."
                            )
                            time.sleep(backoff_seconds)
                            # Reset starting account for next cycle
                            starting_claude_account = get_active_claude_account()
                        else:
                            logger.info(
                                f"Rotated to Claude account: {current_account}, retrying",
                                extra={
                                    "extra_context": {
                                        "current_account": current_account,
                                        "starting_account": starting_claude_account,
                                        "spec_name": spec_name,
                                        "iteration": iteration,
                                    }
                                },
                            )
                        # Retry with new account
                        continue
                    else:
                        # Rotation failed, fall through to wait
                        print("⚠️  Account rotation failed. Falling back to wait...")

                # For non-Claude providers or if rotation failed: wait before retrying
                backoff_seconds = cfg.context_limit_wait_seconds
                wait_minutes = backoff_seconds // 60
                logger.warning(
                    "Context limit exceeded, waiting before retry",
                    extra={
                        "extra_context": {
                            "attempt": attempt,
                            "max_retries": cfg.max_retries,
                            "wait_seconds": backoff_seconds,
                            "wait_minutes": wait_minutes,
                            "spec_name": spec_name,
                            "iteration": iteration,
                            "error": error_message,
                        }
                    },
                )
                print(
                    f"⚠️  Context limit exceeded (no logs to archive). "
                    f"Waiting {wait_minutes} minutes ({backoff_seconds}s) before retry..."
                )
                time.sleep(backoff_seconds)
                # Do not increment attempt for context limits - retry infinitely
                continue

            if attempt < cfg.max_retries:
                # Calculate exponential backoff for other errors: 2^(attempt-1) seconds
                backoff_seconds = 2 ** (attempt - 1)
                logger.warning(
                    "Provider command failed, retrying with backoff",
                    extra={
                        "extra_context": {
                            "attempt": attempt,
                            "max_retries": cfg.max_retries,
                            "backoff_seconds": backoff_seconds,
                            "spec_name": spec_name,
                            "iteration": iteration,
                            "error": error_message,
                        }
                    },
                )
                print(
                    f"⚠️  Attempt {attempt}/{cfg.max_retries} failed. "
                    f"Retrying in {backoff_seconds}s..."
                )
                time.sleep(backoff_seconds)
                attempt += 1
            else:
                logger.error(
                    "Provider command failed after all retries",
                    extra={
                        "extra_context": {
                            "attempts": attempt,
                            "spec_name": spec_name,
                            "iteration": iteration,
                            "error": str(err),
                        }
                    },
                )
                # All retries exhausted - raise the last error
                raise last_error


def _display_dry_run_spec_status(spec_name: str, spec_path: Path, stats: TaskStats) -> None:
    """Display dry-run status for a single spec."""
    print(f"\n[DRY-RUN MODE] Spec: {spec_name}")
    print(f"{'='*90}")
    print(f"Status: {stats.summary()}")
    print(f"Path: {spec_path}")
    ctime = spec_path.stat().st_ctime
    created_date = datetime.fromtimestamp(ctime).strftime("%Y-%m-%d %H:%M:%S")
    print(f"Created: {created_date}")
    print(f"{'='*90}")
    if stats.done >= stats.total:
        print("✓ All tasks complete. Nothing to run.")
    else:
        print(f"Would run provider to complete {stats.total - stats.done} remaining task(s).")


def _check_commit_progress(
    project_path: Path,
    last_commit: str,
    no_commit_streak: int,
    cfg: Config,
) -> tuple[str, int]:
    """Check for new commits and update streak counter. Returns (new_last_commit, new_streak)."""
    new_commit = get_current_commit(project_path)
    if new_commit != last_commit:
        print(f"Detected new commit: {new_commit}")
        return new_commit, 0

    no_commit_streak += 1
    has_changes = has_uncommitted_changes(project_path)
    if has_changes:
        print(
            f"⚠️  No new commit detected, but uncommitted changes exist! "
            f"Streak: {no_commit_streak}/{cfg.no_commit_limit}"
        )
        print("   The AI may have created/modified files but didn't commit them.")
        print("   Check 'git status' to see what changed.")
    else:
        print(f"No new commit detected. Streak: {no_commit_streak}/{cfg.no_commit_limit}")

    if no_commit_streak >= cfg.no_commit_limit:
        if has_changes:
            raise RunnerError(
                "Circuit breaker: reached consecutive no-commit limit. "
                "Uncommitted changes exist - the AI is not committing as instructed!"
            )
        raise RunnerError("Circuit breaker: reached consecutive no-commit limit.")

    return last_commit, no_commit_streak


def run_loop(
    provider: Provider,
    cfg: Config,
    project_path: Path,
    spec_name: str,
    spec_path: Path,
    dry_run: bool,
) -> None:
    """Main orchestration loop."""
    tasks_path = spec_path / cfg.tasks_filename
    if not tasks_path.exists():
        raise RunnerError(f"tasks.md not found at {tasks_path}")
    stats = read_task_stats(tasks_path)
    if stats.total == 0:
        raise RunnerError("No tasks detected in tasks.md.")
    if dry_run:
        _display_dry_run_spec_status(spec_name, spec_path, stats)
        return

    no_commit_streak = 0
    iteration = 0
    log_dir = project_path / cfg.log_dir_name / spec_name
    last_commit = get_current_commit(project_path)

    while True:
        stats = read_task_stats(tasks_path)
        remaining = stats.total - stats.done
        print(f"\nCurrent status ({spec_name}): {stats.summary()}")
        if remaining <= 0:
            print("All tasks complete. Nothing more to run.")
            return

        iteration += 1
        prompt = build_prompt(cfg, spec_name, stats)
        log_path = log_dir / cfg.log_file_template.format(index=iteration)
        run_provider(
            provider,
            cfg,
            project_path,
            prompt,
            dry_run,
            spec_name=spec_name,
            iteration=iteration,
            log_path=log_path,
        )

        last_commit, no_commit_streak = _check_commit_progress(
            project_path, last_commit, no_commit_streak, cfg
        )


def main() -> int:
    """Script entry point."""
    args = parse_args()
    cfg = load_config(args.config)

    try:
        provider_name = ensure_provider(args.provider)
        model = ensure_model(provider_name, args.model)
        provider = create_provider(provider_name, cfg.codex_command, model)
        project = ensure_project(cfg, args.project, args.refresh_cache)

        if not args.dry_run:
            check_clean_working_tree(project)
            check_mcp_server_exists(provider, project, cfg)

        selection = _choose_spec_or_all(project, cfg, args.spec)
        if isinstance(selection, AllSpecsSentinel):
            run_all_specs(provider, cfg, project, args.dry_run)
        elif isinstance(selection, MultipleSpecsSentinel):
            run_multiple_specs(provider, cfg, project, selection.specs, args.dry_run)
        elif isinstance(selection, PollPendingTasksSentinel):
            if args.dry_run:
                print("\n[DRY-RUN MODE] Would poll for pending tasks every 10 seconds.")
                print("When found, would automatically start executing them.")
            else:
                poll_for_pending_tasks(project, cfg)
                run_all_specs(provider, cfg, project, args.dry_run)
        else:
            spec_name, spec_path = selection
            run_loop(provider, cfg, project, spec_name, spec_path, args.dry_run)
        return 0
    except KeyboardInterrupt:
        print("\nAborted by user.")
        return 130
    except (RunnerError, subprocess.CalledProcessError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
