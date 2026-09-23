"""
Overview — the answer first, then where to go.

Laid out like the sibling job-market-intelligence app: a title, one line, four
numbers, and a chart on the first screen. The previous landing page opened with
a strip of warehouse metadata, a box of prose and a coverage table, and a
visitor had to scroll before seeing a single price.

Scoped to one city on purpose — the one the scheduled pipeline actually
scrapes. The other cities in the warehouse hold a single older snapshot; mixing
them into the headline numbers made the first screen look like a pile of
unrelated figures, which is the fastest way to make good data look like junk.
They are named in a caption, not hidden.
"""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from chrome import page_header
from components.charts import bar_barrio_ppsqm
from connection import query
import pandas as pd
import streamlit as st
from theme import altair_chart

# transform/dbt_project.yml → vars.min_comps_for_benchmark. A barrio with fewer
# listings than this has a median that describes a handful of flats, so it is
# left off the chart rather than drawn as if it were as solid as the rest.
MIN_LISTINGS = 8
RPT = "spanish_housing_radar.main_gold.rpt_opportunities"

# Absolute, not "views/…". st.page_link resolves a relative path against the
# *main script's* directory, so a relative link only works when app/main.py is
# the entry point — the render tests run each page inside a navigation harness
# whose main script lives elsewhere, and the relative form 404'd there.
VIEWS = Path(__file__).parent


@st.cache_data(ttl=600)
def load_city() -> tuple[str, pd.DataFrame]:
    """The live city, and the other cities with how old their snapshot is."""
    cities = query(f"""
        SELECT municipality, COUNT(*) AS listings,
               MAX(_loaded_at::date) AS last_seen
        FROM {RPT}
        GROUP BY 1 ORDER BY listings DESC
    """)
    return str(cities.iloc[0]["municipality"]), cities.iloc[1:]


@st.cache_data(ttl=600)
def load_overview(city: str) -> tuple[pd.Series, pd.DataFrame, pd.DataFrame]:
    kpis = query(f"""
        SELECT
            COUNT(*)                                             AS scored,
            COUNT(*) FILTER (WHERE deal_tier = 'great_deal')     AS great_deals,
            MEDIAN(price_per_sqm) FILTER (WHERE property_type = 'apartment')
                                                                 AS median_ppsqm,
            COUNT(*) FILTER (WHERE benchmark_level = 'neighbourhood')
                                                                 AS at_barrio
        FROM {RPT}
        WHERE municipality = $city AND operation_type = 'sale'
    """, city=city).iloc[0]

    barrios = query(f"""
        SELECT neighborhood, COUNT(*) AS listings, MEDIAN(price_per_sqm) AS median_ppsqm
        FROM {RPT}
        WHERE municipality = $city AND operation_type = 'sale'
          AND property_type = 'apartment' AND neighborhood IS NOT NULL
        GROUP BY 1
        HAVING COUNT(*) >= $min_n
    """, city=city, min_n=MIN_LISTINGS)

    # Barrio-grain scores only. A "great deal" measured against the whole city is
    # the weakest claim the app makes, and the landing page is the wrong place to
    # lead with a weak claim. The Deals page shows every grain, labelled.
    deals = query(f"""
        SELECT neighborhood, price_eur, size_sqm, price_per_sqm,
               neighborhood_median_ppsqm, opportunity_score, url
        FROM {RPT}
        WHERE municipality = $city AND operation_type = 'sale'
          AND benchmark_level = 'neighbourhood'
        ORDER BY opportunity_score DESC
        LIMIT 6
    """, city=city)
    return kpis, barrios, deals


page_header(
    "Spanish Housing Radar",
    "Portals tell you what a flat costs. This tells you whether that's cheap for "
    "where it is — every listing scored against the flats around it.",
    explain_facts=True,
)

try:
    city, others = load_city()
    kpis, barrios, deals = load_overview(city)
