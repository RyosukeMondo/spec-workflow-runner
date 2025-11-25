"""Tests for project discovery caching functionality."""

from __future__ import annotations

import time
from pathlib import Path

from spec_workflow_runner.utils import (
    Config,
    ProjectCache,
    _get_cache_path,
    _is_cache_valid,
    _read_cache,
    _scan_projects,
    _write_cache,
    discover_projects,
)


def _make_config(
    repos_root: Path,
    cache_dir: Path,
    cache_max_age_days: int = 7,
) -> Config:
    """Create test config."""
    return Config(
        repos_root=repos_root,
        spec_workflow_dir_name=".spec-workflow",
        specs_subdir="specs",
        tasks_filename="tasks.md",
        codex_command=("codex", "e"),
        prompt_template="test",
        no_commit_limit=3,
        log_dir_name="logs",
        log_file_template="task_{index}.log",
        ignore_dirs=(".git", "node_modules"),
        monitor_refresh_seconds=5,
        cache_dir=cache_dir,
        cache_max_age_days=cache_max_age_days,
        codex_config_overrides=(),
    )


def test_project_cache_serialization() -> None:
    cache = ProjectCache(
        repos_root="/tmp/repos",
        last_scan=1234567890.0,
        projects=["/tmp/repos/project1", "/tmp/repos/project2"],
    )

    cache_dict = cache.to_dict()
    restored = ProjectCache.from_dict(cache_dict)

    assert restored.repos_root == cache.repos_root
    assert restored.last_scan == cache.last_scan
    assert restored.projects == cache.projects


def test_write_and_read_cache(tmp_path: Path) -> None:
    repos_root = tmp_path / "repos"
    cache_dir = tmp_path / "cache"
    cfg = _make_config(repos_root, cache_dir)

    cache = ProjectCache(
        repos_root=str(repos_root),
        last_scan=time.time(),
        projects=[str(repos_root / "project1"), str(repos_root / "project2")],
    )

    _write_cache(cfg, cache)

    cache_path = _get_cache_path(cfg)
    assert cache_path.exists()

    restored = _read_cache(cfg)
    assert restored is not None
    assert restored.repos_root == cache.repos_root
    assert restored.projects == cache.projects


def test_read_cache_returns_none_when_missing(tmp_path: Path) -> None:
    repos_root = tmp_path / "repos"
    cache_dir = tmp_path / "cache"
    cfg = _make_config(repos_root, cache_dir)

    result = _read_cache(cfg)

    assert result is None


def test_read_cache_returns_none_on_corrupted_file(tmp_path: Path) -> None:
    repos_root = tmp_path / "repos"
    cache_dir = tmp_path / "cache"
    cfg = _make_config(repos_root, cache_dir)

    cache_path = _get_cache_path(cfg)
    cache_path.parent.mkdir(parents=True)
    cache_path.write_text("corrupted json", encoding="utf-8")

    result = _read_cache(cfg)

    assert result is None


def test_is_cache_valid_with_recent_cache(tmp_path: Path) -> None:
    repos_root = tmp_path / "repos"
    cache_dir = tmp_path / "cache"
    cfg = _make_config(repos_root, cache_dir, cache_max_age_days=7)

    cache = ProjectCache(
        repos_root=str(repos_root),
        last_scan=time.time() - (3 * 86400),  # 3 days ago
        projects=[],
    )

    assert _is_cache_valid(cfg, cache)


def test_is_cache_valid_with_expired_cache(tmp_path: Path) -> None:
    repos_root = tmp_path / "repos"
    cache_dir = tmp_path / "cache"
    cfg = _make_config(repos_root, cache_dir, cache_max_age_days=7)

    cache = ProjectCache(
        repos_root=str(repos_root),
        last_scan=time.time() - (10 * 86400),  # 10 days ago
        projects=[],
    )

    assert not _is_cache_valid(cfg, cache)


def test_is_cache_valid_with_different_repos_root(tmp_path: Path) -> None:
    repos_root = tmp_path / "repos"
    cache_dir = tmp_path / "cache"
    cfg = _make_config(repos_root, cache_dir)

    cache = ProjectCache(
        repos_root=str(tmp_path / "different"),
        last_scan=time.time(),
        projects=[],
    )

    assert not _is_cache_valid(cfg, cache)


def test_scan_projects_finds_spec_workflow_dirs(tmp_path: Path) -> None:
    repos_root = tmp_path / "repos"
    cache_dir = tmp_path / "cache"
    cfg = _make_config(repos_root, cache_dir)

    project1 = repos_root / "project1"
    project2 = repos_root / "project2"
    no_spec = repos_root / "no_spec_project"

    (project1 / ".spec-workflow").mkdir(parents=True)
    (project2 / ".spec-workflow").mkdir(parents=True)
    no_spec.mkdir(parents=True)

    projects = _scan_projects(cfg)

    assert len(projects) == 2
    assert project1 in projects
    assert project2 in projects
    assert no_spec not in projects


