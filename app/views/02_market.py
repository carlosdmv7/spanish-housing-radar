"""
Market — neighbourhood €/m² benchmarks, price spread, historical evolution.
"""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from components.charts import bar_ppsqm_with_range, line_price_history
from components.filters import municipality_filter, operation_filter
from config import PROPERTY_TYPE_LABELS
from connection import query
import pandas as pd
import streamlit as st
from theme import altair_chart, page_hero, section

page_hero(
    "📊",
    "Market Overview",
    "The benchmark every opportunity score is measured against: €/m² by "
    "neighbourhood, how wide the spread is, and where prices are heading.",
)


@st.cache_data(ttl=3600)
def load_municipalities():
    df = query(
        "SELECT DISTINCT municipality "
        "FROM spanish_housing_radar.main_silver.int_listings_current ORDER BY 1"
    )
    return df["municipality"].tolist()


try:
    munis = load_municipalities()
except Exception as exc:
    st.error(
        "**Can't reach the warehouse.** The app reads from MotherDuck — check that "
        "`MOTHERDUCK_TOKEN` is set in `.env` locally, or in the app's Secrets on "
        "Streamlit Cloud."
    )
    st.caption(f"Underlying error: {exc}")
    st.stop()

with st.sidebar:
    st.header("Filters")
    op = operation_filter()
    muni = municipality_filter(munis)
    prop = st.selectbox(
        "Property type",
        ["apartment", "house", "other"],
        format_func=lambda k: PROPERTY_TYPE_LABELS[k],
    )

# ── Load data ─────────────────────────────────────────────────────────────────
market_sql = (Path(__file__).parent.parent / "queries" / "market.sql").read_text()


@st.cache_data(ttl=600, show_spinner="Loading market data…")
def load_market(op, muni):
    return query(market_sql, operation_type=op, municipality=muni)


df = load_market(op, muni)
df = df[df["property_type"] == prop]

if df.empty:
    st.info(
        f"**No {PROPERTY_TYPE_LABELS[prop].lower()} benchmarks for this city yet.** "
        "Benchmarks need enough listings per neighbourhood to be meaningful. Coverage "
        "is deepest for **apartments** in **Valencia** — or pick *All cities*."
    )
    st.stop()

# ── KPIs ──────────────────────────────────────────────────────────────────────
unit = "€/m²" if op == "sale" else "€/m² rent"
c1, c2, c3, c4 = st.columns(4)
c1.metric("Neighbourhoods", len(df))
c2.metric(f"Median {unit}", f"€{df['median_ppsqm'].median():,.0f}")
c3.metric("Cheapest area", df.loc[df["median_ppsqm"].idxmin(), "neighborhood"].title(),
          help=f"€{df['median_ppsqm'].min():,.0f}/m²")
c4.metric("Priciest area", df.loc[df["median_ppsqm"].idxmax(), "neighborhood"].title(),
          help=f"€{df['median_ppsqm'].max():,.0f}/m²")

st.markdown("")


# ── Official market context (INE house-price index) ───────────────────────────
# Grounds the scraped ASKING prices against the official, transaction-based index.
@st.cache_data(ttl=3600)
def load_market_context(muni):
    return query(
        "SELECT * FROM spanish_housing_radar.main_gold.rpt_market_context "
        "WHERE ($m = 'all' OR municipality = $m)",
        m=muni,
    )


