"""Tests for the run_tasks orchestration helpers."""
from __future__ import annotations

from spec_workflow_runner.run_tasks import TimeoutBudget


class FakeClock:
    """Deterministic monotonic clock for timeout tests."""

    def __init__(self) -> None:
        self._value = 0.0

    def advance(self, seconds: float) -> None:
        self._value += seconds

    def __call__(self) -> float:
        return self._value


def test_timeout_budget_expires_after_limit() -> None:
    clock = FakeClock()
    budget = TimeoutBudget(10, monotonic=clock)

    clock.advance(5)
    assert budget.expired() is False

    clock.advance(6)
    assert budget.expired() is True


def test_timeout_budget_reset_provides_new_window() -> None:
    clock = FakeClock()
    budget = TimeoutBudget(10, monotonic=clock)

    clock.advance(9)
    assert budget.expired() is False

    budget.reset()
    clock.advance(9)
    assert budget.expired() is False

    clock.advance(2)
    assert budget.expired() is True
