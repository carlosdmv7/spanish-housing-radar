"""
Overview — the answer first, then where to go.

Laid out like the sibling job-market-intelligence app: a title, one line, four
numbers, and a picture on the first screen. The previous landing page opened
with a strip of warehouse metadata, a box of prose and a coverage table, and a
visitor had to scroll before seeing a single price.

The picture is the city itself. A ranked bar chart answered "which barrio is
dearest" well and "where" not at all, and where is the first thing anyone who
knows València asks. The ranking lives on Neighbourhoods.

Scoped to one city on purpose — the one the scheduled pipeline actually
scrapes. The other cities in the warehouse hold a single older snapshot; mixing
them into the headline numbers made the first screen look like a pile of
unrelated figures, which is the fastest way to make good data look like junk.
They are named in a caption, not hidden.
"""
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from chrome import page_header
from components.charts import map_barrio_ppsqm
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
# València's official barrio outlines, keyed by the seed's names — see
# scripts/fetch_barrio_shapes.py. Drawn only for the city they describe.
SHAPES = Path(__file__).parent.parent / "assets" / "valencia_barrios.geojson"
MAPPED_CITY = "valència"
DEAL_CARDS = 4


@st.cache_data
def load_shapes() -> dict:
    return json.loads(SHAPES.read_text(encoding="utf-8"))


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
    """, city=city)

    # Barrio-grain scores only. A "great deal" measured against the whole city is
    # the weakest claim the app makes, and the landing page is the wrong place to
    # lead with a weak claim. The Deals page shows every grain, labelled.
    deals = query(f"""
        SELECT neighborhood, price_eur, size_sqm, rooms, price_per_sqm,
               neighborhood_median_ppsqm, opportunity_score, deal_tier, url,
               -- The load of its latest snapshot: the last time the scraper saw
               -- it. Printed on each card, so "right now" can be checked.
               _loaded_at::date AS last_seen
        FROM {RPT}
        WHERE municipality = $city AND operation_type = 'sale'
          AND benchmark_level = 'neighbourhood'
        ORDER BY opportunity_score DESC
        LIMIT $n
    """, city=city, n=DEAL_CARDS)
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

solid = barrios[barrios["listings"] >= MIN_LISTINGS]

m1, m2, m3, m4 = st.columns(4)
m1.metric(f"Flats for sale in {place}", f"{scored:,}",
          help="Every one scored against comparable flats nearby.")
m2.metric("Great deals right now", f"{int(kpis['great_deals']):,}",
          help="Score of 75 or more: well below what comparable flats ask.")
m3.metric("Barrios with a solid benchmark", f"{len(solid):,}",
          help=f"Barrios with at least {MIN_LISTINGS} flats for sale — enough for "
               "their median to describe the barrio rather than a handful of flats.")
m4.metric("Typical asking price", f"€{kpis['median_ppsqm']:,.0f}/m²",
          help=f"Median across apartments for sale in {place}.")

map_col, deals_col = st.columns([3, 2], gap="large")

with map_col:
    st.markdown("#### Where a m² costs more")
    if city == MAPPED_CITY and not solid.empty:
        altair_chart(map_barrio_ppsqm(load_shapes(), barrios, float(kpis["median_ppsqm"]),
                                      MIN_LISTINGS))
        st.caption(
            f"Median asking €/m² for flats for sale, against the {place} median. "
            f"Pale barrios have fewer than {MIN_LISTINGS} for sale — too few to say. "
            "The villages beyond the huerta and the Albufera are left off."
        )
    else:
        st.info(f"No barrio in {place} has {MIN_LISTINGS}+ listings yet.")

with deals_col:
    st.markdown("#### Best deals right now")
    if deals.empty:
        st.info("No listing is scored against its own barrio yet.")
    for d in deals.itertuples():
        below = (d.price_per_sqm / d.neighborhood_median_ppsqm - 1) * 100
        beds = f"{int(d.rooms)} bed · " if pd.notna(d.rooms) else ""
        with st.container(border=True):
            name, badge = st.columns([3, 2], vertical_alignment="center")
            name.markdown(f"**{str(d.neighborhood).title()}**")
            with badge:
                # Teal: in this brand rust means *above* the benchmark.
                st.badge(f"{below:+.0f}% vs barrio", color="green")
            st.markdown(
                f"**€{d.price_eur:,.0f}** · {beds}{d.size_sqm:.0f} m²  \n"
                f":small[:gray[Score {d.opportunity_score:.0f} · seen "
                f"{pd.Timestamp(d.last_seen):%-d %b} ·] [open ↗]({d.url})]"
            )
    st.page_link(str(VIEWS / "01_opportunities.py"), label="See every deal",
                 icon=":material/arrow_forward:")

st.divider()

# Where to go next: three doors, one line each. The page names are the links.
n1, n2, n3 = st.columns(3, gap="large")
for col, view, icon, label, line in [
    (n1, "02_market.py", "map", "Neighbourhoods",
     "Every barrio ranked, with the official price trend beside it."),
    (n2, "04_affordability.py", "balance", "Value check",
     "Is the area itself overpriced for what it rents and what it earns?"),
    (n3, "03_mortgage.py", "calculate", "Budget",
     "The monthly payment, the cash on signing day, and buy against rent."),
]:
    with col, st.container(border=True):
        st.page_link(str(VIEWS / view), label=f"**{label}**", icon=f":material/{icon}:")
        st.caption(line)

if not others.empty:
    oldest = pd.to_datetime(others["last_seen"]).min().date()
    names = ", ".join(others["municipality"].str.title())
    st.caption(
        f"{place} is scraped on a schedule. The warehouse also holds a single older "
        f"snapshot of {names} (from {oldest:%B %Y}), browsable on the Deals page — "
        "too thin for barrio-level benchmarks, so they stay out of the headline."
    )
