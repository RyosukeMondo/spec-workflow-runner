"""Shared helpers for spec workflow automation scripts."""
from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
from typing import Callable, List, Sequence, Tuple, TypeVar


T = TypeVar("T")


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
    timeout_seconds: int
    log_dir_name: str
    log_file_template: str
    ignore_dirs: Tuple[str, ...]
    monitor_refresh_seconds: int

    @classmethod
    def from_dict(cls, payload: dict) -> "Config":
        """Create a Config object from a raw dictionary."""
        repos_root = Path(os.path.expanduser(payload["repos_root"])).resolve()
        return cls(
            repos_root=repos_root,
            spec_workflow_dir_name=payload["spec_workflow_dir_name"],
            specs_subdir=payload["specs_subdir"],
            tasks_filename=payload["tasks_filename"],
            codex_command=tuple(payload["codex_command"]),
            prompt_template=payload["prompt_template"],
            no_commit_limit=int(payload["no_commit_limit"]),
            timeout_seconds=int(payload["timeout_seconds"]),
            log_dir_name=payload["log_dir_name"],
            log_file_template=payload["log_file_template"],
            ignore_dirs=tuple(payload.get("ignore_dirs", [])),
            monitor_refresh_seconds=int(payload.get("monitor_refresh_seconds", 5)),
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


def discover_projects(cfg: Config) -> List[Path]:
    """Return every project directory under repos_root containing a .spec-workflow."""
    root = cfg.repos_root
    if not root.exists():
        raise FileNotFoundError(f"Repos root not found: {root}")

    found: List[Path] = []
    for dirpath, dirnames, _ in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in cfg.ignore_dirs]
        if cfg.spec_workflow_dir_name in dirnames:
            found.append(Path(dirpath))
    return sorted(found)


def discover_specs(project_path: Path, cfg: Config) -> List[Tuple[str, Path]]:
    """List specs for the selected project."""
    specs_root = project_path / cfg.spec_workflow_dir_name / cfg.specs_subdir
    if not specs_root.exists():
        raise FileNotFoundError(f"No specs directory at {specs_root}")
    specs: List[Tuple[str, Path]] = []
    for child in sorted(specs_root.iterdir()):
        if child.is_dir():
            specs.append((child.name, child))
    return specs


TASK_PATTERN = re.compile(r"\[(?P<state> |x|-)\]")


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


def choose_option(
    title: str,
    options: Sequence[T],
    label: Callable[[T], str],
    *,
    allow_quit: bool = True,
) -> T:
    """Display a simple numeric menu and return the selected item."""
    if not options:
        raise ValueError(f"No options available for {title}")

    while True:
        print(f"\n{title}")
        for idx, option in enumerate(options, start=1):
            print(f"  {idx}. {label(option)}")
        prompt = "Select option"
        if allow_quit:
            prompt += " (or q to quit)"
        prompt += ": "
        choice = input(prompt).strip().lower()
        if allow_quit and choice in {"q", "quit"}:
            raise KeyboardInterrupt("User cancelled selection")
        try:
            numeric = int(choice)
        except ValueError:
            print("Please enter a valid number.")
            continue
        if 1 <= numeric <= len(options):
            return options[numeric - 1]
        print("Choice out of range, try again.")
