"""
How it works & data quality — the pipeline, the score, and what it can't tell you.

This page exists because a number without its provenance is a guess with better
typography. It is also the page that keeps the rest of the app honest: the score's
arithmetic, the fallback rule that decides which comparables it used, and the
limitations, all in one place a visitor can check against what they just saw.
"""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from components.charts import bar_benchmark_grain
from freshness import get_benchmark_grain_counts
import streamlit as st
from theme import altair_chart, page_hero, section

MIN_COMPS = 8  # transform/dbt_project.yml → vars.min_comps_for_benchmark
DBT_DOCS_URL = "https://carlosdmv7.github.io/spanish-housing-radar/"
REPO_URL = "https://github.com/carlosdmv7/spanish-housing-radar"

page_hero(
    "How it works & data quality",
    "Where the numbers come from, how the opportunity score is computed, and the "
    "questions this data honestly cannot answer.",
)

# ── Lineage ───────────────────────────────────────────────────────────────────
section("From portal to page")
st.markdown(
    ":small[Two sources, one warehouse, three modelling layers. Scraped listings give "
    "**asking** prices; the INE house-price index grounds them against **transactions**.]"
)
st.code(
    "Idealista search cards ┐\n"
    "                       ├─→  raw  →  bronze  →  silver  →  gold  →  this app\n"
    "INE house-price index  ┘",
    language="text",
)
st.markdown("""
| Layer | Models | What happens |
|---|---|---|
| **raw** | `idealista_listings`, `ine_hpi` | Append-only landing tables. Loads are idempotent upserts on `(source_name, source_id)`, so a retried run never duplicates rows. |
| **bronze** | `stg_*` | Typing, renaming, light cleaning. No business logic, one staging model per source table. |
| **silver** | `int_listings_current`, `int_listings_history`, `int_neighborhood_stats`, `int_listing_lifecycle`, `dim_neighborhoods` | Latest snapshot per listing, the full snapshot history behind price trends, and the €/m² benchmarks the score divides by. |
| **gold** | `fct_listings_scored`, `rpt_opportunities`, `rpt_market_context` | The scoring fact table and the consumption views this app reads. |
""")
st.markdown(
    f":small[Every model carries a grain declaration, column docs and tests. The full "
    f"lineage graph is published from CI: [dbt docs]({DBT_DOCS_URL}) · "
    f"[source]({REPO_URL}/tree/main/transform/models).]"
)

# ── The score ─────────────────────────────────────────────────────────────────
st.markdown("")
section("The opportunity score")
st.markdown(
    "A listing's price per m² is compared against the **median and standard "
    "deviation** of comparable listings — same operation, same property type:"
)
st.code(
    "z         = (price_per_sqm − benchmark_median_ppsqm) / benchmark_stddev_ppsqm\n"
    "z_clamped = clamp(z, −3, +3)\n"
    "score     = clamp(50 − z_clamped × (50/3), 0, 100)",
    language="text",
)
st.markdown(
    "So **50 is exactly the benchmark median**, 100 is three standard deviations "
    "below it, 0 is three above. The score is a *relative* statement about a market, "
    "never an appraisal of a building."
)

col_a, col_b = st.columns(2)
with col_a:
    st.markdown("""
| Score | Tier |
|---|---|
| ≥ 75 | Great deal |
| ≥ 55 | Good deal |
| ≥ 45 | Fair price |
| ≥ 25 | Overpriced |
| < 25 | Very overpriced |
""")
with col_b:
    st.markdown("""
**Why a z-score and not a simple % below median?**
Dividing by the spread makes the score comparable across
neighbourhoods. Being 10% under median means much more in a
tight market than in a heterogeneous one, and a raw
percentage would rank those two identically.

**Edge case:** when a benchmark has zero variance the
z-score is undefined, so it's coalesced to 0 — a score of
exactly 50, which reads as "no signal", not as a deal.
""")

