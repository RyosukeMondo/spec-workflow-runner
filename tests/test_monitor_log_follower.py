from __future__ import annotations

from pathlib import Path

from spec_workflow_runner.monitor import LogFollower


def test_log_follower_reads_new_lines(tmp_path: Path) -> None:
    follower = LogFollower(tmp_path, pattern="*.log", max_lines=5)
    follower.poll()
    assert follower.lines == []

    log_path = tmp_path / "task_1.log"
    log_path.write_text("first\n", encoding="utf-8")

    follower.poll()
    assert follower.lines == ["first"]

    with log_path.open("a", encoding="utf-8") as handle:
        handle.write("second\nthird\n")

    follower.poll()
    assert follower.lines[-2:] == ["second", "third"]


def test_log_follower_switches_to_latest_file(tmp_path: Path) -> None:
    log_a = tmp_path / "task_1.log"
    log_a.write_text("old\n", encoding="utf-8")
    follower = LogFollower(tmp_path, pattern="*.log", max_lines=5)
    follower.poll()

    log_b = tmp_path / "task_2.log"
    log_b.write_text("new\n", encoding="utf-8")

    follower.poll()
    assert follower.lines == ["new"]
    assert follower.current_path == log_b
