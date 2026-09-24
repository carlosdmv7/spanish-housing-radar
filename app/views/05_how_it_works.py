"""
How it works — the pipeline, the score, the sources and the limits, drawn
rather than described.

The one page with the freshness strip and its explanations, because it is the
page a visitor comes to when they want to check a number. Everything the other
pages leave out to stay short is here, as diagrams and tables first and prose
only where a limitation has no shape to draw.
"""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from chrome import page_header
from components.charts import bar_benchmark_grain
from config import DEAL_TIER_COLORS, DEAL_TIER_LABELS, SOURCES_CONSULTED_ON
from connection import query
from freshness import get_benchmark_grain_counts, get_snapshot_coverage
import pandas as pd
import streamlit as st
from theme import BORDER, INK, INK_MUTED, SURFACE_2, TEAL_700, altair_chart

MIN_COMPS = 8  # transform/dbt_project.yml → vars.min_comps_for_benchmark
DBT_DOCS_URL = "https://carlosdmv7.github.io/spanish-housing-radar/"
REPO_URL = "https://github.com/carlosdmv7/spanish-housing-radar"

page_header(
    "How it works",
    "Where the numbers come from, how a flat gets its score, and what the data "
    "cannot tell you.",
    explain_facts=True,
)

# Shared Graphviz styling, in the brand's tokens. White text only on the 700
# fill, per the design system's contrast rules.
_NODE = (f'node [shape=box, style="rounded,filled", fontname="Public Sans", '
         f'fontsize=11, color="{BORDER}", fillcolor="{SURFACE_2}", '
         f'fontcolor="{INK}", margin="0.18,0.08"]')
_EDGE = f'edge [color="{INK_MUTED}", arrowsize=0.6, fontname="Public Sans", fontsize=10, fontcolor="{INK_MUTED}"]'
_KEY = f'style="rounded,filled", fillcolor="{TEAL_700}", fontcolor="white", color="{TEAL_700}"'

# ── The pipeline ──────────────────────────────────────────────────────────────
st.markdown("#### From portal to page")
st.graphviz_chart(f"""
digraph {{
  rankdir=LR; bgcolor="transparent"; nodesep=0.25; ranksep=0.45;
  {_NODE}; {_EDGE};
  idealista [label="Idealista\\nlistings · weekly"];
  hpi [label="INE price index\\nquarterly"];
  income [label="INE household income\\nyearly"];
  raw [label="raw\\nlanded as fetched"];
  bronze [label="bronze\\ntyped"];
  silver [label="silver\\nhistory · benchmarks"];
  gold [label="gold\\nscores · reports", {_KEY}];
  app [label="this app"];
  {{idealista hpi income}} -> raw -> bronze -> silver -> gold -> app;
}}
""", width="stretch")
st.caption(
    "A GitHub Actions cron runs the flow every Monday under Prefect: scrape, load "
    "to MotherDuck, `dbt build` with every test. Pull requests build into isolated "
    f"`ci_*` schemas. [dbt docs and lineage]({DBT_DOCS_URL}) · [source]({REPO_URL})"
)

st.divider()

# ── The score ─────────────────────────────────────────────────────────────────
st.markdown("#### How a flat gets its score")
tree, rules = st.columns([3, 2], gap="large")
with tree:
    st.graphviz_chart(f"""
digraph {{
  rankdir=TB; bgcolor="transparent"; nodesep=0.3; ranksep=0.3;
  {_NODE}; {_EDGE};
  flat [label="A listing's price per m²"];
  q1 [label="Its barrio has {MIN_COMPS}+\\ncomparable flats?"];
  q2 [label="Its district has {MIN_COMPS}+?"];
  b [label="Compare with the barrio", {_KEY}];
  d [label="Compare with the district"];
  c [label="Compare with the city"];
  s [label="Score 0–100\\n50 = the typical price"];
  flat -> q1; q1 -> b [label=" yes"]; q1 -> q2 [label=" no"];
  q2 -> d [label=" yes"]; q2 -> c [label=" no"];
  {{b d c}} -> s;
}}
""", width="stretch")
with rules:
    st.latex(r"z = \frac{\text{€/m}^2 - \text{median}}{\text{spread}}"
             r"\qquad \text{score} = 50 - \tfrac{50}{3}\,\text{clamp}(z,\,-3,\,3)")
    thresholds = {"great_deal": "75+", "good_deal": "55+", "fair": "45+",
                  "overpriced": "25+", "very_overpriced": "below 25"}
    st.markdown("  \n".join(
        f":color[●]{{foreground=\"{DEAL_TIER_COLORS[k]}\"}} **{DEAL_TIER_LABELS[k]}** "
        f"· {thresholds[k]}"
        for k in DEAL_TIER_LABELS
    ))
    st.caption("Same operation and property type only. Dividing by the spread makes "
               "10% under in a tight barrio count for more than 10% under in a mixed "
               "one. Every score is shown with the grain that produced it.")

