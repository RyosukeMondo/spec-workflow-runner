"""Tests for the run_tasks orchestration helpers."""

from __future__ import annotations

import io
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from spec_workflow_runner import run_tasks as runner
from spec_workflow_runner.providers import CodexProvider
from spec_workflow_runner.utils import Config, RunnerError, TaskStats

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

    # Mock time.sleep to raise exception after first sleep (when entering polling mode)
    sleep_count = {"count": 0}

    def fake_sleep(seconds: float) -> None:
        sleep_count["count"] += 1
        # Raise exception when entering polling mode to break infinite loop
        raise KeyboardInterrupt("Test interrupt to exit polling")

    monkeypatch.setattr(runner, "run_loop", fake_run_loop)
    monkeypatch.setattr(runner.time, "sleep", fake_sleep)

    # Should process both specs, then enter polling mode and raise KeyboardInterrupt
    with pytest.raises(KeyboardInterrupt, match="Test interrupt"):
        runner.run_all_specs(provider, cfg, tmp_path, dry_run=False)

    assert seen == ["alpha", "beta"]
    assert sleep_count["count"] == 1  # Should sleep once when entering polling mode


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


def test_check_clean_working_tree_warns_on_uncommitted_changes(tmp_path: Path, capsys) -> None:
    """Verify that check_clean_working_tree warns but continues with uncommitted changes."""
    import subprocess

    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    (tmp_path / "uncommitted.txt").write_text("uncommitted", encoding="utf-8")

    # Should not raise, just warn
    runner.check_clean_working_tree(tmp_path)

    output = capsys.readouterr().out
    assert "Warning: Uncommitted changes detected" in output
    assert "Commit detection may be unreliable" in output


def test_run_provider_succeeds_on_first_attempt(tmp_path: Path, monkeypatch) -> None:
    """Verify that run_provider succeeds without retry when command succeeds on first attempt."""
    cfg = _make_config()
    provider = CodexProvider()
    log_path = tmp_path / "logs" / "task_1.log"

    class DummyProcess:
        def __init__(self) -> None:
            self.stdout = io.BytesIO(b"success\n")
            self.returncode = 0

        def wait(self) -> None:
            return None

    def fake_popen(command, **kwargs):  # type: ignore[no-untyped-def]
        return DummyProcess()

    monkeypatch.setattr(runner.subprocess, "Popen", fake_popen)

    # Should not raise
    runner.run_provider(
        provider,
        cfg,
        project_path=tmp_path,
        prompt="test prompt",
        dry_run=False,
        spec_name="test-spec",
        iteration=1,
        log_path=log_path,
    )