# ── Fallback rule ─────────────────────────────────────────────────────────────
st.markdown("")
section("Which comparables a listing actually got")
st.markdown(
    f"Spanish listings are sparse at barrio level. Comparing a flat against three "
    f"neighbours would mostly compare it against itself — a z-score near zero and a "
    f"meaningless \"fair\" 50. So the score takes the **finest grain with at least "
    f"{MIN_COMPS} comparables**:"
)
st.markdown(f"""
1. **Barrio** — if the listing's neighbourhood has ≥ {MIN_COMPS} comparables, score
   against it. `benchmark_level = 'neighbourhood'`.
2. **District** — otherwise, if the district has ≥ {MIN_COMPS}, score against that.
   `benchmark_level = 'district'`.
3. **City** — otherwise the city, always. If even the city has < {MIN_COMPS}
   comparables the row is stamped `low_confidence_flag`.
""")
st.markdown(
    "Each row records which grain scored it, and **every surface that shows a score "
    "also shows that grain** — the cards, the table and the map tooltips. Falling back "
    "isn't hidden, because a coarser comparison is a weaker claim."
)

grain = get_benchmark_grain_counts()
if grain.empty:
    st.warning(
        "**Grain distribution unavailable** — the warehouse didn't answer. Everything "
        "above still describes the model; only the live counts are missing."
    )
else:
    st.markdown("")
    section("Live grain distribution")
    altair_chart(bar_benchmark_grain(grain))
    barrio_share = float(
        grain.loc[grain["benchmark_level"] == "neighbourhood", "share"].sum()
    )
    st.markdown(
        f":small[**{barrio_share:.1%}** of scored listings currently reach barrio "
        "grain. This number rises with scraping volume — the fix is more data, not a "
        f"lower threshold than {MIN_COMPS}.]"
    )

# ── Honesty about the data ────────────────────────────────────────────────────
st.markdown("")
section("What this data cannot tell you")
with st.container(border=True):
    st.markdown("""
**Asking prices, not sale prices.** Everything scraped is what a seller *wants*.
The INE index on the Market page is the transaction-based counterweight, but it's
regional and quarterly — deliberately not presented as a per-flat valuation.

**No per-listing coordinates.** Search cards are scraped at ~1 proxy credit per 30
listings instead of 25–29 per detail page, which buys breadth of comparables at the
cost of exact addresses. Map dots sit at their barrio's centroid, so several
listings share a point.

**Barrio centroids exist for five cities only** — Valencia, Madrid, Barcelona,
Sevilla, Málaga. Listings elsewhere are scored but not mapped.

**Price history is accumulated, never backfilled.** Days-on-market and price-cut
counts come from comparing daily snapshots, so a listing seen once reads as "no
signal yet" rather than a fabricated zero. Scraping is currently paused, which
stops that clock.

**The score says nothing about the flat itself** — no condition, floor, light,
noise, or renovation state. It says a price is unusual for its market, which is
where a search should *start*, not end.
""")

st.markdown("")
section("How it's kept honest")
st.markdown(f"""
- **dbt tests** on sources and models — `unique`, `not_null`, `accepted_values`,
  `accepted_range` — so a broken assumption fails the build instead of reaching this page.
- **Source freshness thresholds** per table: the INE feed errors CI after 10 days of
  staleness; the paused listings table warns without failing, because its staleness is
  a known decision rather than a fault.
- **A contract on `rpt_opportunities`** — the model this app reads is a declared
  interface, so a column change breaks CI, not the dashboard.
- **CI builds into isolated `ci_*` schemas**, never `main_*`, so a bad pull request
  can't overwrite what the live app is reading.
- **Decisions are written down** as [ADRs]({REPO_URL}/tree/main/docs/adr), including
  the one that requires this page to exist.

The freshness strip at the top of every page carries the current values: last ingest,
row counts, share of barrio-grain scores, and dbt test results.
""")
