"""Tests for the run_tasks orchestration helpers."""

from __future__ import annotations

from pathlib import Path

from spec_workflow_runner.run_tasks import build_prompt, run_codex
from spec_workflow_runner.utils import Config, TaskStats

DEFAULT_PROMPT_TEMPLATE = "{spec_name}:{tasks_remaining}:{tasks_in_progress}"


def _make_config(prompt_template: str = DEFAULT_PROMPT_TEMPLATE) -> Config:
    """Return a Config tailored for unit tests."""

    return Config(
        repos_root=Path("/tmp/repos"),
        spec_workflow_dir_name=".spec-workflow",
        specs_subdir="specs",
        tasks_filename="tasks.md",
        codex_command=("codex", "e"),
        prompt_template=prompt_template,
        no_commit_limit=3,
        log_dir_name="logs",
        log_file_template="task_{index}.log",
        ignore_dirs=(),
        monitor_refresh_seconds=5,
    )


def test_build_prompt_uses_remaining_tasks() -> None:
    cfg = _make_config("{spec_name}:{tasks_remaining}:{tasks_in_progress}")
    stats = TaskStats(done=1, pending=3, in_progress=1)

    prompt = build_prompt(cfg, "alpha", stats)

    # total = 5, remaining = total - done = 4
    assert prompt == "alpha:4:1"


def test_run_codex_dry_run_writes_log(tmp_path, capsys) -> None:
    cfg = _make_config()
    prompt = "demo prompt"
    log_path = tmp_path / "logs" / "task_1.log"

    run_codex(
        cfg,
        project_path=tmp_path,
        prompt=prompt,
        dry_run=True,
        spec_name="alpha",
        iteration=1,
        log_path=log_path,
    )

    log_contents = log_path.read_text(encoding="utf-8")
    assert prompt in log_contents
    assert "[dry-run]" in log_contents

    stdout = capsys.readouterr().out
    assert "Saved log" in stdout
