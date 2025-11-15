PYTHON ?= python
PACKAGE = spec_workflow_runner
SRC = src tests

.PHONY: install format lint typecheck test check

install:
	$(PYTHON) -m pip install -e .[dev]

format:
	$(PYTHON) -m black $(SRC)

lint:
	$(PYTHON) -m ruff check $(SRC)

typecheck:
	$(PYTHON) -m mypy src

test:
	$(PYTHON) -m pytest

check: lint typecheck test
