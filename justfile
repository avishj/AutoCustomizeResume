# SPDX-FileCopyrightText: 2026 Avish Jha <avish.j@pm.me>
#
# SPDX-License-Identifier: AGPL-3.0-or-later

set dotenv-load

default:
    @just --list

lint:
    uvx pre-commit run --all-files


test *args:
    uv run pytest --cov --cov-report=term -n auto {{ args }}

build:
    uv build
    uvx twine check dist/*
    uv run --with dist/*.whl --no-project -- autocustomizeresume --help

docs:
    uv run mkdocs build --strict
    uv run mkdocs serve

ci:
    uvx pre-commit run --all-files
    uv run pytest --cov --cov-report=term --cov-report=html --cov-fail-under=70 -n auto
    just build
    uv run mkdocs build --strict

clean:
    rm -rf build/ dist/ *.egg-info/ .pytest_cache/ .ruff_cache/ .coverage htmlcov/ coverage.xml results.xml site/ .ty/
