"""Tests for the run_tasks orchestration helpers."""

from __future__ import annotations

import io
from pathlib import Path

import pytest

from spec_workflow_runner import run_tasks as runner
from spec_workflow_runner.providers import CodexProvider
from spec_workflow_runner.utils import Config, TaskStats

DEFAULT_PROMPT_TEMPLATE = "{spec_name}:{tasks_remaining}:{tasks_in_progress}"


def _make_config(
    prompt_template: str = DEFAULT_PROMPT_TEMPLATE,
    overrides: tuple[tuple[str, str], ...] | None = None,
) -> Config:
    """Return a Config tailored for unit tests."""

    return Config(
        repos_root=Path("/tmp/repos"),
        spec_workflow_dir_name=".spec-workflow",
        specs_subdir="specs",
        tasks_filename="tasks.md",
        codex_command=("codex", "e", "--dangerously-bypass-approvals-and-sandbox"),
        prompt_template=prompt_template,
        no_commit_limit=3,
        log_dir_name="logs",
        log_file_template="task_{index}.log",
        ignore_dirs=(),
        monitor_refresh_seconds=5,
        cache_dir=Path("/tmp/cache"),
        cache_max_age_days=7,
        codex_config_overrides=tuple(overrides or ()),
    )


def test_build_prompt_uses_remaining_tasks() -> None:
    cfg = _make_config("{spec_name}:{tasks_remaining}:{tasks_in_progress}")
    stats = TaskStats(done=1, pending=3, in_progress=1)

    prompt = runner.build_prompt(cfg, "alpha", stats)

    # total = 5, remaining = total - done = 4
    assert prompt == "alpha:4:1"