grain = get_benchmark_grain_counts()
if not grain.empty:
    altair_chart(bar_benchmark_grain(grain))

st.divider()


# ── Data quality, live ────────────────────────────────────────────────────────
@st.cache_data(ttl=3600)
def load_reference_dates() -> tuple[pd.Timestamp | None, int | None]:
    try:
        quarter = query("SELECT MAX(latest_period) AS q FROM "
                        "spanish_housing_radar.main_gold.rpt_market_context").iloc[0]["q"]
        year = query("SELECT MAX(income_reference_year) AS y FROM "
                     "spanish_housing_radar.main_gold.rpt_district_affordability"
                     ).iloc[0]["y"]
        return (pd.Timestamp(quarter) if pd.notna(quarter) else None,
                int(year) if pd.notna(year) else None)
    except Exception:
        return None, None


st.markdown("#### The data, in numbers")
coverage = get_snapshot_coverage()
quarter, income_year = load_reference_dates()
barrio_share = (float(grain.loc[grain["benchmark_level"] == "neighbourhood", "share"].sum())
                if not grain.empty else None)

q1, q2, q3, q4 = st.columns(4)
q1.metric("Scored against their own barrio",
          f"{barrio_share:.0%}" if barrio_share is not None else "—",
          help="The strongest comparison. It rises with scraping depth, not with a "
               f"lower bar than {MIN_COMPS} comparables.")
q2.metric("Listings seen more than once",
          f"{coverage['repeat_share']:.0%}" if coverage else "—",
          help="Days on market and price cuts need a listing observed twice or more. "
               "The weekly scrape grows this.")
q3.metric("Official price index up to",
          f"Q{quarter.quarter} {quarter.year}" if quarter is not None else "—",
          help="INE publishes each quarter about ten weeks after it ends.")
q4.metric("Household income year", str(income_year) if income_year else "—",
          help="INE publishes household income with a two-year lag.")

st.dataframe(
    pd.DataFrame([
        ("Listings", "Idealista search results", "Listing, placed in its barrio",
         "Weekly (València)"),
        ("Official prices", "INE house price index, table 79563",
         "Autonomous community, quarterly", "Weekly check"),
        ("Household income", "INE Atlas de Distribución de Renta, table 30824",
         "District, yearly", "Yearly"),
        ("Barrio shapes", "València open data (88 barrios)", "Barrio", "Static"),
        ("Mortgage rate", "Banco de España reference rate (BOE)", "Spain, monthly",
         f"Checked {SOURCES_CONSULTED_ON}"),
        ("Euribor", "EMMI 12-month, last closed month", "Eurozone, monthly",
         f"Checked {SOURCES_CONSULTED_ON}"),
        ("Transfer tax", "Each region's tax agency", "Autonomous community",
         f"Checked {SOURCES_CONSULTED_ON}"),
        ("Average salary", "INE salary structure survey 2024", "Autonomous community",
         f"Checked {SOURCES_CONSULTED_ON}"),
    ], columns=["What", "Source", "Grain", "Refreshed"]),
    width="stretch", hide_index=True,
)

st.divider()

# ── The limits ────────────────────────────────────────────────────────────────
st.markdown("#### What it cannot tell you")
l1, l2 = st.columns(2, gap="large")
l1.markdown(
    "- **Asking prices, not sale prices.** The INE index is the check on them, "
    "but it is regional.\n"
    "- **Nothing about the flat itself.** No condition, floor, light or noise — a "
    "score says the price is unusual, which is where a search starts."
)
l2.markdown(
    "- **No exact addresses.** Search cards are ~30× cheaper to scrape than detail "
    "pages, so map dots sit at their barrio's centre.\n"
    "- **Depth in one city.** València is scraped every week; the other cities hold "
    "one older snapshot, too thin for barrio benchmarks."
)
st.caption(
    f"Decisions behind all of this are written down as [ADRs]({REPO_URL}/tree/main/docs/adr)."
)
