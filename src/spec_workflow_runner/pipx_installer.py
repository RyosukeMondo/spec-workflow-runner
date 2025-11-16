"""CLI helper that keeps the pipx-based install of this project up to date."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

SERVICE_NAME = "spec-workflow-pipx"
DEFAULT_TARGET = str(Path(__file__).resolve().parents[2])


class PipxError(Exception):
    """Domain-specific error raised for pipx orchestration issues."""


Command = Sequence[str]
CommandRunner = Callable[[Command], None]
WhichFunc = Callable[[str], str | None]
NowFunc = Callable[[], datetime]


def _default_run(command: Command) -> None:
    subprocess.run(command, check=True)


def _default_now() -> datetime:
    return datetime.now(UTC)


@dataclass(slots=True)
class Dependencies:
    """External side effects injected for testability."""

    run: CommandRunner = _default_run
    which: WhichFunc = shutil.which
    now: NowFunc = _default_now


class JsonLogger:
    """Emit structured log lines understood by the CLI workflow."""

    def __init__(self, *, debug: bool, now: NowFunc) -> None:
        self._debug_enabled = debug
        self._now = now

    def info(self, event: str, **context: object) -> None:
        self._emit("info", event, context)

    def debug(self, event: str, **context: object) -> None:
        if not self._debug_enabled:
            return
        self._emit("debug", event, context)

    def error(self, event: str, **context: object) -> None:
        self._emit("error", event, context)

    def _emit(self, level: str, event: str, context: dict[str, object]) -> None:
        payload = {
            "ts": self._now().isoformat(),
            "level": level,
            "service": SERVICE_NAME,
            "event": event,
            "context": {key: _stringify(value) for key, value in context.items()},
        }
        print(json.dumps(payload))


def parse_args() -> argparse.Namespace:
    """Return CLI arguments."""
    parser = argparse.ArgumentParser(description="Install or update the pipx-managed build.")
    parser.add_argument(
        "--target",
        default=DEFAULT_TARGET,
        help=(
            "Package spec or path passed to `pipx install`. "
            "Defaults to the repository root, enabling local installs."
        ),
    )
    parser.add_argument(
        "--pipx",
        dest="pipx_path",
        help="Explicit pipx executable to use (defaults to discovery via PATH).",
    )
    parser.add_argument(
        "--python",
        default=sys.executable,
        help="Python interpreter used to bootstrap pipx (default: current).",
    )
    parser.add_argument(
        "--pip-args",
        help="Optional extra pip arguments forwarded through pipx (e.g. '--pre').",
    )
    parser.add_argument(
        "--no-force",
        dest="force",
        action="store_false",
        help="Do not pass --force to pipx install (default is to force reinstall).",
    )
    parser.set_defaults(force=True)
    parser.add_argument(
        "--upgrade-pipx",
        action="store_true",
        help="Always upgrade pipx before installing the target package.",
    )
    parser.add_argument(
        "--no-ensure-path",
        dest="ensure_path",
        action="store_false",
        help="Skip running 'pipx ensurepath' after installing pipx.",
    )
    parser.set_defaults(ensure_path=True)
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable verbose debug logging.",
    )
    return parser.parse_args()


def install_with_pipx(args: argparse.Namespace, deps: Dependencies | None = None) -> None:
    """Ensure pipx exists and (re)install the requested target."""
    deps = deps or Dependencies()
    logger = JsonLogger(debug=args.debug, now=deps.now)
    pipx_path = resolve_pipx(
        python=args.python,
        requested=args.pipx_path,
        upgrade=args.upgrade_pipx,
        ensure_path=args.ensure_path,
        deps=deps,
        logger=logger,
    )
    install_target(
        pipx_path=pipx_path,
        target=args.target,
        force=args.force,
        pip_args=args.pip_args,
        deps=deps,
        logger=logger,
    )


def resolve_pipx(
    *,
    python: str,
    requested: str | None,
    upgrade: bool,
    ensure_path: bool,
    deps: Dependencies,
    logger: JsonLogger,
) -> str:
    """Return a usable pipx executable, installing it if necessary."""
    pipx_path = requested or deps.which("pipx")
    need_install = pipx_path is None or upgrade
    if need_install:
        logger.info("pipx.bootstrap", python=python, upgrade=str(upgrade))
        command = [python, "-m", "pip", "install", "--user", "--upgrade", "pipx"]
        deps.run(command)
        if ensure_path:
            logger.debug("pipx.ensurepath", python=python)
            deps.run([python, "-m", "pipx", "ensurepath"])
        pipx_path = requested or deps.which("pipx")
    if not pipx_path:
        logger.error("pipx.not_found")
        raise PipxError(
            "pipx executable not found on PATH even after installation. "
            "Ensure your user base binary directory is on PATH."
        )
    logger.debug("pipx.resolved", path=pipx_path)
    return pipx_path


def install_target(
    *,
    pipx_path: str,
    target: str,
    force: bool,
    pip_args: str | None,
    deps: Dependencies,
    logger: JsonLogger,
) -> None:
    """Run `pipx install` for the provided target."""
    normalized_target = _normalize_target(target)
    command: list[str] = [pipx_path, "install"]
    if force:
        command.append("--force")
    if pip_args:
        command.extend(["--pip-args", pip_args])
    command.append(normalized_target)
    logger.info(
        "pipx.install",
        pipx=pipx_path,
        target=normalized_target,
        force=str(force),
        pip_args=pip_args or "",
    )
    deps.run(command)


def _normalize_target(raw: str) -> str:
    path = Path(raw)
    if path.exists():
        return str(path.resolve())
    return raw


def _stringify(value: object) -> str:
    if isinstance(value, Path):
        return str(value)
    if value is None:
        return ""
    return str(value)


def main() -> int:
    args = parse_args()
    try:
        install_with_pipx(args)
        return 0
    except PipxError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except subprocess.CalledProcessError as exc:
        print(f"Command failed: {exc}", file=sys.stderr)
        return exc.returncode or 1


if __name__ == "__main__":
    raise SystemExit(main())
