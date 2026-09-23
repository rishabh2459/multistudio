# Multicam Studio — developer commands
# Run `make help` to see everything.

.DEFAULT_GOAL := help
SAMPLES ?= samples

.PHONY: help setup doctor lint format typecheck test test-accuracy cov \
        schemas schemas-check fetch-models gt-audio gt-build gt-check check clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

setup: ## One-command setup: Python env, JS deps, git hooks, generated types
	@git rev-parse --git-dir >/dev/null 2>&1 || git init -b main
	uv sync
	pnpm install
	uv run pre-commit install
	$(MAKE) schemas
	@echo ""
	@echo "Setup complete. Run 'make doctor' to verify your toolchain."

doctor: ## Check that all required tools are installed and suitable
	uv run python scripts/doctor.py

lint: ## Lint Python + JS/TS
	uv run ruff check .
	pnpm lint

format: ## Auto-format everything
	uv run ruff check --fix .
	uv run ruff format .
	pnpm format

typecheck: ## Static type checks (mypy strict + tsc)
	uv run mypy
	pnpm typecheck

test: ## Fast tests (unit + integration, no real footage)
	uv run pytest -m "not accuracy"

test-accuracy: ## Real-footage accuracy benchmarks (needs samples/)
	uv run pytest -m accuracy

cov: ## Tests with coverage report
	uv run pytest -m "not accuracy" --cov=multicam_engine --cov-report=term-missing

schemas: ## Regenerate JSON Schema + TypeScript types from Python models
	uv run python scripts/export_schemas.py
	pnpm --filter @multicam/types generate

schemas-check: ## Fail if generated schema/types are out of date
	uv run python scripts/export_schemas.py --check
	pnpm --filter @multicam/types generate:check

fetch-models: ## Download bundled AI model files (verified by SHA-256)
	uv run python packaging/scripts/fetch_models.py

gt-audio: ## Extract WAVs for labeling: make gt-audio REC=samples/T1
	uv run multicam gt extract-audio $(REC)

gt-build: ## Build ground_truth.json from labels: make gt-build REC=samples/T1
	uv run multicam gt build $(REC)

gt-check: ## Validate all ground-truth files under samples/
	uv run multicam gt check $(SAMPLES)

gt-eval: ## Score sync vs ground truth: make gt-eval REC=samples/T1
	uv run multicam gt eval-sync $(REC)

check: lint typecheck test schemas-check ## Everything CI runs
	pnpm format:check
	uv run ruff format --check .

clean: ## Remove caches and build artifacts
	rm -rf .mypy_cache .ruff_cache .pytest_cache .coverage htmlcov
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