def test_scan_projects_respects_ignore_dirs(tmp_path: Path) -> None:
    repos_root = tmp_path / "repos"
    cache_dir = tmp_path / "cache"
    cfg = _make_config(repos_root, cache_dir)

    project = repos_root / "project"
    ignored = repos_root / "node_modules" / "nested_project"

    (project / ".spec-workflow").mkdir(parents=True)
    (ignored / ".spec-workflow").mkdir(parents=True)

    projects = _scan_projects(cfg)

    assert project in projects
    assert ignored not in projects


def test_discover_projects_uses_cache(tmp_path: Path, capsys) -> None:
    repos_root = tmp_path / "repos"
    cache_dir = tmp_path / "cache"
    cfg = _make_config(repos_root, cache_dir)

    project1 = repos_root / "project1"
    (project1 / ".spec-workflow").mkdir(parents=True)

    # First call - no cache
    projects1 = discover_projects(cfg)
    output1 = capsys.readouterr().out
    assert "Scanning for projects" in output1
    assert "Cache updated" in output1
    assert len(projects1) == 1

    # Second call - should use cache
    projects2 = discover_projects(cfg)
    output2 = capsys.readouterr().out
    assert "Using cached projects" in output2
    assert "Scanning for projects" not in output2
    assert projects2 == projects1


def test_discover_projects_force_refresh(tmp_path: Path, capsys) -> None:
    repos_root = tmp_path / "repos"
    cache_dir = tmp_path / "cache"
    cfg = _make_config(repos_root, cache_dir)

    project1 = repos_root / "project1"
    (project1 / ".spec-workflow").mkdir(parents=True)

    # First call - creates cache
    discover_projects(cfg)
    capsys.readouterr()  # Clear output

    # Force refresh ignores cache
    projects = discover_projects(cfg, force_refresh=True)
    output = capsys.readouterr().out
    assert "Scanning for projects" in output
    assert "Using cached projects" not in output
    assert len(projects) == 1


def test_discover_projects_invalidates_expired_cache(tmp_path: Path, capsys) -> None:
    repos_root = tmp_path / "repos"
    cache_dir = tmp_path / "cache"
    cfg = _make_config(repos_root, cache_dir, cache_max_age_days=7)

    project1 = repos_root / "project1"
    (project1 / ".spec-workflow").mkdir(parents=True)

    # Create expired cache
    old_cache = ProjectCache(
        repos_root=str(repos_root),
        last_scan=time.time() - (10 * 86400),  # 10 days ago
        projects=[str(project1)],
    )
    _write_cache(cfg, old_cache)

    # Should detect expired cache and rescan
    projects = discover_projects(cfg)
    output = capsys.readouterr().out
    assert "Cache expired" in output
    assert "Scanning for projects" in output
    assert len(projects) == 1


def test_discover_projects_invalidates_wrong_repos_root(tmp_path: Path, capsys) -> None:
    repos_root = tmp_path / "repos"
    cache_dir = tmp_path / "cache"
    cfg = _make_config(repos_root, cache_dir)

    project1 = repos_root / "project1"
    (project1 / ".spec-workflow").mkdir(parents=True)

    # Create cache with different repos_root
    wrong_cache = ProjectCache(
        repos_root=str(tmp_path / "different"),
        last_scan=time.time(),
        projects=[],
    )
    _write_cache(cfg, wrong_cache)

    # Should detect mismatch and rescan
    projects = discover_projects(cfg)
    output = capsys.readouterr().out
    assert "Cache invalidated" in output
    assert "repos_root changed" in output
    assert len(projects) == 1


def test_discover_projects_cache_age_message(tmp_path: Path, capsys) -> None:
    repos_root = tmp_path / "repos"
    cache_dir = tmp_path / "cache"
    cfg = _make_config(repos_root, cache_dir)

    project1 = repos_root / "project1"
    (project1 / ".spec-workflow").mkdir(parents=True)

    # Test "today" message
    cache_today = ProjectCache(
        repos_root=str(repos_root),
        last_scan=time.time() - 3600,  # 1 hour ago
        projects=[str(project1)],
    )
    _write_cache(cfg, cache_today)
    discover_projects(cfg)
    output = capsys.readouterr().out
    assert "scanned today" in output

    # Test "yesterday" message
    cache_yesterday = ProjectCache(
        repos_root=str(repos_root),
        last_scan=time.time() - (86400 + 3600),  # 25 hours ago
        projects=[str(project1)],
    )
    _write_cache(cfg, cache_yesterday)
    discover_projects(cfg)
    output = capsys.readouterr().out
    assert "scanned yesterday" in output

    # Test "X days ago" message
    cache_old = ProjectCache(
        repos_root=str(repos_root),
        last_scan=time.time() - (3 * 86400),  # 3 days ago
        projects=[str(project1)],
    )
    _write_cache(cfg, cache_old)
    discover_projects(cfg)
    output = capsys.readouterr().out
    assert "scanned 3 days ago" in output