def test_run_provider_dry_run_writes_log(tmp_path, capsys) -> None:
    cfg = _make_config()
    provider = CodexProvider()
    prompt = "demo prompt"
    log_path = tmp_path / "logs" / "task_1.log"

    runner.run_provider(
        provider,
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


def test_run_provider_applies_config_overrides(tmp_path, monkeypatch) -> None:
    overrides = (
        ("mcp_servers.demo.tool_timeout_sec", "60"),
        ("features.example", '"value"'),
    )
    cfg = _make_config(overrides=overrides)
    provider = CodexProvider()
    prompt = "demo prompt"
    log_path = tmp_path / "logs" / "task_1.log"

    recorded: dict[str, object] = {}

    class DummyProcess:
        def __init__(self) -> None:
            self.stdout = io.BytesIO(b"ok\n")
            self.returncode = 0

        def wait(self) -> None:
            return None

    def fake_popen(command, **kwargs):  # type: ignore[no-untyped-def]
        recorded["command"] = command
        recorded["kwargs"] = kwargs
        return DummyProcess()

    monkeypatch.setattr(runner.subprocess, "Popen", fake_popen)

    runner.run_provider(
        provider,
        cfg,
        project_path=tmp_path,
        prompt=prompt,
        dry_run=False,
        spec_name="alpha",
        iteration=1,
        log_path=log_path,
    )

    assert recorded["command"] == [
        "codex",
        "e",
        "--dangerously-bypass-approvals-and-sandbox",
        "-c",
        "mcp_servers.demo.tool_timeout_sec=60",
        "-c",
        'features.example="value"',
        prompt,
    ]


def test_list_unfinished_specs_filters_completed(tmp_path: Path) -> None:
    cfg = _make_config()
    specs_root = tmp_path / cfg.spec_workflow_dir_name / cfg.specs_subdir
    alpha = specs_root / "alpha"
    beta = specs_root / "beta"
    alpha.mkdir(parents=True)
    beta.mkdir(parents=True)
    (alpha / cfg.tasks_filename).write_text("- [ ] todo\n- [x] done\n", encoding="utf-8")
    (beta / cfg.tasks_filename).write_text("- [x] done\n- [x] done\n", encoding="utf-8")

    unfinished = runner.list_unfinished_specs(tmp_path, cfg)

    assert unfinished == [("alpha", alpha)]


def test_list_unfinished_specs_sorts_by_ctime(tmp_path: Path) -> None:
    """Verify that unfinished specs are sorted by spec directory creation time (oldest first)."""
    import os
    import time

    cfg = _make_config()
    specs_root = tmp_path / cfg.spec_workflow_dir_name / cfg.specs_subdir
    alpha = specs_root / "alpha"
    beta = specs_root / "beta"
    gamma = specs_root / "gamma"
    alpha.mkdir(parents=True)
    beta.mkdir(parents=True)
    gamma.mkdir(parents=True)

    # Create tasks.md files with unfinished tasks
    alpha_tasks = alpha / cfg.tasks_filename
    beta_tasks = beta / cfg.tasks_filename
    gamma_tasks = gamma / cfg.tasks_filename

    alpha_tasks.write_text("- [ ] todo\n", encoding="utf-8")
    beta_tasks.write_text("- [ ] todo\n", encoding="utf-8")
    gamma_tasks.write_text("- [ ] todo\n", encoding="utf-8")

    # Modify directories to set different ctimes (os.utime updates ctime as a side effect)
    # The sleep delays ensure different ctime values
    base_time = time.time() - 1000
    os.utime(beta, (base_time, base_time))
    time.sleep(0.01)  # Ensure different ctimes
    os.utime(gamma, (base_time + 100, base_time + 100))
    time.sleep(0.01)
    os.utime(alpha, (base_time + 200, base_time + 200))

    unfinished = runner.list_unfinished_specs(tmp_path, cfg)

    # Should be sorted by directory ctime: beta (oldest), gamma, alpha (newest)
    assert unfinished == [("beta", beta), ("gamma", gamma), ("alpha", alpha)]


def test_run_all_specs_processes_each_unfinished_spec(tmp_path: Path, monkeypatch) -> None:
    cfg = _make_config()
    provider = CodexProvider()
    specs_root = tmp_path / cfg.spec_workflow_dir_name / cfg.specs_subdir
    first = specs_root / "alpha"
    second = specs_root / "beta"
    first.mkdir(parents=True)
    second.mkdir(parents=True)

    def _write_tasks(path: Path, content: str) -> None:
        (path / cfg.tasks_filename).write_text(content, encoding="utf-8")

    _write_tasks(first, "- [ ] pending\n")
    _write_tasks(second, "- [ ] todo\n")

    seen: list[str] = []

    def fake_run_loop(
        _provider,  # type: ignore[no-untyped-def]
        _cfg: Config,
        _project: Path,
        spec_name: str,
        spec_path: Path,
        dry_run: bool,
    ) -> None:
        assert not dry_run
        seen.append(spec_name)
        _write_tasks(spec_path, "- [x] done\n")

    monkeypatch.setattr(runner, "run_loop", fake_run_loop)

    runner.run_all_specs(provider, cfg, tmp_path, dry_run=False)

    assert seen == ["alpha", "beta"]


def test_ensure_provider_returns_explicit_value() -> None:
    result = runner.ensure_provider("claude")
    assert result == "claude"

    result = runner.ensure_provider("codex")
    assert result == "codex"


def test_ensure_provider_prompts_when_none(monkeypatch) -> None:
    def fake_input(_prompt: str) -> str:
        return "1"

    monkeypatch.setattr("builtins.input", fake_input)
    result = runner.ensure_provider(None)
    assert result in ("codex", "claude")


def test_has_uncommitted_changes_detects_new_files(tmp_path: Path) -> None:
    import subprocess

    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    (tmp_path / "initial.txt").write_text("initial", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "initial"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )

    assert not runner.has_uncommitted_changes(tmp_path)

    (tmp_path / "new.txt").write_text("new file", encoding="utf-8")
    assert runner.has_uncommitted_changes(tmp_path)


def test_has_uncommitted_changes_detects_modified_files(tmp_path: Path) -> None:
    import subprocess

    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    test_file = tmp_path / "test.txt"
    test_file.write_text("initial", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "initial"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )

    assert not runner.has_uncommitted_changes(tmp_path)

    test_file.write_text("modified", encoding="utf-8")
    assert runner.has_uncommitted_changes(tmp_path)


def test_check_clean_working_tree_passes_when_clean(tmp_path: Path) -> None:
    import subprocess

    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    (tmp_path / "test.txt").write_text("content", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "initial"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )

    runner.check_clean_working_tree(tmp_path)


def test_check_clean_working_tree_aborts_on_choice_1(tmp_path: Path, monkeypatch) -> None:
    import subprocess

    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    (tmp_path / "uncommitted.txt").write_text("uncommitted", encoding="utf-8")

    def fake_input(_prompt: str) -> str:
        return "1"

    monkeypatch.setattr("builtins.input", fake_input)

    with pytest.raises(runner.RunnerError, match="Aborted"):
        runner.check_clean_working_tree(tmp_path)


def test_check_clean_working_tree_continues_on_choice_2(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    import subprocess

    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    (tmp_path / "uncommitted.txt").write_text("uncommitted", encoding="utf-8")

    def fake_input(_prompt: str) -> str:
        return "2"

    monkeypatch.setattr("builtins.input", fake_input)

    runner.check_clean_working_tree(tmp_path)

    output = capsys.readouterr().out
    assert "Continuing with uncommitted changes" in output