def test_run_provider_retries_on_failure(tmp_path: Path, monkeypatch) -> None:
    """Verify that run_provider retries when command fails initially."""
    cfg = _make_config()
    provider = CodexProvider()
    log_path = tmp_path / "logs" / "task_1.log"

    attempt_count = {"count": 0}

    class DummyProcess:
        def __init__(self) -> None:
            attempt_count["count"] += 1
            self.stdout = io.BytesIO(b"output\n")
            # Fail on first attempt, succeed on second
            self.returncode = 0 if attempt_count["count"] > 1 else 1

        def wait(self) -> None:
            return None

    def fake_popen(command, **kwargs):  # type: ignore[no-untyped-def]
        return DummyProcess()

    mock_sleep = MagicMock()
    monkeypatch.setattr(runner.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(runner.time, "sleep", mock_sleep)

    runner.run_provider(
        provider,
        cfg,
        project_path=tmp_path,
        prompt="test prompt",
        dry_run=False,
        spec_name="test-spec",
        iteration=1,
        log_path=log_path,
    )

    assert attempt_count["count"] == 2
    # Should sleep once with 1 second backoff (2^(1-1) = 1)
    mock_sleep.assert_called_once_with(1)


def test_run_provider_exponential_backoff(tmp_path: Path, monkeypatch) -> None:
    """Verify exponential backoff timing between retries."""
    cfg = _make_config()
    provider = CodexProvider()
    log_path = tmp_path / "logs" / "task_1.log"

    attempt_count = {"count": 0}

    class DummyProcess:
        def __init__(self) -> None:
            attempt_count["count"] += 1
            self.stdout = io.BytesIO(b"output\n")
            # Succeed on third attempt
            self.returncode = 0 if attempt_count["count"] >= 3 else 1

        def wait(self) -> None:
            return None

    def fake_popen(command, **kwargs):  # type: ignore[no-untyped-def]
        return DummyProcess()

    sleep_calls: list[float] = []

    def track_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)

    monkeypatch.setattr(runner.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(runner.time, "sleep", track_sleep)

    runner.run_provider(
        provider,
        cfg,
        project_path=tmp_path,
        prompt="test prompt",
        dry_run=False,
        spec_name="test-spec",
        iteration=1,
        log_path=log_path,
    )

    assert attempt_count["count"] == 3
    # Exponential backoff: 2^0=1, 2^1=2
    assert sleep_calls == [1, 2]


def test_run_provider_fails_after_max_retries(tmp_path: Path, monkeypatch) -> None:
    """Verify that run_provider raises RunnerError after exhausting all retries."""
    cfg = _make_config()
    provider = CodexProvider()
    log_path = tmp_path / "logs" / "task_1.log"

    attempt_count = {"count": 0}

    class DummyProcess:
        def __init__(self) -> None:
            attempt_count["count"] += 1
            self.stdout = io.BytesIO(b"error\n")
            self.returncode = 1  # Always fail

        def wait(self) -> None:
            return None

    def fake_popen(command, **kwargs):  # type: ignore[no-untyped-def]
        return DummyProcess()

    mock_sleep = MagicMock()
    monkeypatch.setattr(runner.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(runner.time, "sleep", mock_sleep)

    with pytest.raises(RunnerError, match="Provider command failed"):
        runner.run_provider(
            provider,
            cfg,
            project_path=tmp_path,
            prompt="test prompt",
            dry_run=False,
            spec_name="test-spec",
            iteration=1,
            log_path=log_path,
        )

    # Should attempt max_retries times (default is 3)
    assert attempt_count["count"] == 3
    # Should sleep before retry 2 and retry 3: 1s, 2s
    assert mock_sleep.call_count == 2


def test_run_provider_logs_retry_attempts(tmp_path: Path, monkeypatch, caplog) -> None:
    """Verify that retry attempts are logged correctly."""
    import logging

    caplog.set_level(logging.WARNING)

    cfg = _make_config()
    provider = CodexProvider()
    log_path = tmp_path / "logs" / "task_1.log"

    attempt_count = {"count": 0}

    class DummyProcess:
        def __init__(self) -> None:
            attempt_count["count"] += 1
            self.stdout = io.BytesIO(b"output\n")
            # Succeed on second attempt
            self.returncode = 0 if attempt_count["count"] > 1 else 1

        def wait(self) -> None:
            return None

    def fake_popen(command, **kwargs):  # type: ignore[no-untyped-def]
        return DummyProcess()

    mock_sleep = MagicMock()
    monkeypatch.setattr(runner.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(runner.time, "sleep", mock_sleep)

    runner.run_provider(
        provider,
        cfg,
        project_path=tmp_path,
        prompt="test prompt",
        dry_run=False,
        spec_name="test-spec",
        iteration=1,
        log_path=log_path,
    )

    # Check that warning was logged for retry
    assert any("retrying with backoff" in record.message.lower() for record in caplog.records)


def test_run_provider_context_limit_error_uses_long_wait(tmp_path: Path, monkeypatch) -> None:
    """Verify that context limit errors trigger configured wait time instead of exponential backoff."""
    cfg = _make_config()
    provider = CodexProvider()
    log_path = tmp_path / "logs" / "task_1.log"

    attempt_count = {"count": 0}

    class DummyProcess:
        def __init__(self) -> None:
            attempt_count["count"] += 1
            # Simulate context limit error on first attempt
            if attempt_count["count"] == 1:
                self.stdout = io.BytesIO(
                    b"Error: input length and max_tokens exceed context limit: 197626 + 21333 > 200000\n"
                )
                self.returncode = 1
            else:
                self.stdout = io.BytesIO(b"success\n")
                self.returncode = 0

        def wait(self) -> None:
            return None

    def fake_popen(command, **kwargs):  # type: ignore[no-untyped-def]
        return DummyProcess()

    sleep_calls: list[float] = []

    def track_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)

    monkeypatch.setattr(runner.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(runner.time, "sleep", track_sleep)

    runner.run_provider(
        provider,
        cfg,
        project_path=tmp_path,
        prompt="test prompt",
        dry_run=False,
        spec_name="test-spec",
        iteration=1,
        log_path=log_path,
    )

    assert attempt_count["count"] == 2
    # Should use context_limit_wait_seconds (600) instead of exponential backoff (1)
    assert sleep_calls == [600]


def test_run_provider_context_limit_error_logs_wait_time(
    tmp_path: Path, monkeypatch, caplog
) -> None:
    """Verify that context limit errors log the wait time correctly."""
    import logging

    caplog.set_level(logging.WARNING)

    cfg = _make_config()
    provider = CodexProvider()
    log_path = tmp_path / "logs" / "task_1.log"

    attempt_count = {"count": 0}

    class DummyProcess:
        def __init__(self) -> None:
            attempt_count["count"] += 1
            if attempt_count["count"] == 1:
                self.stdout = io.BytesIO(b"Error: context window exceeded\n")
                self.returncode = 1
            else:
                self.stdout = io.BytesIO(b"success\n")
                self.returncode = 0

        def wait(self) -> None:
            return None

    def fake_popen(command, **kwargs):  # type: ignore[no-untyped-def]
        return DummyProcess()

    mock_sleep = MagicMock()
    monkeypatch.setattr(runner.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(runner.time, "sleep", mock_sleep)

    runner.run_provider(
        provider,
        cfg,
        project_path=tmp_path,
        prompt="test prompt",
        dry_run=False,
        spec_name="test-spec",
        iteration=1,
        log_path=log_path,
    )

    # Check that context limit message was logged
    assert any("context limit" in record.message.lower() for record in caplog.records)
    mock_sleep.assert_called_once_with(600)


def test_run_provider_non_context_error_uses_exponential_backoff(
    tmp_path: Path, monkeypatch
) -> None:
    """Verify that non-context errors still use exponential backoff."""
    cfg = _make_config()
    provider = CodexProvider()
    log_path = tmp_path / "logs" / "task_1.log"

    attempt_count = {"count": 0}

    class DummyProcess:
        def __init__(self) -> None:
            attempt_count["count"] += 1
            if attempt_count["count"] < 3:
                # Regular error, not context limit
                self.stdout = io.BytesIO(b"Error: Connection timeout\n")
                self.returncode = 1
            else:
                self.stdout = io.BytesIO(b"success\n")
                self.returncode = 0

        def wait(self) -> None:
            return None

    def fake_popen(command, **kwargs):  # type: ignore[no-untyped-def]
        return DummyProcess()

    sleep_calls: list[float] = []

    def track_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)

    monkeypatch.setattr(runner.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(runner.time, "sleep", track_sleep)

    runner.run_provider(
        provider,
        cfg,
        project_path=tmp_path,
        prompt="test prompt",
        dry_run=False,
        spec_name="test-spec",
        iteration=1,
        log_path=log_path,
    )

    assert attempt_count["count"] == 3
    # Should use exponential backoff: 2^0=1, 2^1=2
    assert sleep_calls == [1, 2]


def test_run_provider_infinite_retries_for_context_limit(tmp_path: Path, monkeypatch) -> None:
    """Verify that context limit errors trigger infinite retries beyond max_retries."""
    cfg = _make_config()
    # Ensure max_retries is small to verify we go beyond it
    assert cfg.max_retries == 3

    provider = CodexProvider()
    log_path = tmp_path / "logs" / "task_1.log"

    attempt_count = {"count": 0}

    class DummyProcess:
        def __init__(self) -> None:
            attempt_count["count"] += 1
            # Simulate context limit error for first 5 attempts (more than max_retries=3)
            if attempt_count["count"] <= 5:
                self.stdout = io.BytesIO(b"Error: You've hit your limit\n")
                self.returncode = 1
            else:
                self.stdout = io.BytesIO(b"success\n")
                self.returncode = 0

        def wait(self) -> None:
            return None

    def fake_popen(command, **kwargs):  # type: ignore[no-untyped-def]
        return DummyProcess()

    sleep_calls: list[float] = []

    def track_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)

    monkeypatch.setattr(runner.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(runner.time, "sleep", track_sleep)

    runner.run_provider(
        provider,
        cfg,
        project_path=tmp_path,
        prompt="test prompt",
        dry_run=False,
        spec_name="test-spec",
        iteration=1,
        log_path=log_path,
    )

    # Should attempt 6 times (5 fails + 1 success)
    assert attempt_count["count"] == 6
    # Should sleep 5 times with context_limit_wait_seconds (600)
    assert len(sleep_calls) == 5
    assert all(s == 600 for s in sleep_calls)
