"""Tests for the run_tasks orchestration helpers."""

from __future__ import annotations

from pathlib import Path

from spec_workflow_runner import run_tasks as runner
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

    prompt = runner.build_prompt(cfg, "alpha", stats)

    # total = 5, remaining = total - done = 4
    assert prompt == "alpha:4:1"


def test_run_codex_dry_run_writes_log(tmp_path, capsys) -> None:
    cfg = _make_config()
    prompt = "demo prompt"
    log_path = tmp_path / "logs" / "task_1.log"

    runner.run_codex(
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


def test_list_unfinished_specs_filters_completed(tmp_path: Path) -> None:
    cfg = _make_config()
    specs_root = tmp_path / cfg.spec_workflow_dir_name / cfg.specs_subdir
    alpha = specs_root / "alpha"
    beta = specs_root / "beta"
    alpha.mkdir(parents=True)
    beta.mkdir(parents=True)
    (alpha / cfg.tasks_filename).write_text("[ ] todo\n[x] done\n", encoding="utf-8")
    (beta / cfg.tasks_filename).write_text("[x] done\n[x] done\n", encoding="utf-8")

    unfinished = runner.list_unfinished_specs(tmp_path, cfg)

    assert unfinished == [("alpha", alpha)]


def test_run_all_specs_processes_each_unfinished_spec(tmp_path: Path, monkeypatch) -> None:
    cfg = _make_config()
    specs_root = tmp_path / cfg.spec_workflow_dir_name / cfg.specs_subdir
    first = specs_root / "alpha"
    second = specs_root / "beta"
    first.mkdir(parents=True)
    second.mkdir(parents=True)

    def _write_tasks(path: Path, content: str) -> None:
        (path / cfg.tasks_filename).write_text(content, encoding="utf-8")

    _write_tasks(first, "[ ] pending\n")
    _write_tasks(second, "[ ] todo\n")

    seen: list[str] = []

    def fake_run_loop(
        _cfg: Config,
        _project: Path,
        spec_name: str,
        spec_path: Path,
        dry_run: bool,
    ) -> None:
        assert not dry_run
        seen.append(spec_name)
        _write_tasks(spec_path, "[x] done\n")

    monkeypatch.setattr(runner, "run_loop", fake_run_loop)

    runner.run_all_specs(cfg, tmp_path, dry_run=False)

    assert seen == ["alpha", "beta"]
