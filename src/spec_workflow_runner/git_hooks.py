"""Git hooks system for commit blocking during implementation phase.

Installs temporary pre-commit hooks to prevent commits during implementation.
"""

from __future__ import annotations

import stat
from contextlib import contextmanager
from pathlib import Path


class GitHookManager:
    """Manages temporary git hooks for commit control."""

    def __init__(self, repo_path: Path):
        """Initialize git hook manager.

        Args:
            repo_path: Path to git repository root
        """
        self.repo_path = repo_path
        self.hooks_dir = repo_path / ".git" / "hooks"
        self.pre_commit_hook = self.hooks_dir / "pre-commit"
        self.backup_hook = self.hooks_dir / "pre-commit.backup"

    def install_commit_blocker(self) -> bool:
        """Install pre-commit hook that blocks all commits.

        Returns:
            True if installed successfully, False otherwise
        """
        if not self.hooks_dir.exists():
            return False

        # Backup existing hook if present
        if self.pre_commit_hook.exists():
            if not self.backup_hook.exists():
                self.pre_commit_hook.rename(self.backup_hook)
            else:
                # Backup already exists, remove current hook
                self.pre_commit_hook.unlink()

        # Create blocking hook
        hook_content = """#!/bin/sh
# Temporary hook installed by spec-workflow-runner
# Blocks commits during implementation phase

echo "❌ Commits are blocked during implementation phase"
echo "   The runner will create commits during post-session verification"
echo "   after validating that acceptance criteria are met."
exit 1
"""

        self.pre_commit_hook.write_text(hook_content)

        # Make executable
        self.pre_commit_hook.chmod(self.pre_commit_hook.stat().st_mode | stat.S_IEXEC)

        return True

    def remove_commit_blocker(self) -> bool:
        """Remove pre-commit hook and restore backup if exists.

        Returns:
            True if removed successfully, False otherwise
        """
        if not self.pre_commit_hook.exists():
            return True

        # Remove blocking hook
        self.pre_commit_hook.unlink()

        # Restore backup if exists
        if self.backup_hook.exists():
            self.backup_hook.rename(self.pre_commit_hook)

        return True

    def is_blocker_installed(self) -> bool:
        """Check if commit blocker is currently installed.

        Returns:
            True if blocker is installed, False otherwise
        """
        if not self.pre_commit_hook.exists():
            return False

        content = self.pre_commit_hook.read_text()
        return "spec-workflow-runner" in content and "Blocks commits" in content


@contextmanager
def block_commits(repo_path: Path):
    """Context manager to temporarily block commits.

    Usage:
        with block_commits(project_path):
            # Commits are blocked here
            run_implementation_session()
        # Commits are allowed again

    Args:
        repo_path: Path to git repository root

    Yields:
        GitHookManager instance
    """
    manager = GitHookManager(repo_path)

    try:
        manager.install_commit_blocker()
        yield manager
    finally:
        manager.remove_commit_blocker()


def main() -> int:
    """CLI for git hook management.

    Usage:
        python git_hooks.py install <repo_path>
        python git_hooks.py remove <repo_path>
        python git_hooks.py status <repo_path>

    Returns:
        Exit code
    """
    import sys

    if len(sys.argv) < 3:
        print("Usage: git_hooks.py {install|remove|status} <repo_path>", file=sys.stderr)
        return 1

    command = sys.argv[1]
    repo_path = Path(sys.argv[2])

    manager = GitHookManager(repo_path)

    if command == "install":
        if manager.install_commit_blocker():
            print("✅ Commit blocker installed")
            return 0
        print("❌ Failed to install commit blocker", file=sys.stderr)
        return 1

    elif command == "remove":
        if manager.remove_commit_blocker():
            print("✅ Commit blocker removed")
            return 0
        print("❌ Failed to remove commit blocker", file=sys.stderr)
        return 1

    elif command == "status":
        if manager.is_blocker_installed():
            print("🔒 Commit blocker is ACTIVE")
            return 0
        print("🔓 Commit blocker is NOT active")
        return 1

    else:
        print(f"Unknown command: {command}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    import sys

    sys.exit(main())
