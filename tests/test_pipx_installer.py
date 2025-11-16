"""Tests for the pipx installer CLI."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from spec_workflow_runner import pipx_installer as pipx


class StubDeps(pipx.Dependencies):
    """Fake dependencies that capture executed commands."""

    def __init__(self, *, pipx_path: str | None = None) -> None:
        self.commands: list[Sequence[str]] = []
        self._pipx_path = pipx_path
        super().__init__(run=self._run, which=self._which, now=self._now)

    def _run(self, command: Sequence[str]) -> None:
        self.commands.append(tuple(command))
        # Once pip is asked to install pipx we pretend pipx is now available.
        if "pip" in command and "pipx" in command:
            self._pipx_path = self._pipx_path or "/tmp/bin/pipx"

    def _which(self, exe: str) -> str | None:
        if exe == "pipx":
            return self._pipx_path
        return None

    def _now(self) -> datetime:
        return datetime(2024, 1, 1, tzinfo=UTC)


def make_args(**overrides):
    payload = dict(
        target="demo",
        pipx_path=None,
        python="python3",
        pip_args=None,
        force=True,
        upgrade_pipx=False,
        ensure_path=True,
        debug=False,
    )
    payload.update(overrides)
    return type("Args", (), payload)


def test_resolve_pipx_installs_when_missing() -> None:
    deps = StubDeps()
    args = make_args(target="pkg")

    pipx.install_with_pipx(args, deps=deps)

    assert any("pip" in cmd and "pipx" in cmd for cmd in deps.commands)
    assert deps.commands[-1][-1] == "pkg"


def test_resolve_pipx_skips_install_when_present() -> None:
    deps = StubDeps(pipx_path="/opt/pipx")
    args = make_args(target="pkg")

    pipx.install_with_pipx(args, deps=deps)

    assert deps.commands[0][0] == "/opt/pipx"
    assert deps.commands[0][-1] == "pkg"


def test_normalize_target_prefers_real_path(tmp_path: Path) -> None:
    file_path = tmp_path / "pkg"
    file_path.write_text("", encoding="utf-8")

    normalized = pipx._normalize_target(str(tmp_path))

    assert normalized == str(tmp_path.resolve())
