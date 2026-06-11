# ─────────────────────────────────────────────
# Crop Intelligence Agent — Makefile
# Usage: make <target>
# ─────────────────────────────────────────────

.PHONY: help setup lint typecheck test run-dashboard run-agent clean

PYTHON := .venv/bin/python
PIP    := .venv/bin/pip

help:  ## Show this help message
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

setup:  ## Create venv and install all dependencies
	python3 -m venv .venv
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt
	$(PIP) install -r requirements-dev.txt
	cp -n .env.example .env || true
	@echo "✅ Setup complete. Edit .env with your API keys."

lint:  ## Run ruff linter
	.venv/bin/ruff check crop_agent/

format:  ## Auto-fix formatting with ruff
	.venv/bin/ruff check --fix crop_agent/

typecheck:  ## Run mypy type checker
	.venv/bin/mypy crop_agent/

test:  ## Run tests with coverage (must be >= 80%)
	.venv/bin/pytest

test-fast:  ## Run tests without coverage (faster for dev)
	.venv/bin/pytest --no-cov -q

ci:  ## Run full CI pipeline: lint + typecheck + test
	make lint
	make typecheck
	make test

run-dashboard:  ## Start Streamlit dashboard
	$(PYTHON) -m streamlit run crop_agent/dashboard/app.py

run-agent:  ## Start the night agent scheduler (runs all tasks once)
	$(PYTHON) -m crop_agent.scheduler.night_agent --run-now

db-init:  ## Initialize database and run migrations
	$(PYTHON) -m crop_agent.database.init_db

clean:  ## Remove build artifacts and cache
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .mypy_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .ruff_cache -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
	rm -rf htmlcov/ .coverage coverage.xml
	@echo "✅ Clean complete"