try:
    ctx = load_market_context(muni)
    ctx = ctx[ctx["hpi_yoy_general"].notna()]
    if not ctx.empty:
        section("Official market context · INE house-price index")
        st.markdown(
            ":small[Transaction-based reality check (INE IPV, latest quarter). The "
            "prices above are *asking* prices; this is where the market actually "
            "cleared. Regional grain, so it reads direction, never a per-flat value.]"
        )
        row = ctx.iloc[0] if muni != "all" else None
        if row is not None:
            region = str(row["region"]).title()
            k1, k2, k3 = st.columns(3)
            k1.metric(f"{region} · index (2015=100)", f"{row['hpi_index_general']:.1f}")
            k2.metric("YoY · all housing", f"{row['hpi_yoy_general']:+.1f}%")
            sh = row["hpi_yoy_second_hand"]
            k3.metric("YoY · second-hand", f"{sh:+.1f}%" if pd.notna(sh) else "—")
            st.markdown(f":small[Reference quarter: {row['latest_period']}]")
        else:
            st.dataframe(
                ctx.assign(region_name=ctx["region"].str.title())
                   [["municipality", "region_name", "hpi_yoy_general", "hpi_yoy_second_hand"]],
                width="stretch", hide_index=True,
                column_config={
                    "municipality": st.column_config.TextColumn("City"),
                    "region_name": st.column_config.TextColumn("Region"),
                    "hpi_yoy_general": st.column_config.NumberColumn(
                        "YoY · all", format="%+.1f%%"),
                    "hpi_yoy_second_hand": st.column_config.NumberColumn(
                        "YoY · 2nd hand", format="%+.1f%%"),
                },
            )
        st.markdown("")
except Exception as exc:  # market context is a nice-to-have, never block the page
    st.markdown(f":small[Official market context is unavailable right now: {exc}]")

# ── Ranked €/m² chart ─────────────────────────────────────────────────────────
section("Price per m² by neighbourhood")
altair_chart(bar_ppsqm_with_range(df))

# ── Benchmark table ───────────────────────────────────────────────────────────
section("Neighbourhood benchmark")
st.markdown(
    ":small[These medians are the denominators of the opportunity score. A wide "
    "P25–P75 spread means the barrio is heterogeneous, so its median is a weaker "
    "reference — worth checking before trusting a score built on it.]"
)
st.dataframe(
    df.assign(area=df["neighborhood"].str.title())[[
        "area", "total_listings", "median_ppsqm", "p25_ppsqm", "p75_ppsqm",
        "avg_ppsqm", "stddev_ppsqm", "median_size_sqm",
    ]].sort_values("median_ppsqm", ascending=False),
    width="stretch",
    hide_index=True,
    column_config={
        "area": st.column_config.TextColumn("Neighbourhood", pinned=True),
        "total_listings": st.column_config.NumberColumn(
            "Listings", format="%,d",
            help="Comparables behind this benchmark. Fewer than 8 and the score "
                 "falls back to a coarser grain.",
        ),
        "median_ppsqm": st.column_config.NumberColumn("Median €/m²", format="€%,d"),
        "p25_ppsqm": st.column_config.NumberColumn("P25", format="€%,d"),
        "p75_ppsqm": st.column_config.NumberColumn("P75", format="€%,d"),
        "avg_ppsqm": st.column_config.NumberColumn("Mean €/m²", format="€%,d"),
        "stddev_ppsqm": st.column_config.NumberColumn(
            "Std dev", format="€%,d",
            help="Denominator of the z-score. A large spread compresses scores "
                 "towards 50.",
        ),
        "median_size_sqm": st.column_config.NumberColumn("Median size", format="%.0f m²"),
    },
)

# ── Price history ─────────────────────────────────────────────────────────────
st.markdown("")
section("Price evolution over time")

history_sql = (Path(__file__).parent.parent / "queries" / "price_history.sql").read_text()


@st.cache_data(ttl=600)
def load_history(op, muni):
    return query(history_sql, operation_type=op, municipality=muni)


hist = load_history(op, muni)
hist = hist[hist["property_type"] == prop]

if hist["scraped_date"].nunique() > 1:
    top_hoods = hist.groupby("neighborhood")["total_listings"].sum().nlargest(8).index
    altair_chart(line_price_history(hist[hist["neighborhood"].isin(top_hoods)]))
else:
    st.info(
        "**Only one snapshot so far, so there is no trend to draw.** Price history is "
        "accumulated, not backfilled — `int_listings_history` keeps every observation, "
        "and this chart fills in once the pipeline has run on several days. Listing "
        "scraping is currently paused, so the clock is stopped here on purpose."
    )
