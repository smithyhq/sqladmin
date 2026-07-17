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
	build \
	publish

# ARGS used for `test`. `PY_ARGS` used for `lint` and `format`
PY_ARGS := $(or $(filter %.py,$(ARGS)),sqladmin tests)

# Locale code for `i18n-init` (e.g. `make i18n-init LOCALE=fr`)
LOCALE ?=

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

# Extract translatable strings into the .pot template and sync every catalog.
i18n-extract:
	uv run python -c "import os; os.makedirs('sqladmin/translations', exist_ok=True)"
	uv run pybabel extract -F babel.cfg -o sqladmin/translations/admin.pot .
	uv run pybabel update -i sqladmin/translations/admin.pot -d sqladmin/translations -D admin

# Create a catalog for a new locale, e.g. `make i18n-init LOCALE=fr`.
i18n-init:
	uv run pybabel init -i sqladmin/translations/admin.pot -d sqladmin/translations -D admin -l $(LOCALE)

# Compile .po catalogs into the binary .mo files loaded at runtime.
i18n-compile:
	uv run pybabel compile -d sqladmin/translations -D admin

docs-build:
	uv run zensical build

docs-serve:
	uv run zensical serve --dev-addr localhost:8080

build:
	uv build

publish:
	uv publish


.PHONY: setup test cov lint-check lint-format i18n-extract i18n-init i18n-compile docs-build docs-serve build publish