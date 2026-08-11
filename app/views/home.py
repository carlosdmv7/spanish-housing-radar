"""
Home — what the tool is, what's actually in the warehouse, and where to go next.

The page answers one question: *what can this actually tell me?* The honest
answer depends on depth, not on totals — a listing scored against its own barrio
is worth far more than one scored against a whole city — so the lede leads with
the share at barrio grain rather than with the row count, which is the flattering
number and the less informative one.
"""
from datetime import date
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from connection import query
import pandas as pd
import streamlit as st
from theme import lede, page_hero, section

page_hero(
    "Spanish Housing Radar",
    "Spanish portals tell you a flat's price, never whether it's a good one. This "
    "scores every listing against comparable flats in its own barrio, so a cheap flat "
    "in an expensive area rises to the top.",
)


# ── What this can currently answer ────────────────────────────────────────────
# Deliberately separate from the snapshot below and deliberately about grain. A
# score computed against a whole city barely answers the question the app asks,
# so quoting the total row count as the headline would overstate what is here.
@st.cache_data(ttl=600)
def load_grain():
    return query("""
        SELECT
            municipality,
            COUNT(*)                                                AS scored,
            COUNT(*) FILTER (WHERE benchmark_level = 'neighbourhood') AS at_barrio
        FROM spanish_housing_radar.main_gold.rpt_opportunities
        GROUP BY 1
    """)


try:
    grain = load_grain()
    total_scored = int(grain["scored"].sum())
    total_barrio = int(grain["at_barrio"].sum())
    deepest = grain.sort_values("at_barrio", ascending=False).iloc[0]
    lede(
        f"**{total_barrio:,}** of {total_scored:,} listings are priced against their "
        f"own barrio — deepest in **{str(deepest['municipality']).title()}**, with "
        f"{int(deepest['at_barrio']):,}.",
        "The rest fall back to their district or the whole city, which is a weaker "
        "comparison and is labelled as such on every listing. Depth is the "
        "constraint here, not coverage: one city scraped properly answers the "
        "question that ten cities scraped thinly cannot.",
    )
except Exception:
    # The snapshot below reports the connection failure in full; repeating it here
    # would put the same error on screen twice.
    pass

# ── Live data snapshot ────────────────────────────────────────────────────────
try:
    row = query("""
        SELECT
            COUNT(DISTINCT listing_pk)    AS total_listings,
            COUNT(DISTINCT municipality)  AS cities,
            COUNT(DISTINCT neighborhood)  AS neighborhoods,
            MAX(_loaded_at::date)         AS last_run
        FROM spanish_housing_radar.main_silver.int_listings_current
    """).iloc[0]

    section("What's in the warehouse")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Active listings", f"{int(row['total_listings']):,}")
    c2.metric("Cities", int(row["cities"]))
    c3.metric("Neighbourhoods", int(row["neighborhoods"]))
    # An ISO date set at metric size is both the widest value in the row — it was
    # being truncated to "2026-06-26…" — and the least useful, since the number a
    # visitor actually wants from a freshness figure is how *old* it is. The age
    # answers that in three characters; the date itself stays one hover away.
    # `::date` in the SQL does not survive the round trip: DuckDB hands pandas a
    # datetime64 column, so this arrives as a Timestamp and subtracting a
    # date.today() from it raises. Normalise on the Python side rather than trust
    # the cast.
    last_run = pd.to_datetime(row["last_run"]).date() if pd.notna(row["last_run"]) else None
    age_days = (date.today() - last_run).days if last_run is not None else None
    c4.metric(
        "Last ingest",
        "—" if age_days is None else f"{age_days}d ago",
        help=None if last_run is None else f"Most recent load: {last_run}.",
    )

    cov = query("""
        SELECT
            municipality                                        AS city,
            COUNT(*) FILTER (WHERE operation_type = 'sale')     AS for_sale,
            COUNT(*) FILTER (WHERE operation_type = 'rent')     AS for_rent
        FROM spanish_housing_radar.main_silver.int_listings_current
        GROUP BY 1
        ORDER BY (for_sale + for_rent) DESC
    """)

    section("Coverage by city")
    st.markdown(
        ":small[Depth per city is what decides whether a score is computed against a "
        "barrio or falls back to the whole city.]"
    )
    st.dataframe(
        cov.assign(city=cov["city"].str.title()),
        width="stretch",
        hide_index=True,
        column_config={
            "city": st.column_config.TextColumn("City", pinned=True),
            "for_sale": st.column_config.NumberColumn("For sale", format="%,d"),
            "for_rent": st.column_config.NumberColumn("For rent", format="%,d"),
        },
    )
except Exception as exc:
    st.error(
        "**Can't reach the warehouse, so the live snapshot is empty.** The app reads "
        "from MotherDuck — locally that needs `MOTHERDUCK_TOKEN` in `.env`; on "
        "Streamlit Cloud it comes from the app's Secrets. The pages below will show "
        "the same error until the connection works."
    )
    st.caption(f"Underlying error: {exc}")

st.markdown("")
section("Where to go")
st.markdown("""
| Page | What you'll find |
|---|---|
| :material/search: **Opportunities** | Listings ranked by opportunity score, each showing the benchmark it was scored against. |
| :material/bar_chart: **Market** | €/m² benchmarks per neighbourhood, price spread, official INE market context. |
| :material/calculate: **Mortgage** | Fixed vs variable simulator with a full French amortisation schedule. |
| :material/savings: **Affordability** | The income each neighbourhood demands, plus buy-vs-rent. |
| :material/science: **How it works** | The pipeline, the score's arithmetic, and what this data can't tell you. |
""")
st.markdown(
    ":small[Coverage is deepest in **Valencia**, which is why it's the default city "
    "on every page.]"
)
