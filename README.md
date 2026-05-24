# Spanish Housing Radar — Conversation Context

## What this is
A real estate opportunity finder for Spain. Scrapes Idealista → loads into MotherDuck (DuckDB cloud) → transforms with dbt (Medallion architecture) → Streamlit dashboard with Opportunity Score (0–100).

**Stack:** Python + BeautifulSoup + Scrapfly → MotherDuck → dbt Core → Streamlit  
**Environment:** WSL 2 Ubuntu, VSCode, Python 3.12, venv at `.venv/`

---

## Current status
- ✅ Extraction pipeline working end-to-end
- ✅ 3 rows loaded in `raw.idealista_listings` in MotherDuck (Madrid, sale)
- ✅ Scrapfly integrated (`asp=True`, `render_js=False` works for Idealista)
- ✅ Makefile, requirements.txt, .env, VSCode launch.json all working
- ⏳ **dbt models not created yet — this is the next step**
- ⏳ Streamlit app scaffolded but not connected to real data

---

## Project structure
```
spanish-housing-radar/
├── extraction/
│   ├── config.py                  # all settings from .env, dynamic URL builder
│   ├── run_extraction.py          # Typer CLI: --source, --city, --all-cities, --all
│   ├── aux_logger.py              # colored logging + rotating file handler
│   ├── debug_scrapfly.py          # diagnostic script (do NOT run again, wastes credits)
│   ├── scrapers/
│   │   ├── base.py                # AbstractScraper, _get_html() dispatches Scrapfly/requests
│   │   ├── idealista.py           # search-card parser, fixed _is_blocked()
│   │   └── fotocasa.py            # __NEXT_DATA__ JSON first, CSS fallback
│   ├── loaders/
│   │   └── motherduck_loader.py   # context manager, INSERT OR REPLACE upsert
│   └── schemas/
│       └── raw_listings.py        # Pydantic v2 validation + price/sqm sanity check
├── transform/                     # dbt project
│   ├── dbt_project.yml
│   ├── profiles.yml.example
│   ├── packages.yml               # dbt_utils, dbt_expectations
│   ├── macros/
│   │   ├── generate_schema_name.sql   # enforces exact names: bronze, silver, gold
│   │   └── price_per_sqm.sql          # reusable macro
│   └── models/
│       ├── bronze/                # ⚠️ EMPTY — needs stg_idealista__listings.sql
│       ├── silver/                # ⚠️ EMPTY — needs int_listings_unioned.sql etc
│       └── gold/                  # ⚠️ EMPTY — needs fct_listings_scored.sql etc
├── app/
│   ├── main.py
│   ├── connection.py              # st.cache_resource singleton
│   ├── queries/
│   │   ├── listings.sql
│   │   └── neighborhood_stats.sql
│   └── pages/
│       ├── 1_Search.py
│       ├── 2_Market_Stats.py
│       └── 3_Affordability.py
├── .vscode/
│   ├── launch.json                # F5 = Streamlit, dropdown = extraction/pytest
│   └── settings.json
├── .env.example
├── .gitignore
├── Makefile
├── requirements.txt
└── README.md
```

---

## MotherDuck schema

**Database:** `spanish_housing_radar`  
**Table:** `raw.idealista_listings` — 3 rows currently

```sql
source_id           VARCHAR   -- PK composite with source_name
source_name         VARCHAR   -- 'idealista'
raw_url             VARCHAR   -- https://www.idealista.com/inmueble/{id}/
raw_price_eur       DOUBLE
raw_operation_type  VARCHAR   -- 'sale' | 'rent'
raw_size_sqm        DOUBLE
raw_rooms           INTEGER   -- nullable
raw_bathrooms       INTEGER   -- nullable (not available on search cards)
raw_property_type   VARCHAR   -- 'apartment' | 'house' | 'penthouse' | 'studio'
raw_lat             DOUBLE    -- nullable (not available on search cards)
raw_lon             DOUBLE    -- nullable (not available on search cards)
raw_municipality    VARCHAR
raw_district        VARCHAR   -- nullable
raw_neighborhood    VARCHAR   -- nullable
_loaded_at          TIMESTAMPTZ
_run_id             VARCHAR
```

Sample data:
```
109947740 | idealista | 2100000 | sale | 137m² | 3 rooms | madrid | goya          | piso en calle alcalá
110438977 | idealista |  820000 | sale | 110m² | 4 rooms | madrid | sol           | piso en calle de la lechuga
110632197 | idealista | 3150000 | sale | 332m² | 5 rooms | madrid | cuatro caminos | piso en calle de raimundo...
```

---

## Key technical decisions already made

