# AGENT PLAYBOOK

This project now lives inside `src/spec_workflow_runner/` and follows a high-quality, CLI-first workflow. When jumping in, apply the following principles distilled from `CLAUDE.md` and our current tooling stack.

## Engineering Principles
- **Break compatibility when it helps** – do not cling to legacy APIs unless the user explicitly requires backward support.
- **Keep code small & focused** – target ≤500 LOC per file and ≤50 LOC per function; apply SOLID, DI, SSOT, KISS, and SLAP to maintain clarity.
- **Dependency injection everywhere** – external services, subprocesses, and IO should be injected/mocked to keep tests deterministic.
- **Fail fast with explicit errors** – validate inputs immediately, raise domain-specific exceptions, and never leak secrets/PII in logs.
- **Structured logging** – prefer JSON payloads including timestamp, level, service, event, and context details; ensure every CLI has an opt-in debug flag.

## Tooling & Quality Gates
Run the full suite before shipping any change:

```bash
make lint        # ruff check src tests
make format      # black src tests
make typecheck   # mypy src
make test        # pytest
make check       # lint + typecheck + test
```

Targets depend on an editable install:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
```

Aim for ≥80 % coverage overall (≥90 % on critical paths) and keep each PR green locally before relying on CI.

- Always reuse the repo’s `.venv` when present: `source .venv/bin/activate`. Install missing deps via `pip install -e '.[dev]'` (quotes required for extras). Run commands with the virtualenv active (`python -m pytest`, `ruff`, etc.) so they pick up installed tooling.
- Shells may cache missing executables; after installing new entry points run `hash -r` (bash) or `rehash` (zsh) before calling `spec-workflow-run` / `spec-workflow-monitor`.

## Workflow Expectations
- CLIs are the canonical entry points (`spec-workflow-run`, `spec-workflow-monitor`); build/debug new features behind flags before expanding scope.
- Prefer modern Python 3.11 features (pattern matching, type aliases, `|` unions) where they improve readability.
- Add or update pytest suites whenever behavior changes; no feature ships without tests.
- Keep Rich UI or other heavy deps encapsulated; utilities in `spec_workflow_runner.utils` remain UI-agnostic for reuse.

Stick to this playbook and future agents will have a smooth, high-signal runway.
