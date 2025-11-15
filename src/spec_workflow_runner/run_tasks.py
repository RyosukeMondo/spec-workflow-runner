"""Interactive runner that loops through spec-workflow tasks via codex."""
from __future__ import annotations

import argparse
from datetime import UTC, datetime, timedelta
import shlex
import subprocess
import sys
import textwrap
import time
from pathlib import Path
from typing import Callable, Optional

from .utils import (
    Config,
    TaskStats,
    choose_option,
    discover_projects,
    discover_specs,
    load_config,
    read_task_stats,
)


class RunnerError(Exception):
    """Raised when the run needs to abort early."""


class TimeoutBudget:
    """Track elapsed time between iterations and flag overages."""

    def __init__(
        self,
        seconds: int,
        *,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._limit = timedelta(seconds=seconds)
        self._monotonic = monotonic
        self._started_at = self._monotonic()

    def reset(self) -> None:
        """Start a new timeout window."""

        self._started_at = self._monotonic()

    def expired(self) -> bool:
        """Return True when the timeout window has been exceeded."""

        elapsed = timedelta(seconds=self._monotonic() - self._started_at)
        return elapsed > self._limit


def parse_args() -> argparse.Namespace:
    """Return CLI arguments for the runner."""
    parser = argparse.ArgumentParser(
        description="Run codex against remaining spec tasks until finished.",
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
        "--dry-run",
        action="store_true",
        help="Skip codex execution; useful for smoke testing.",
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


def ensure_spec(project: Path, cfg: Config, spec_name: Optional[str]) -> tuple[str, Path]:
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


def ensure_project(cfg: Config, explicit_path: Optional[Path]) -> Path:
    """Resolve the project directory."""
    if explicit_path:
        return explicit_path.resolve()
    projects = discover_projects(cfg)
    return choose_option(
        "Select project",
        projects,
        label=lambda path: f"{path.name}  ({path})",
    )


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


def run_codex(
    cfg: Config,
    project_path: Path,
    prompt: str,
    dry_run: bool,
    *,
    spec_name: str,
    iteration: int,
    log_path: Path,
) -> None:
    """Execute the codex command and stream output into a log file."""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    command = list(cfg.codex_command) + [prompt]
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

    def _print_and_log(message: str, handle) -> None:
        print(message, end="")
        handle.write(message)
        handle.flush()

    if dry_run:
        simulated = (
            f"[dry-run] Would run: {' '.join(cfg.codex_command)} {prompt!r}\n"
        )
        with log_path.open("w", encoding="utf-8") as handle:
            handle.write(header)
            handle.write(simulated)
            handle.write("# Exit Code\n0\n")
        print(simulated.strip())
        print(f"Saved log: {log_path}")
        return

    print("\nRunning:", formatted_command)
    with log_path.open("w", encoding="utf-8") as handle:
        handle.write(header)
        proc = subprocess.Popen(
            command,
            cwd=project_path,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        assert proc.stdout is not None
        for line in proc.stdout:
            _print_and_log(line, handle)
        proc.wait()
        handle.write(f"\n# Exit Code\n{proc.returncode}\n")

    if proc.returncode != 0:
        raise RunnerError("codex command failed. See log for details.")
    print(f"Saved log: {log_path}")


def run_loop(
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
    timeout = TimeoutBudget(cfg.timeout_seconds)
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

        if timeout.expired():
            raise RunnerError("Timeout exceeded. Aborting.")

        iteration += 1
        prompt = build_prompt(cfg, spec_name, stats)
        log_path = log_dir / cfg.log_file_template.format(index=iteration)
        run_codex(
            cfg,
            project_path,
            prompt,
            dry_run,
            spec_name=spec_name,
            iteration=iteration,
            log_path=log_path,
        )
        timeout.reset()
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
            print(f"No new commit detected. Streak: {no_commit_streak}/{cfg.no_commit_limit}")
            if no_commit_streak >= cfg.no_commit_limit:
                raise RunnerError("Circuit breaker: reached consecutive no-commit limit.")


def main() -> int:
    """Script entry point."""
    args = parse_args()
    cfg = load_config(args.config)

    try:
        project = ensure_project(cfg, args.project)
        spec_name, spec_path = ensure_spec(project, cfg, args.spec)
        run_loop(cfg, project, spec_name, spec_path, args.dry_run)
        return 0
    except KeyboardInterrupt:
        print("\nAborted by user.")
        return 130
    except (RunnerError, subprocess.CalledProcessError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
