# spec-workflow-runner

Tools that keep the spec-workflow loop moving:

- `spec-workflow-run` – orchestrates Codex runs until all tasks in a spec are complete.
- `spec-workflow-monitor` – Rich-based dashboard to watch progress in real time.

## Installation

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -e '.[dev]'
```

The editable install provides both CLIs on your `$PATH` and pulls in the dev-only tooling
configured in `pyproject.toml`.

## Usage

Each CLI ships with `--help`, but the common flows look like:

```bash
spec-workflow-run --project /path/to/repo --spec my-spec
spec-workflow-run --project ... --spec ... --dry-run  # simulate only
spec-workflow-monitor --project /path/to/repo --spec my-spec
```

Both commands expect to find a `config.json` in the working directory unless a different
`--config` path is provided.

## Quality Toolkit

The repo uses modern tooling wired through `pyproject.toml`:

- `ruff` for linting (`ruff check src tests`)
- `black` for formatting (`black src tests`)
- `mypy` for static typing (`mypy src`)
- `pytest` for tests (`pytest`)

You can run the whole suite in one go via:

```bash
ruff check src tests && black --check src tests && mypy src && pytest
```

Feel free to script this (e.g., with `make`) as the project grows.
