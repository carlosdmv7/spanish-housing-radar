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

from chrome import page_header
from components.charts import bar_benchmark_grain
from freshness import get_benchmark_grain_counts, get_snapshot_coverage
import streamlit as st
from theme import altair_chart, section

MIN_COMPS = 8  # transform/dbt_project.yml → vars.min_comps_for_benchmark
DBT_DOCS_URL = "https://carlosdmv7.github.io/spanish-housing-radar/"
REPO_URL = "https://github.com/carlosdmv7/spanish-housing-radar"

page_header(
    "How it works",
    "Where the numbers come from, how a flat gets its score, and what this data "
    "cannot tell you.",
)

# ── Lineage ───────────────────────────────────────────────────────────────────
section("From portal to page")
st.markdown(
    ":small[Three feeds, one warehouse, three modelling layers. Scraped listings give "
    "**asking** prices; the INE house-price index grounds them against **transactions**; "
    "INE household income is the denominator that turns *cheap for the area* into "
    "*cheap for the people who live there*.]"
)
st.code(
    "Idealista search cards ┐\n"
    "INE house-price index  ├─→  raw  →  bronze  →  silver  →  gold  →  this app\n"
    "INE district income    ┘",
    language="text",
)
st.markdown("""
| Layer | Models | What happens |
|---|---|---|
| **raw** | `idealista_listings`, `ine_hpi`, `ine_income` | Append-only landing tables. Loads are idempotent upserts on `(source_name, source_id)`, so a retried run never duplicates rows. |
| **bronze** | `stg_*` | Typing, renaming, light cleaning. No business logic, one staging model per source table. |
| **silver** | `int_listings_current`, `int_listings_history`, `int_neighborhood_stats`, `int_listing_lifecycle`, `int_market_context`, `int_district_income`, `dim_neighborhoods` | Latest snapshot per listing, the full snapshot history behind price trends, the €/m² benchmarks the score divides by, and the two INE feeds resolved to the grains this app can join to. |
| **gold** | `fct_listings_scored`, `rpt_opportunities`, `rpt_market_context`, `rpt_district_affordability` | The scoring fact table and the consumption views this app reads. |
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

# Derived, not written down. The sentence this replaces said "Valencia now has
# four snapshots since May, so its price evolution and seller-motivation signals
# are real" — while the warehouse held 1,260 of 1,283 listings observed exactly
# once. A claim about live data that is typed by hand is true until the data
# moves, and this page is the last one that should be making one.
coverage = get_snapshot_coverage()
if coverage is None:
    history_note = (
        "Days-on-market and price-cut counts come from comparing snapshots, so a "
        "listing seen once reads as \"no signal yet\" rather than a fabricated zero. "
        "How much repeat history exists right now could not be read from the "
        "warehouse."
    )
else:
    history_note = (
        f"Days-on-market and price-cut counts come from comparing snapshots, so a "
        f"listing seen once reads as \"no signal yet\" rather than a fabricated zero. "
        f"Right now that is most of them: **{coverage['observed_again']:,} of "
        f"{coverage['listings']:,}** listings "
        f"({coverage['repeat_share']:.1%}) have been seen more than once, and the "
        f"deepest history on any single listing is {coverage['max_snapshots']} "
        f"observations. The behavioural signals are therefore real for that slice "
        f"and silent for the rest — they fill in as the scheduled scrape revisits "
        f"the same city, which is a question of credits, not of modelling."
    )

with st.container(border=True):
    st.markdown("""
**Asking prices, not sale prices.** Everything scraped is what a seller *wants*.
The INE index on the Market page is the transaction-based counterweight, but it's
regional and quarterly — deliberately not presented as a per-flat valuation.

**No per-listing coordinates.** A search page costs a flat 25 proxy credits and
returns ~30 listings; a detail page costs 25–29 and returns one. Scraping cards is
therefore ~30× cheaper per listing, and it buys breadth of comparables at the cost
of exact addresses. Map dots sit at their barrio's centroid, so several listings
share a point.

**Barrio centroids exist for five cities only** — Valencia, Madrid, Barcelona,
Sevilla, Málaga. Listings elsewhere are scored but not mapped.

**The score says nothing about the flat itself** — no condition, floor, light,
noise, or renovation state. It says a price is unusual for its market, which is
where a search should *start*, not end.
""")
    st.markdown(f"**Price history is accumulated, never backfilled.** {history_note}")

st.markdown("")
section("How it's kept honest")
st.markdown(f"""
- **dbt tests** on sources and models — `unique`, `not_null`, `accepted_values`,
  `accepted_range` — so a broken assumption fails the build instead of reaching this page.
- **Two separate staleness checks, because they catch different things.** Source
  freshness watches *load* time: the INE feed errors CI after 10 days, which catches
  a cron that has died, while the listings table only warns, because a metered scrape
  ageing is a decision rather than a fault. Load time says nothing about the data
  inside, though — the INE loader replaces every row each week, so that gate passes
  however old the index is. `assert_ine_hpi_period_is_current` watches the newest
  *quarter* instead and warns when it falls further behind than a publication gap
  explains. It is warning today, and the Market page shows the reference quarter and
  its age rather than leaving you to infer currency from a green check.
- **A contract on `rpt_opportunities`** — the model this app reads is a declared
  interface, so a column change breaks CI, not the dashboard.
- **CI builds into isolated `ci_*` schemas**, never `main_*`, so a bad pull request
  can't overwrite what the live app is reading.
- **Decisions are written down** as [ADRs]({REPO_URL}/tree/main/docs/adr), including
  the one that requires this page to exist.

The freshness strip at the top of every page carries the current values: last ingest,
row counts, share of barrio-grain scores, and dbt test results.
""")
