"""Tests for git_hooks module."""

import subprocess
from pathlib import Path

import pytest

from spec_workflow_runner.git_hooks import GitHookManager, block_commits


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    """Create a temporary git repository."""
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

    # Create .git/hooks directory
    hooks_dir = tmp_path / ".git" / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)

    return tmp_path


def test_git_hook_manager_init(git_repo: Path):
    """Test GitHookManager initialization."""
    manager = GitHookManager(git_repo)

    assert manager.repo_path == git_repo
    assert manager.hooks_dir == git_repo / ".git" / "hooks"
    assert manager.pre_commit_hook == git_repo / ".git" / "hooks" / "pre-commit"


def test_install_commit_blocker(git_repo: Path):
    """Test installing commit blocker hook."""
    manager = GitHookManager(git_repo)

    result = manager.install_commit_blocker()

    assert result is True
    assert manager.pre_commit_hook.exists()
    assert manager.pre_commit_hook.stat().st_mode & 0o111  # Executable

    # Check content
    content = manager.pre_commit_hook.read_text()
    assert "spec-workflow-runner" in content
    assert "Blocks commits" in content


def test_install_blocker_with_existing_hook(git_repo: Path):
    """Test installing blocker when a hook already exists."""
    manager = GitHookManager(git_repo)

    # Create existing hook
    existing_content = "#!/bin/sh\necho 'existing hook'\n"
    manager.pre_commit_hook.write_text(existing_content)

    manager.install_commit_blocker()

    # Backup should be created
    assert manager.backup_hook.exists()
    assert manager.backup_hook.read_text() == existing_content

    # New blocker should be installed
    assert manager.pre_commit_hook.exists()
    content = manager.pre_commit_hook.read_text()
    assert "spec-workflow-runner" in content


def test_remove_commit_blocker(git_repo: Path):
    """Test removing commit blocker hook."""
    manager = GitHookManager(git_repo)

    # Install blocker
    manager.install_commit_blocker()
    assert manager.pre_commit_hook.exists()

    # Remove it
    result = manager.remove_commit_blocker()

    assert result is True
    assert not manager.pre_commit_hook.exists()


def test_remove_blocker_restores_backup(git_repo: Path):
    """Test removing blocker restores backed up hook."""
    manager = GitHookManager(git_repo)

    # Create existing hook
    existing_content = "#!/bin/sh\necho 'existing hook'\n"
    manager.pre_commit_hook.write_text(existing_content)

    # Install blocker (creates backup)
    manager.install_commit_blocker()

    # Remove blocker (should restore backup)
    manager.remove_commit_blocker()

    assert manager.pre_commit_hook.exists()
    assert manager.pre_commit_hook.read_text() == existing_content
    assert not manager.backup_hook.exists()


def test_is_blocker_installed(git_repo: Path):
    """Test checking if blocker is installed."""
    manager = GitHookManager(git_repo)

    # Initially not installed
    assert manager.is_blocker_installed() is False

    # Install it
    manager.install_commit_blocker()
    assert manager.is_blocker_installed() is True

    # Remove it
    manager.remove_commit_blocker()
    assert manager.is_blocker_installed() is False


def test_block_commits_context_manager(git_repo: Path):
    """Test block_commits context manager."""
    manager = GitHookManager(git_repo)

    # Initially no hook
    assert not manager.pre_commit_hook.exists()

    # Use context manager
    with block_commits(git_repo):
        # Hook should be installed
        assert manager.pre_commit_hook.exists()
        assert manager.is_blocker_installed()

    # Hook should be removed after context
    assert not manager.pre_commit_hook.exists()


def test_block_commits_cleanup_on_exception(git_repo: Path):
    """Test that hook is cleaned up even if exception occurs."""
    manager = GitHookManager(git_repo)

    try:
        with block_commits(git_repo):
            assert manager.pre_commit_hook.exists()
            raise ValueError("Test exception")
    except ValueError:
        pass

    # Hook should still be cleaned up
    assert not manager.pre_commit_hook.exists()


def test_commit_blocked_when_hook_installed(git_repo: Path):
    """Test that commits are actually blocked by the hook."""
    manager = GitHookManager(git_repo)

    # Create a file to commit
    test_file = git_repo / "test.txt"
    test_file.write_text("test content")

    subprocess.run(["git", "add", "test.txt"], cwd=git_repo, check=True)

    # Install blocker
    manager.install_commit_blocker()

    # Try to commit - should fail
    result = subprocess.run(
        ["git", "commit", "-m", "test commit"],
        cwd=git_repo,
        capture_output=True,
    )

    assert result.returncode != 0
    assert b"blocked" in result.stdout.lower() or b"blocked" in result.stderr.lower()

    # Remove blocker
    manager.remove_commit_blocker()

    # Now commit should work
    result = subprocess.run(
        ["git", "commit", "-m", "test commit"],
        cwd=git_repo,
        capture_output=True,
    )

    assert result.returncode == 0
