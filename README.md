# Spanish Housing Radar

Identify real estate opportunities across Spain. The app compares any listing's price per m² against its neighbourhood median and surfaces an **Opportunity Score (0–100)** — so you can find undervalued properties at a glance.

**Stack:** Python scrapers → MotherDuck (DuckDB cloud) → dbt Core (Medallion) → Streamlit

---

## Architecture overview

```
Python scrapers  →  MotherDuck (raw)  →  dbt Bronze  →  dbt Silver  →  dbt Gold  →  Streamlit
  Idealista             DuckDB cloud        raw layer      cleaned       scored        dashboard
  Fotocasa
  (+ future)
```

The three dbt layers follow the **Medallion architecture**:

| Layer | Schema | Purpose |
|-------|--------|---------|
| Bronze | `bronze.*` | Raw data as-scraped, append/upsert only |
| Silver | `silver.*` | Cleaned, normalised, deduplicated |
| Gold | `gold.*` | Business-ready tables with Opportunity Score |

---

## Prerequisites

- **WSL 2** running Ubuntu 22.04+ (tested on Ubuntu 22.04 & 24.04)
- **Python 3.11+** — check with `python3 --version`
- **VSCode** with the [Remote - WSL](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-wsl) extension
- A free **MotherDuck** account → [app.motherduck.com](https://app.motherduck.com)

If Python 3.11+ is missing on your WSL:
```bash
sudo apt update && sudo apt install -y python3.11 python3.11-venv python3-pip
```

---

## Quick start (WSL + VSCode)

### 1. Clone and open in VSCode

```bash
git clone https://github.com/your-org/spanish-housing-radar.git
cd spanish-housing-radar
code .          # opens the project in VSCode via WSL
```

VSCode will prompt you to install the recommended extensions (`.vscode/extensions.json`) — accept all.

### 2. Create the virtual environment

```bash
make install
```

This runs:
```
python3 -m venv .venv
pip install -r requirements.txt
cp .env.example .env
cp transform/profiles.yml.example transform/profiles.yml
```

VSCode will automatically detect `.venv` as your interpreter (set in `.vscode/settings.json`).
If it doesn't: `Ctrl+Shift+P` → **Python: Select Interpreter** → pick `.venv/bin/python`.

### 3. Add your MotherDuck token

```bash
# Get your token at: https://app.motherduck.com → Settings → Access Tokens
nano .env
```

Set:
```
MOTHERDUCK_TOKEN=your_token_here
```

`transform/profiles.yml` reads this automatically via `{{ env_var('MOTHERDUCK_TOKEN') }}` — you don't need to paste it twice.

### 4. Install dbt packages

```bash
source .venv/bin/activate
make dbt-deps
```

### 5. Run your first extraction (dry run)

```bash
make extract-dry SOURCE=idealista PROVINCE=madrid
```

If you have Idealista API credentials (see [API access](#idealista-api-access)):
```bash
make extract SOURCE=idealista PROVINCE=madrid OP=sale
```

### 6. Transform with dbt

```bash
make transform        # runs bronze → silver → gold
make test             # runs all dbt schema tests
```

### 7. Launch the Streamlit app

**Option A — terminal:**
```bash
make app
# Open http://localhost:8501 in your browser
```

**Option B — press F5 in VSCode** (uses `.vscode/launch.json` → "▶ Streamlit App")

> WSL note: if your browser doesn't open automatically, navigate to `http://localhost:8501` manually. Port forwarding from WSL → Windows is automatic in modern WSL 2.

---

## Project structure

```
spanish-housing-radar/
│
├── extraction/                 # Python extraction layer
│   ├── config.py               # All settings from environment
│   ├── run_extraction.py       # CLI entrypoint (also F5-runnable)
│   ├── schemas/
│   │   └── raw_listings.py     # Pydantic v2 validation before load
│   ├── scrapers/
│   │   ├── base.py             # AbstractScraper (retry, rate limiting)
│   │   ├── idealista.py        # Idealista API v3.5 (OAuth2)
│   │   └── fotocasa.py         # Fotocasa HTML scraper
│   └── loaders/
│       └── motherduck_loader.py  # DuckDB client → MotherDuck upsert
├── data/
│   └── debug/
│       └── idealista_search_madrid_sale.html
│
├── scripts/
│   └── test_scrapfly_idealista.py
│
├── transform/                  # dbt project
│   ├── dbt_project.yml
│   ├── profiles.yml.example    # Copy to profiles.yml (git-ignored)
│   ├── packages.yml            # dbt_utils, dbt_expectations
│   ├── macros/
│   │   ├── generate_schema_name.sql  # Enforces bronze/silver/gold
│   │   └── price_per_sqm.sql         # DRY formula
│   └── models/
│       ├── bronze/             # stg_idealista__listings, stg_fotocasa__listings
│       ├── silver/             # int_listings_unioned, dim_neighborhoods
│       └── gold/               # fct_listings_scored, rpt_opportunities
│
├── app/                        # Streamlit frontend
│   ├── main.py                 # Entry point (F5 target)
│   ├── connection.py           # Singleton MotherDuck connector
│   ├── queries/                # .sql files — never inline SQL in Python
│   │   ├── listings.sql
│   │   └── neighborhood_stats.sql
│   └── pages/
│       ├── 1_Search.py         # Filters + Opportunity Score + map
│       ├── 2_Market_Stats.py   # Neighbourhood price distributions
│       └── 3_Affordability.py  # Mortgage calculator (Phase 2)
│
├── .vscode/
│   ├── launch.json             # F5 = Streamlit, Shift+F5 = extraction
│   ├── settings.json           # Interpreter, formatter, WSL tweaks
│   └── extensions.json         # Recommended extensions
│
├── .env.example                # Template — copy to .env
├── .gitignore
├── Makefile                    # make install | extract | transform | app
├── requirements.txt
└── README.md
```

---

## VSCode F5 launch configurations

`.vscode/launch.json` contains three configurations selectable from the Run panel (`Ctrl+Shift+D`):

| Name | What it does |
|------|--------------|
| **▶ Streamlit App** | Starts the app on port 8501 |
| **🔄 Run Extraction (Madrid)** | Runs `run_extraction.py` with `--dry-run` |
| **🧪 Pytest** | Runs the Python test suite |

Switch between them in the dropdown at the top of the Run & Debug panel before pressing F5.

---

## Makefile reference

```bash
make install          # Create .venv + install deps + copy config templates
make dbt-deps         # Install dbt packages (run once after install)
make extract          # Run extraction (SOURCE=, PROVINCE=, OP= overrides)
make extract-dry      # Dry-run — validates without writing to MotherDuck
make transform        # Full dbt run: bronze → silver → gold
make transform-bronze # Bronze models only (fast iteration)
make test             # dbt test suite
make transform-test   # dbt run + dbt test
make app              # Launch Streamlit on :8501
make pipeline         # Full nightly run: extract + transform + test
make lint             # ruff
make format           # black
make pytest           # Python unit tests
```

---

## Opportunity Score explained

The score (0–100) is a **Z-score** of a listing's price/m² relative to its neighbourhood, inverted and scaled:

```
z_score   = (listing_ppsqm - neighbourhood_median_ppsqm) / neighbourhood_stddev_ppsqm
z_clamped = GREATEST(-3, LEAST(3, z_score))
score     = 50 - z_clamped × (50 / 3)
```

| Score range | Label | Meaning |
|-------------|-------|---------|
| 75–100 | Great deal | 1.5+ std below median |
| 55–74 | Good deal | Below median |
| 45–54 | Fair | At or near median |
| 25–44 | Overpriced | Above median |
| 0–24 | Very overpriced | 1.5+ std above median |

Listings in neighbourhoods with fewer than 10 comparables are flagged `low_confidence = true` and excluded from the app until more data is collected.

---

## Idealista API access

The `IdealistaScraper` uses the official **Idealista API v3.5** which requires partner approval:

1. Apply at [developers.idealista.com/access-request](https://developers.idealista.com/access-request)
2. Add your credentials to `.env`:
   ```
   IDEALISTA_API_KEY=your_key
   IDEALISTA_API_SECRET=your_secret
   ```
3. Without credentials, the scraper logs a warning and returns an empty set — the pipeline won't crash.

---

## Adding a new data source (Phase 2 pattern)

1. Create `extraction/scrapers/your_source.py` inheriting `AbstractScraper`
2. Add it to `SCRAPER_REGISTRY` in `run_extraction.py`
3. Add the raw table name to `RAW_TABLE_MAP` in `config.py`
4. Create `transform/models/bronze/stg_your_source__listings.sql` with the same output columns as the existing staging models
5. Add the new source to the `{% for model in sources %}` loop in `int_listings_unioned.sql`

Silver and Gold models — including the Opportunity Score — pick it up automatically.

---

## Running in production (GitHub Actions)

`.github/workflows/daily_extract_and_transform.yml` runs the full pipeline on a cron:

```yaml
on:
  schedule:
    - cron: '0 6 * * *'   # 06:00 UTC daily
```

Secrets to add in your GitHub repo settings:
- `MOTHERDUCK_TOKEN`
- `IDEALISTA_API_KEY`
- `IDEALISTA_API_SECRET`

---

## Troubleshooting (WSL)

**`python3: command not found`**
```bash
sudo apt install python3.11 python3.11-venv
```

**VSCode doesn't see the `.venv` interpreter**
Press `Ctrl+Shift+P` → *Python: Select Interpreter* → *Enter interpreter path* → `./.venv/bin/python`

**Port 8501 not reachable in Windows browser**
WSL 2 forwards ports automatically. If it doesn't work, run `wsl hostname -I` to get the WSL IP and navigate to `http://<IP>:8501`.

**MotherDuck connection timeout**
Check that your `MOTHERDUCK_TOKEN` in `.env` is correct and not expired. Tokens can be regenerated at [app.motherduck.com](https://app.motherduck.com) → Settings.

**dbt can't find `profiles.yml`**
```bash
export DBT_PROFILES_DIR=$(pwd)/transform
# or add to .env: DBT_PROFILES_DIR=./transform
```
