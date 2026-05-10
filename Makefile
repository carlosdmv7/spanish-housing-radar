# Spanish Housing Radar — Makefile
# WSL Ubuntu: run `make help` to see all commands
# Assumes .venv is activated or make is run via `source .venv/bin/activate && make ...`

PYTHON    := .venv/bin/python
PIP       := .venv/bin/pip
STREAMLIT := .venv/bin/streamlit
DBT       := .venv/bin/dbt

.DEFAULT_GOAL := help

# ── Setup ─────────────────────────────────────────────────────────────────────
.PHONY: install
install: ## Create .venv and install all dependencies
	python3 -m venv .venv
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt
	cp .env.example .env
	cp transform/profiles.yml.example transform/profiles.yml
	@echo ""
	@echo "✅ Done! Next steps:"
	@echo "   1. Edit .env and add your MOTHERDUCK_TOKEN"
	@echo "   2. Edit transform/profiles.yml if needed (token is read from .env)"
	@echo "   3. Run: make dbt-deps"

.PHONY: dbt-deps
dbt-deps: ## Install dbt packages (dbt_utils, dbt_expectations)
	cd transform && $(DBT) deps

# ── Extraction ────────────────────────────────────────────────────────────────
.PHONY: extract
extract: ## Run extraction: idealista, madrid, sale (edit SOURCE/PROVINCE/OP to change)
	$(PYTHON) extraction/run_extraction.py \
		--source $(or $(SOURCE),idealista) \
		--province $(or $(PROVINCE),madrid) \
		--operation $(or $(OP),sale)

.PHONY: extract-dry
extract-dry: ## Dry-run extraction (no writes to MotherDuck)
	$(PYTHON) extraction/run_extraction.py \
		--source $(or $(SOURCE),idealista) \
		--province $(or $(PROVINCE),madrid) \
		--dry-run

# ── dbt ───────────────────────────────────────────────────────────────────────
.PHONY: transform
transform: ## Run full dbt pipeline: bronze → silver → gold
	cd transform && $(DBT) run

.PHONY: transform-bronze
transform-bronze: ## Run bronze models only
	cd transform && $(DBT) run --select bronze

.PHONY: test
test: ## Run dbt tests
	cd transform && $(DBT) test

.PHONY: transform-test
transform-test: transform test ## Run dbt pipeline then tests

# ── App ───────────────────────────────────────────────────────────────────────
.PHONY: app
app: ## Launch Streamlit app (or press F5 in VSCode)
	$(STREAMLIT) run app/main.py --server.port 8501 --server.headless true

# ── Full pipeline ─────────────────────────────────────────────────────────────
.PHONY: pipeline
pipeline: extract transform test ## Extract → Transform → Test (full nightly run)
	@echo "✅ Full pipeline complete."

# ── Code quality ──────────────────────────────────────────────────────────────
.PHONY: lint
lint: ## Lint with ruff
	.venv/bin/ruff check extraction/ app/

.PHONY: format
format: ## Format with black
	.venv/bin/black extraction/ app/ --line-length 100

.PHONY: pytest
pytest: ## Run Python unit tests
	.venv/bin/pytest extraction/ -v

# ── Help ──────────────────────────────────────────────────────────────────────
.PHONY: help
help:
	@echo "Spanish Housing Radar — available commands:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'
