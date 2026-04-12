# Capture extra CLI arguments as ARGS
ARGS ?= $(filter-out $@,$(MAKECMDGOALS))

# Prevent make from treating extra args as targets
%:
	@:

PY_ARGS := $(filter %.py,$(ARGS))

actions = \
	setup \
	test \
	cov \
	lint-check \
	lint-format \
	docs-build \
	docs-serve \
	docs-deploy \
	build \
	publish

# ARGS used for `test`. `PY_ARGS` used for `lint` and `format`
PY_ARGS := $(or $(filter %.py,$(ARGS)),sqladmin)

setup:
	uv sync --all-groups

test:
	uv run coverage run -a --concurrency=thread,greenlet -m pytest $(ARGS)

cov:
	uv run coverage report
	uv run coverage xml

lint:
	uv run ruff check $(PY_ARGS)
	uv run ruff format --check $(PY_ARGS)
	uv run mypy $(PY_ARGS)

format:
	uv run ruff format $(PY_ARGS)
	uv run ruff check --fix $(PY_ARGS)

secure:
	uv run bandit -r sqladmin --config pyproject.toml

docs-build:
	uv run mkdocs build

docs-serve:
	uv run mkdocs serve --dev-addr localhost:8080

docs-deploy:
	uv run mkdocs gh-deploy --force

build:
	uv build

publish:
	uv publish


.PHONY: setup test cov lint-check lint-format docs-build docs-serve docs-deploy build publish
