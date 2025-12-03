"""Interactive runner that loops through spec-workflow tasks via AI providers."""

from __future__ import annotations

import argparse
import os
import shlex
import subprocess
import sys
import textwrap
from datetime import UTC, datetime
from pathlib import Path
from typing import TextIO

from .providers import Provider, create_provider, get_supported_models
from .utils import (
    Config,
    TaskStats,
    choose_option,
    discover_projects,
    discover_specs,
    load_config,
    read_task_stats,
)


class AllSpecsSentinel:
    """Marker object representing the 'run all specs' selection."""


ALL_SPECS_SENTINEL = AllSpecsSentinel()
SpecOption = tuple[str, Path] | AllSpecsSentinel


class RunnerError(Exception):
    """Raised when the run needs to abort early."""


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
        choices=["claude", "codex"],
        help="AI provider to use (prompts if not specified).",
    )
    parser.add_argument(
        "--model",
        type=str,
        help=(
            "AI model to use (prompts if not specified). "
            "Codex: gpt-5.1-codex-max, gpt-5.1-codex, etc. Claude: sonnet, haiku, opus."
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


def check_clean_working_tree(repo_path: Path) -> None:
    """Ensure working tree is clean before starting, prompting user if needed."""
    if not has_uncommitted_changes(repo_path):
        return

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


def check_mcp_server_exists(provider: Provider, project_path: Path) -> None:
    """Ensure spec-workflow MCP server is configured for the provider."""
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
            executable = provider.get_mcp_list_command().executable
            raise RunnerError(
                f"spec-workflow MCP server not found for {provider.get_provider_name()}.\n"
                f"   The spec-workflow MCP server is required for automatic task tracking.\n"
                f"   Please configure it by running: {executable} mcp\n"
                f"   Or check your MCP server configuration."
            )

        print(f"✓ spec-workflow MCP server detected for {provider.get_provider_name()}")

    except FileNotFoundError as err:
        executable = provider.get_mcp_list_command().executable
        raise RunnerError(
            f"{executable} command not found.\n"
            f"   Please ensure {provider.get_provider_name()} is installed and available in PATH."
        ) from err


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
    return option[0]


def _choose_spec_or_all(
    project: Path,
    cfg: Config,
    spec_name: str | None,
) -> SpecOption:
    """Return either a spec tuple or ALL_SPECS_SENTINEL."""
    specs = discover_specs(project, cfg)
    if spec_name:
        if spec_name.lower() == "all":
            return ALL_SPECS_SENTINEL
        for candidate, path in specs:
            if candidate == spec_name:
                return candidate, path
        raise RunnerError(f"Spec '{spec_name}' not found under {project}")

    options: list[SpecOption] = [ALL_SPECS_SENTINEL, *specs]
    return choose_option(f"Select spec within {project}", options, label=_label_option)


def list_unfinished_specs(project: Path, cfg: Config) -> list[tuple[str, Path]]:
    """Return specs with unfinished tasks, sorted by directory creation time (oldest first)."""
    unfinished_with_ctime: list[tuple[float, str, Path]] = []
    for name, spec_path in discover_specs(project, cfg):
        tasks_path = spec_path / cfg.tasks_filename
        if not tasks_path.exists():
            continue
        stats = read_task_stats(tasks_path)
        if stats.total == 0:
            continue
        if stats.done < stats.total:
            ctime = spec_path.stat().st_ctime
            unfinished_with_ctime.append((ctime, name, spec_path))

    # Sort by creation time (oldest first)
    unfinished_with_ctime.sort(key=lambda x: x[0])

    # Return without the timestamp
    return [(name, spec_path) for _, name, spec_path in unfinished_with_ctime]


def run_all_specs(
    provider: Provider,
    cfg: Config,
    project: Path,
    dry_run: bool,
) -> None:
    """Sequentially run provider for every unfinished spec until all complete."""
    print("\nRunning unfinished specs in sequence.")
    while True:
        unfinished = list_unfinished_specs(project, cfg)
        if not unfinished:
            print("No unfinished specs remaining. All caught up!")
            return
        spec_name, spec_path = unfinished[0]
        print(f"\n==> Processing spec '{spec_name}'")
        run_loop(provider, cfg, project, spec_name, spec_path, dry_run)
        if dry_run:
            print("Dry-run mode: processed the first unfinished spec only.")
            return


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
    started = datetime.now(UTC).isoformat()
    formatted_command = " ".join(shlex.quote(part) for part in command)
    header = textwrap.dedent(
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

    def _print_and_log(message: str, handle: TextIO) -> None:
        print(message, end="")
        handle.write(message)
        handle.flush()

    if dry_run:
        simulated = f"[dry-run] Would run: {formatted_command}\n"
        with log_path.open("w", encoding="utf-8") as handle:
            handle.write(header)
            handle.write(simulated)
            handle.write("# Exit Code\n0\n")
        print(simulated.strip())
        print(f"Saved log: {log_path}")
        return

    print("\nRunning:", formatted_command)
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"

    with log_path.open("w", encoding="utf-8") as handle:
        handle.write(header)
        proc = subprocess.Popen(
            command,
            cwd=project_path,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=0,
            env=env,
        )
        assert proc.stdout is not None
        for line in iter(proc.stdout.readline, b""):
            decoded = line.decode("utf-8", errors="replace")
            _print_and_log(decoded, handle)
        proc.wait()
        handle.write(f"\n# Exit Code\n{proc.returncode}\n")

    if proc.returncode != 0:
        raise RunnerError("Provider command failed. See log for details.")
    print(f"Saved log: {log_path}")


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

    no_commit_streak = 0
    iteration = 0
    log_dir = project_path / cfg.log_dir_name / spec_name
    last_commit = get_current_commit(project_path)

    while True:
        stats = read_task_stats(tasks_path)
        if stats.total == 0:
            raise RunnerError("No tasks detected in tasks.md.")
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
        if dry_run:
            print("Dry-run mode: skipping commit checks and exiting after first iteration.")
            return

        new_commit = get_current_commit(project_path)
        if new_commit != last_commit:
            print(f"Detected new commit: {new_commit}")
            no_commit_streak = 0
            last_commit = new_commit
        else:
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
            check_mcp_server_exists(provider, project)

        selection = _choose_spec_or_all(project, cfg, args.spec)
        if isinstance(selection, AllSpecsSentinel):
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
