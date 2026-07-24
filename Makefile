# Spanish Housing Radar — Makefile
# Dependencies are managed with uv (https://docs.astral.sh/uv/).
# `make install` runs `uv sync`, which creates .venv from uv.lock.

# Use absolute paths so `cd transform && $(DBT)` works correctly
# $(CURDIR) = project root, evaluated once at parse time. uv sync populates .venv.
PYTHON    := $(CURDIR)/.venv/bin/python
STREAMLIT := $(CURDIR)/.venv/bin/streamlit
DBT       := $(CURDIR)/.venv/bin/dbt

ifneq (,$(wildcard .env))
include .env
export MOTHERDUCK_TOKEN SCRAPFLY_API_KEY
endif

.DEFAULT_GOAL := help

# ── Setup ──────────────────────────────────────────────────────────────────────
.PHONY: install
install: ## Sync the uv-managed venv (from uv.lock) + copy config templates
	uv sync
	@test -f .env          || cp .env.example .env          && echo "  created .env"
	@test -f transform/profiles.yml || cp transform/profiles.yml.example transform/profiles.yml && echo "  created transform/profiles.yml"
	@echo ""
	@echo "✅  Done! Next steps:"
	@echo "   1. Edit .env → add MOTHERDUCK_TOKEN and SCRAPFLY_API_KEY"
	@echo "   2. make dbt-deps"
	@echo ""
	@echo "   (No uv yet?  curl -LsSf https://astral.sh/uv/install.sh | sh)"

.PHONY: dbt-deps
dbt-deps: ## Install dbt packages (run once after install)
	cd transform && $(DBT) deps

# ── Extraction ─────────────────────────────────────────────────────────────────

.PHONY: extract-dry
extract-dry: ## Dry-run: idealista madrid sale — validate without writing to MotherDuck
	$(PYTHON) extraction/run_extraction.py \
		--source idealista --city madrid --operation sale --dry-run

.PHONY: extract
extract: ## Single city (make extract CITY=valencia SOURCE=idealista OP=sale/rent)
	$(PYTHON) extraction/run_extraction.py \
		--source    $(or $(SOURCE),idealista) \
		--city      $(or $(CITY),madrid) \
		--operation $(or $(OP),sale)

.PHONY: extract-all-cities
extract-all-cities: ## One source, all cities (make extract-all-cities SOURCE=fotocasa)
	$(PYTHON) extraction/run_extraction.py \
		--source $(or $(SOURCE),idealista) \
		--all-cities

.PHONY: extract-all
extract-all: ## Full run: all sources × all cities × sale + rent
	$(PYTHON) extraction/run_extraction.py --all

.PHONY: ingest-ine
ingest-ine: ## Fetch the official INE house-price index → raw.ine_hpi (free, no credits)
	$(PYTHON) -m extraction.run_ine

.PHONY: ingest-ine-dry
ingest-ine-dry: ## Dry-run the INE feed — fetch + validate, no MotherDuck writes
	$(PYTHON) -m extraction.run_ine --dry-run

# ── dbt ────────────────────────────────────────────────────────────────────────
.PHONY: transform
transform: ## Full dbt run: bronze → silver → gold
	cd transform && $(DBT) run

.PHONY: transform-bronze
transform-bronze: ## Bronze models only
	cd transform && $(DBT) run --select bronze

.PHONY: dbt-test
dbt-test: ## Run all dbt tests
	cd transform && $(DBT) test

.PHONY: transform-test
transform-test: transform dbt-test ## dbt run + dbt test

.PHONY: transform-full-refresh
transform-full-refresh: ## Full dbt run with full-refresh (rebuilds all incrementals from scratch)
	cd transform && $(DBT) run --full-refresh
	
# ── App ────────────────────────────────────────────────────────────────────────
.PHONY: app
app: ## Launch Streamlit on :8501 (or press F5 in VSCode)
	$(STREAMLIT) run app/main.py --server.port 8501 --server.headless true

# ── Full pipeline ──────────────────────────────────────────────────────────────
.PHONY: pipeline
pipeline: extract-all transform dbt-test ## Nightly: extract + transform + test
	@echo "✅  Pipeline complete."

.PHONY: pipeline-prefect
pipeline-prefect: ## Nightly pipeline via Prefect (retries + structured logging)
	$(PYTHON) -m orchestration.flows.daily_pipeline

# ── Utilities ──────────────────────────────────────────────────────────────────
.PHONY: check-db
check-db: ## Show row counts for all raw tables in MotherDuck
	$(PYTHON) -c "\
import duckdb, os; \
from dotenv import load_dotenv; load_dotenv(); \
conn = duckdb.connect('md:spanish_housing_radar?motherduck_token=' + os.environ['MOTHERDUCK_TOKEN']); \
rows = conn.execute(\"SELECT schema_name, table_name FROM duckdb_tables() WHERE database_name = current_database() AND schema_name = 'raw' ORDER BY table_name\").fetchall(); \
[print(f'  raw.{r[1]:35s} → {conn.execute(f\"SELECT COUNT(*) FROM raw.{r[1]}\").fetchone()[0]:>6} rows') for r in rows] if rows else print('  No tables in raw schema yet — run make extract first')"

.PHONY: lint
lint: ## Lint with ruff
	$(CURDIR)/.venv/bin/ruff check extraction/ app/

.PHONY: format
format: ## Format with black
	$(CURDIR)/.venv/bin/black extraction/ app/ --line-length 100

.PHONY: pytest
pytest: ## Run Python unit tests
	$(CURDIR)/.venv/bin/pytest extraction/ orchestration/ -v
	$(CURDIR)/.venv/bin/pytest app/ -v

.PHONY: docker-build
docker-build: ## Build the pipeline Docker image
	docker build -t housing-radar .

.PHONY: docker-run
docker-run: ## Run the full pipeline in Docker (needs .env)
	docker run --rm --env-file .env housing-radar

# ── Help ───────────────────────────────────────────────────────────────────────
.PHONY: help
help:
	@echo "Spanish Housing Radar — available commands:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-22s\033[0m %s\n", $$1, $$2}'
