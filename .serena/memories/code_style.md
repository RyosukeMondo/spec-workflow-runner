# Code Style & Conventions
- Python 3.11+ with `from __future__ import annotations` usage, dataclasses, and exhaustive type hints (`Path`, `Sequence`, custom `RunnerError`).
- Follows PEP 8 naming, small single-purpose functions, and descriptive docstrings summarizing responsibilities.
- Uses `pathlib.Path` for filesystem IO, `subprocess.run(..., check=True)` for git commands, and favors immutable dataclasses with helper properties/methods (e.g., `TaskStats.total`).
- User interactions use simple CLI menus via `choose_option`; keep CLI UX text-mode friendly and raise `SystemExit`/custom errors for validation failures.
- Logging uses f-strings and explicit prints; when extending, prefer same stdout/stderr patterns and keep `rich` components encapsulated in monitor module.