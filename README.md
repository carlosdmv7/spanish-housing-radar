# 🏘️ Spanish Housing Radar

**An end-to-end analytics-engineering pipeline that finds undervalued homes across Spain.**
It scrapes live listings from Idealista, models them through a Medallion (bronze → silver → gold)
dbt project on a cloud warehouse, and serves an **Opportunity Score (0–100)** per listing in an
interactive Streamlit app — surfacing deals priced below their neighbourhood's market rate.

<p align="center">
  <a href="https://github.com/carlosdmv7/spanish-housing-radar/actions/workflows/ci.yml">
    <img alt="CI" src="https://github.com/carlosdmv7/spanish-housing-radar/actions/workflows/ci.yml/badge.svg"></a>
  <img alt="Python"     src="https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white">
  <img alt="uv"         src="https://img.shields.io/badge/deps-uv-DE5FE9?logo=uv&logoColor=white">
  <img alt="dbt"        src="https://img.shields.io/badge/dbt-1.9-FF694B?logo=dbt&logoColor=white">
  <img alt="DuckDB"     src="https://img.shields.io/badge/MotherDuck-DuckDB-FFF000?logo=duckdb&logoColor=black">
  <img alt="Streamlit"  src="https://img.shields.io/badge/Streamlit-1.60-FF4B4B?logo=streamlit&logoColor=white">
  <img alt="Prefect"    src="https://img.shields.io/badge/Prefect-orchestration-024DFD?logo=prefect&logoColor=white">
  <img alt="Docker"     src="https://img.shields.io/badge/Docker-pipeline-2496ED?logo=docker&logoColor=white">
  <img alt="License"    src="https://img.shields.io/badge/license-MIT-green">
</p>

> **🔗 Live demo:** https://spanish-housing-radar-carlosdmv7.streamlit.app/
> **📊 dbt docs (lineage & tests):** https://carlosdmv7.github.io/spanish-housing-radar/

![Opportunities — listings scored against their local market](docs/img/opportunities.png)

<details>
<summary>📸 More screenshots — Market, Mortgage, Affordability, How it works</summary>

![Market overview](docs/img/market.png)
![Mortgage simulator](docs/img/mortgage.png)
![Affordability index](docs/img/affordability.png)
![How it works & data quality](docs/img/how_it_works.png)

</details>