except Exception as exc:
    st.error(
        "**Can't reach the warehouse.** Locally that needs `MOTHERDUCK_TOKEN` in "
        "`.env`; on Streamlit Cloud it comes from the app's Secrets."
    )
    st.caption(f"Underlying error: {exc}")
    st.stop()

place = city.title()
scored = int(kpis["scored"])

m1, m2, m3, m4 = st.columns(4)
m1.metric(f"Flats for sale in {place}", f"{scored:,}",
          help="Every one scored against comparable flats nearby.")
m2.metric("Great deals right now", f"{int(kpis['great_deals']):,}",
          help="Score of 75 or more: well below what comparable flats ask.")
m3.metric("Barrios with a solid benchmark", f"{len(barrios):,}",
          help=f"Barrios with at least {MIN_LISTINGS} flats for sale — enough for "
               "their median to describe the barrio rather than a handful of flats.")
m4.metric("Typical asking price", f"€{kpis['median_ppsqm']:,.0f}/m²",
          help=f"Median across apartments for sale in {place}.")

st.divider()

chart_col, deals_col = st.columns([3, 2], gap="large")

with chart_col:
    st.markdown("#### What a m² costs, barrio by barrio")
    if barrios.empty:
        st.info(f"No barrio in {place} has {MIN_LISTINGS}+ listings yet.")
    else:
        altair_chart(bar_barrio_ppsqm(barrios, float(kpis["median_ppsqm"])))
        st.caption(
            f"Bars run from the {place} median (dashed): teal asks less, rust asks "
            f"more. Only barrios with {MIN_LISTINGS}+ flats for sale are drawn."
        )

with deals_col:
    st.markdown("#### Best deals right now")
    if deals.empty:
        st.info("No listing is scored against its own barrio yet.")
    else:
        d = deals.assign(
            area=deals["neighborhood"].str.title(),
            below=(deals["price_per_sqm"] / deals["neighborhood_median_ppsqm"] - 1),
        )
        st.dataframe(
            d[["area", "price_eur", "size_sqm", "below", "opportunity_score", "url"]],
            width="stretch",
            hide_index=True,
            column_config={
                "area": st.column_config.TextColumn("Barrio"),
                "price_eur": st.column_config.NumberColumn("Price", format="€%,d"),
                "size_sqm": st.column_config.NumberColumn("m²", format="%d"),
                "below": st.column_config.NumberColumn(
                    "vs barrio", format="percent",
                    help="Price per m² against the median of its own barrio."),
                "opportunity_score": st.column_config.ProgressColumn(
                    "Score", min_value=0, max_value=100, format="%d"),
                "url": st.column_config.LinkColumn("", display_text="open ↗"),
            },
        )
        st.caption("Scored against their own barrio — the strongest comparison the "
                   "app makes.")
    st.page_link(str(VIEWS / "01_opportunities.py"), label="See every deal",
                 icon=":material/arrow_forward:")

st.divider()

n1, n2 = st.columns(2, gap="large")
with n1:
    st.markdown("#### :material/balance: Is the area itself overpriced?")
    st.markdown(
        "A cheap flat in an expensive barrio is still expensive. Compare what a "
        "barrio asks with what it rents for and what its residents earn."
    )
    st.page_link(str(VIEWS / "04_affordability.py"), label="Open Value check",
                 icon=":material/arrow_forward:")
with n2:
    st.markdown("#### :material/calculate: What would it cost me?")
    st.markdown(
        "The monthly payment, the cash due on signing day, and whether renting and "
        "investing the difference would leave you better off."
    )
    st.page_link(str(VIEWS / "03_mortgage.py"), label="Open Budget",
                 icon=":material/arrow_forward:")

if not others.empty:
    oldest = pd.to_datetime(others["last_seen"]).min().date()
    names = ", ".join(others["municipality"].str.title())
    st.caption(
        f"{place} is scraped on a schedule. The warehouse also holds a single older "
        f"snapshot of {names} (from {oldest:%B %Y}), browsable on the Deals page — "
        "too thin for barrio-level benchmarks, so they stay out of the headline."
    )