**Scrapfly:** `asp=True`, `render_js=False` — sufficient for Idealista. DataDome is bypassed by ASP alone. `render_js=True` costs 25–29 credits vs 1 and is NOT needed.

**`_is_blocked()` fix:** Only flags on literal string `"please enable js and disable any ad blocker"` or response <5KB with no `<article>` tag. Does NOT flag on `"captcha"` or `"datadome"` — these appear in Idealista's JS on every page including successful ones (this was the original bug).

**Search-card-only:** No detail page requests. `raw_lat`, `raw_lon`, `raw_bathrooms` are NULL at this stage. Phase 2 will add detail-page enrichment.

**Scrapfly credits:** ~805/1000 remaining on free tier (resets June 10). Keep `IDEALISTA_MAX_LISTINGS=30` and `IDEALISTA_MAX_SEARCH_PAGES=1` during dev. Each `make extract` call = 1 credit.

**dbt schema names:** `generate_schema_name.sql` macro enforces exact names `bronze`, `silver`, `gold` in MotherDuck — not `dev_bronze` etc.

**DuckDB version:** Must be `>=1.5.2` for MotherDuck compatibility.

---

## .env structure
```bash
MOTHERDUCK_TOKEN=...
MOTHERDUCK_DATABASE=spanish_housing_radar

SCRAPFLY_ENABLED=true
SCRAPFLY_API_KEY=...
SCRAPFLY_ASP=true
SCRAPFLY_COUNTRY=ES
SCRAPFLY_RENDER_JS=false          # false is enough for Idealista

IDEALISTA_MAX_SEARCH_PAGES=1      # keep low to save credits
IDEALISTA_MAX_LISTINGS=30
SCRAPER_DELAY_SECONDS=2
```

---

## requirements.txt key pins
```
duckdb==1.5.2          # MotherDuck requires >=1.5.2
dbt-duckdb==1.10.1
dbt-core==1.9.5
streamlit==1.44.1
scrapfly-sdk==0.10.3
pydantic==2.10.6
typer==0.15.1
tenacity==9.0.0
```

---

## Makefile commands
```bash
make extract CITY=madrid OP=sale   # extract one city (1 Scrapfly credit)
make extract-dry                   # validate without writing (1 credit)
make extract-all-cities            # all cities, one source
make check-db                      # row counts in MotherDuck
make dbt-deps                      # install dbt packages (once)
make transform                     # dbt run: bronze → silver → gold
make dbt-test                      # dbt test
make app                           # streamlit run app/main.py :8501
```

---

## Next step: build the dbt models

The `transform/models/` directories exist but are completely empty. Need to create all SQL files.

### Bronze
**`stg_idealista__listings.sql`** — reads `raw.idealista_listings`, incremental on `_loaded_at`, safe casts, adds metadata. One staging model per source portal.

### Silver
**`int_listings_unioned.sql`** — UNION ALL across sources, dedup with `ROW_NUMBER()`, normalise property types, compute `price_per_sqm` via macro.  
**`dim_neighborhoods.sql`** — distinct neighbourhood/municipality/district combinations.

### Gold
**`fct_listings_scored.sql`** — joins listings with neighbourhood stats, computes Z-score Opportunity Score 0–100.  
**`rpt_neighborhood_stats.sql`** — pre-aggregated benchmark table (median, p25, p75, stddev per neighbourhood × operation × property_type). Materialised as `table`.  
**`rpt_opportunities.sql`** — view on top of `fct_listings_scored`, filters `low_confidence=false`, Streamlit-ready.

### Opportunity Score formula
```sql
z_score  = (price_per_sqm - neighbourhood_median_ppsqm) / neighbourhood_stddev_ppsqm
z_clamped = GREATEST(-3, LEAST(3, z_score))
score     = GREATEST(0, LEAST(100, 50 - z_clamped * (50.0 / 3.0)))
-- 100 = very undervalued vs neighbourhood
-- 50  = exactly at median
-- 0   = very overpriced
deal_tier: great_deal (≥75) | good_deal (≥55) | fair (≥45) | overpriced (≥25) | very_overpriced
```

### dbt profiles.yml (transform/profiles.yml)
```yaml
spanish_housing_radar:
  target: dev
  outputs:
    dev:
      type: duckdb
      path: "md:spanish_housing_radar?motherduck_token={{ env_var('MOTHERDUCK_TOKEN') }}"
      threads: 4
```
`DBT_PROFILES_DIR=./transform` is set in `.env`.

### _sources.yml for Bronze
```yaml
sources:
  - name: raw
    database: spanish_housing_radar
    schema: raw
    tables:
      - name: idealista_listings
      - name: fotocasa_listings
```