> **ℹ️ On the data:** listing scraping is paused (Scrapfly credits), but the pipeline is
> **not** frozen: a free, keyless **INE house-price-index** feed refreshes the warehouse on
> a weekly cron, so the app keeps showing current official market context. Listing scraping
> resumes by flipping one repo variable (`SCRAPFLY_ENABLED=true`) when credits return.
> Every page carries a freshness header with the live figures, and the
> **[How it works & data quality](https://spanish-housing-radar-carlosdmv7.streamlit.app/how-it-works)**
> page states what this data can and cannot tell you.

---

## Why this project

Spanish housing portals tell you the *price* of a flat, but never whether that price is *good*.
"€280k for 90 m² in this area" means nothing without a benchmark. **Spanish Housing Radar builds
that benchmark from data**: it compares every listing against the live €/m² distribution of its own
neighbourhood and quantifies how much of a deal it is.

It's also a deliberate showcase of a **modern, governed data stack** — the same problems I solve
professionally (reliable ELT, trusted metrics, a single source of truth), built in the open and
fully reproducible.

---

## Architecture

```mermaid
flowchart LR
    subgraph SRC["Sources"]
        I["Idealista"]
        F["Fotocasa<br/><i>(scraper ready)</i>"]
        N["INE IPV<br/>official price index"]
    end

    subgraph EXTRACT["Extraction · Python"]
        SC["Scrapfly<br/>anti-bot proxy"]
        PY["Typer CLI scrapers<br/>Pydantic validation"]
        NE["INE Tempus3 client<br/>(free · no credits)"]
    end

    subgraph WH["MotherDuck · DuckDB (cloud)"]
        RAW["raw.*<br/><b>Bronze source</b>"]
        BRONZE["staging<br/>(1_bronze)"]
        SILVER["intermediate + dims<br/>(2_silver)"]
        GOLD["facts + reports<br/>(3_gold)"]
    end

    APP["Streamlit app<br/>5 pages"]

    I --> SC --> PY
    F -.-> SC
    N --> NE
    PY -->|"INSERT OR REPLACE<br/>(idempotent upsert)"| RAW
    NE -->|"idempotent upsert"| RAW
    RAW --> BRONZE --> SILVER --> GOLD --> APP

    ORCH["⏱️ Prefect<br/>daily schedule + retries"]
    CI["🧪 GitHub Actions<br/>lint + tests + dbt build"]
    ORCH -.orchestrates.-> PY
    ORCH -.orchestrates.-> GOLD
    CI -.validates.-> GOLD
```

**Legend:** solid = core data flow · dashed = orchestration/validation layers wrapping it.

| Layer | Tech | Role |
|---|---|---|
| **Ingestion** | Python · BeautifulSoup · Scrapfly · Pydantic · Typer | Robust scraping behind an anti-bot proxy; schema-validated; idempotent loads |
| **Market context** | INE Tempus3 JSON API | Free, keyless feed of the official house-price index (IPV) — grounds asking prices against transaction-based reality; runs even while scraping is parked |
| **Warehouse** | MotherDuck (DuckDB in the cloud) | Cheap, serverless, zero-ops analytical store |
| **Transformation** | dbt Core (Medallion: bronze → silver → gold) | Tested, documented, lineage-tracked SQL models |
| **Orchestration** | Prefect | `extract → dbt build` flow with task-level retries + structured logging, triggered daily by a GitHub Actions cron (`.github/workflows/daily_pipeline.yml`) |
| **CI/CD** | GitHub Actions | Ruff + pytest + `dbt build` against an isolated `ci_*` schema on every PR (`.github/workflows/ci.yml`) |
| **Serving** | Streamlit · Altair · pydeck | 5-page interactive analytical app; charts inherit one brand theme, no CSS injection |

---

## The Opportunity Score

The heart of the product. For each listing we compute its price per m² and compare it to the
**median and standard deviation of comparable listings** (same operation × property type):

```text
z_score   = (price_per_sqm − benchmark_median_ppsqm) / benchmark_stddev_ppsqm
z_clamped = clamp(z_score, −3, +3)
score     = clamp(50 − z_clamped × (50/3), 0, 100)
```

| Score | Meaning | Deal tier |
|---|---|---|
| **100** | far below market | `great_deal` (≥75) |
| **50** | exactly at the median | `good_deal` (≥55) · `fair` (≥45) |
| **0** | far above market | `overpriced` (≥25) · `very_overpriced` |

**Hierarchical benchmark.** Spanish listings are sparse at the neighbourhood level, so comparing a
flat only against its own barrio would mean comparing it against itself (z-score 0 → a meaningless
"fair" 50). Instead the score picks the **finest grain with enough comparables**: neighbourhood →
district → **city**, controlled by `min_comps_for_benchmark` (default 8). Each row records which grain
scored it (`benchmark_level`), and the app shows it ("scored vs city"). Only rows that fall back to a
thin city grain are flagged `low_confidence` and **surfaced with a warning rather than dropped**.

---

## dbt models (lineage)

```
1_bronze   stg_idealista__listings · stg_fotocasa__listings        (sources + light typing)
2_silver   int_listings_unioned → int_listings_current             (latest snapshot per listing)
                                 → int_listings_history             (all snapshots, for trends)
           int_neighborhood_stats · dim_neighborhoods              (benchmarks + dimension)
3_gold     fct_listings_scored                                     (the scoring fact table)
           rpt_opportunities                                       (consumption view for the app)
```

Every model carries a **grain declaration**, column descriptions, and tests
(`unique`, `not_null`, `accepted_values`, `dbt_utils.accepted_range`) so the warehouse fails
loudly when an assumption breaks. See [`transform/models/`](transform/models/).

---

## The Streamlit app

| Page | What it answers |
|---|---|
| **Opportunities** | Where are the under-priced listings right now? Ranked by score, with deal-tier breakdown and map. |
| **Market** | What's the €/m² benchmark by neighbourhood, and how is it evolving? |
| **Mortgage** | Fixed vs variable French-amortisation simulator. |
| **Affordability** | What income does each neighbourhood require? Buy-vs-rent comparison. |
| **How it works** | Where the numbers come from, how the score is computed, and what this data cannot tell you. |

Every page carries a **freshness header** — last ingest, row counts, share of scores computed at
barrio grain, dbt test results — so a visitor sees the data's condition before reading any figure.
Colour comes only from native theme keys and a registered Altair theme; there is no CSS injection
anywhere, so a Streamlit upgrade can't silently break the look.

---

## Key engineering decisions & trade-offs

- **MotherDuck/DuckDB as the warehouse.** A pragmatic call for the project's scale, not a technical
  moat: at thousands-of-rows volume, a serverless DuckDB warehouse is free, zero-ops and fast, while
  Snowflake/BigQuery/Redshift would add cost and operational overhead for no analytical benefit here.
  Crucially the dbt project is **warehouse-agnostic** — it's the same `ref()`/`source()` SQL I'd run
  on Snowflake at work, portable with just a profile swap, so the modelling skills transfer 1:1.
- **Idempotent upserts (`INSERT OR REPLACE`, PK `(source_name, source_id)`).** Re-running an
  extraction never duplicates rows, so the pipeline is safe to retry — a prerequisite for scheduled
  orchestration.
- **Search-card scraping over detail-page scraping.** 25 Scrapfly credits buy ~30 listings from a search page, against one listing from a detail page — ~30× cheaper per listing. (An earlier version of this claimed ~1 credit per search page; that was never measured and is wrong — Idealista requires Scrapfly's anti-bot protection, billed flat at 25.) Detail pages cost 25–29 with
  JS rendering. The trade-off: no per-listing coordinates (see limitations). For a benchmark engine,
  breadth of comparables matters more than per-listing depth.
- **Low-confidence data is shown, not hidden.** Dropping sparse neighbourhoods would make the app
  look complete while quietly lying about coverage. Flagging is the honest default.
- **A benchmark with no dispersion scores neutral, not extreme.** When a cell holds a single
  comparable the standard deviation is 0, and letting the clamp absorb that would snap the z-score
  to −3 → **score 100 → "great deal"** — the pipeline's most confident verdict from its least
  evidence. The z-score is coalesced to 0 (score 50) instead.
- **Snapshot history as a first-class table.** `int_listings_history` keeps every observation so
  price-evolution is real (accumulated daily) rather than reconstructed.
- **Per-table source freshness, not one global threshold.** The INE feed is production-critical and
  fails CI after 10 days of staleness; the paused listings table warns without failing, because its
  staleness is a recorded decision rather than a fault. One global threshold would have forced a
  choice between a permanently red build and no freshness gate at all.

### Key decisions (ADRs)

Each of these is written up as an **[Architecture Decision Record](docs/adr/)** — the context, the
call, the consequences I now have to live with (including the ones that constrain the app's UI),
and the alternatives I rejected and why.

| ADR | Decision | The cost I accepted |
|---|---|---|
| [0001](docs/adr/0001-search-card-scraping.md) | Scrape **search cards**, not detail pages | ~30 listings per 25-credit request instead of one — but **no per-listing coordinates**, so the map plots barrio centroids |
| [0002](docs/adr/0002-warehouse-motherduck-medallion.md) | MotherDuck (DuckDB) warehouse with a dbt medallion | Free and zero-ops at this scale; free-tier limits are a real ceiling |
| [0003](docs/adr/0003-idempotent-upserts.md) | Idempotent upserts keyed on `(source_name, source_id)` | Retry-safe, but a re-scrape overwrites the prior observation — history has to live in silver |
| [0004](docs/adr/0004-hierarchical-benchmark-grain.md) | Hierarchical benchmark grain: neighbourhood → district → city, `min_comps_for_benchmark = 8` | Grain is **per row**, so `benchmark_level` is a visible gold column the app must always show — a score without its grain isn't interpretable |
| [0005](docs/adr/0005-show-low-confidence-rows.md) | Show low-confidence rows, flagged, rather than dropping them | Some visible scores are genuinely weak; disclosure becomes a presentation responsibility |
| [0006](docs/adr/0006-zero-dispersion-neutral-zscore.md) | Zero dispersion → **neutral z-score (0)**, not a ±3 snap | A one-comparable benchmark would otherwise fabricate a `great_deal`; the cost is that a score of 50 is ambiguous without its comparable count |
| [0007](docs/adr/0007-repair-location-in-silver-not-extraction.md) | Repair scraped locations **in silver**, with the seed outranking the pattern | Makes every parser fix retroactive and stops streets becoming benchmarks; the cost is that the seed is now load-bearing while covering only five cities |
| [0008](docs/adr/0008-district-income-as-the-missing-denominator.md) | Ground prices in **district income** from INE's ADRH, via bulk CSV | Answers *is this area cheap?* rather than only *is this cheap for the area?*; the cost is a ~2-year lag and València-only district coverage |

---

## Run it locally

Dependencies are managed with [**uv**](https://docs.astral.sh/uv/) (`pyproject.toml` +
`uv.lock`). Install it once with `curl -LsSf https://astral.sh/uv/install.sh | sh`, then:

```bash
make install        # uv sync (creates .venv from the lockfile) + config templates
# edit .env  → MOTHERDUCK_TOKEN, SCRAPFLY_API_KEY
make dbt-deps        # install dbt packages (once)

make extract CITY=valencia OP=sale     # 25 Scrapfly credits per page of ~30 listings
make ingest-ine                         # free: official INE house-price index → raw.ine_hpi
make transform                          # dbt run: bronze → silver → gold
make dbt-test                           # data-quality tests
make app                                # Streamlit on :8501

make pipeline-prefect                   # same extract → dbt build, run as a Prefect flow
```

**Or with Docker** (no local Python needed):

```bash
make docker-build                       # build the pipeline image
make docker-run                         # extract → dbt build inside the container
```

Full command list: `make help`.

---

## Roadmap

- [x] **Prefect** flow orchestrating `extract → dbt build`, with task-level retries
- [x] **GitHub Actions** CI: lint + `pytest` + `dbt build` on every PR; daily scheduled pipeline run
- [x] `pytest` unit tests for the `_parse_location()` heuristic, orchestration flow, and mortgage math
- [x] **Hierarchical opportunity score** (neighbourhood → district → city fallback) so the score is
      meaningful even where a barrio is sparse
- [x] **Offline geocoding** of Valencia barrios (seed of canonical names + centroids) → the map works
- [x] `int_listings_unioned` as the multi-source spine with cross-source dedup wired in
- [x] **Dockerised** pipeline (`make docker-build && make docker-run`) — image build verified in CI
- [x] **`dbt docs` on GitHub Pages** — lineage graph, column docs and tests, auto-published on merge
- [x] **dbt contract** enforced on `rpt_opportunities` (the app's de-facto API) + **exposure** for the Streamlit dashboard
- [x] Barrio centroids for **Valencia, Madrid, Barcelona, Sevilla, Málaga** (~170 canonical barrios + aliases)
- [x] **Behavioural deal signals** — `int_listing_lifecycle` derives days-on-market,
      price-cut count and cumulative price change from the snapshot history, surfaced as a
      "motivated seller" filter/badge (a stronger negotiability signal than €/m² alone)
- [x] **Official market context** — free INE house-price-index (IPV) feed (`raw.ine_hpi` →
      `int_market_context` → `rpt_market_context`), grounding scraped asking prices against
      transaction-based reality and keeping the app fresh with zero scraping credits
- [x] **Data-trust surface** — freshness header on every page, per-listing score provenance
      (benchmark grain + comparable count shown wherever a score is), a "How it works & data
      quality" page, and `dbt source freshness` gating CI per source table
- [ ] Ingest **Fotocasa** (`raw.fotocasa_listings`) — staging + union are ready, only the source feed is missing
- [ ] Barrio centroids for Zaragoza / Valladolid / Bilbao

## Known limitations

1. **Data volume is still growing.** Most listings currently benchmark against the **city** grain
   (`benchmark_level`); barrios flip to local benchmarks as they accumulate ≥ 8 comparables. The fix
   is sustained scraping + daily runs, not lowering the threshold.
2. **Geocoding is barrio-centroid level** (Valencia, Madrid, Barcelona, Sevilla, Málaga) — listings
   plot at their neighbourhood's centroid, not their exact address (search-card scraping doesn't
   expose per-listing coordinates). Zaragoza/Valladolid/Bilbao have no centroids yet.
3. **Fotocasa** scraper and staging exist but `raw.fotocasa_listings` isn't fed yet.
4. **Price-evolution charts and behavioural signals** (`int_listing_lifecycle`: days-on-market,
   price cuts) need several accumulated snapshots to be meaningful. The models are correct from
   day one — a listing seen once reads as "no signal yet" (0), not a fabricated one — and light
   up as the weekly pipeline runs.
5. **INE context is autonomous-community grain**, not per-listing. The IPV is an official
   *regional* transaction-price index (quarterly), so it grounds *market direction* honestly;
   it is deliberately not presented as a per-flat "fair price" (that would be an AVM — future work).

---

<sub>Built by <a href="https://www.linkedin.com/in/carlos-de-manuel">Carlos De Manuel</a> ·
Analytics / Data Engineering portfolio · MIT License</sub>
