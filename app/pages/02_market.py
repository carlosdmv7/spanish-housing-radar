"""
Page 2 — Market Overview
Neighborhood stats, price distribution, historical evolution.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import plotly.graph_objects as go
import streamlit as st

from components.charts import bar_ppsqm_by_neighborhood, line_price_history
from components.filters import municipality_filter, operation_filter
from config import PAGE_ICON
from connection import query

st.set_page_config(page_title="Market · SHR", page_icon=PAGE_ICON, layout="wide")
st.title("📊 Market Overview")
st.caption("Neighborhood benchmarks and price evolution.")

# ── Sidebar ───────────────────────────────────────────────────────────────────
@st.cache_data(ttl=3600)
def load_municipalities():
    df = query("SELECT DISTINCT municipality FROM spanish_housing_radar.main_silver.int_listings_current ORDER BY 1")
    return df["municipality"].tolist()

munis = load_municipalities()

with st.sidebar:
    st.header("Filters")
    op   = operation_filter()
    muni = municipality_filter(munis)
    prop = st.selectbox(
        "Property type",
        ["apartment", "house", "other"],
        format_func=lambda k: {"apartment": "Apartment", "house": "House", "other": "Other"}[k],
    )

# ── Load data ─────────────────────────────────────────────────────────────────
market_sql = (Path(__file__).parent.parent / "queries" / "market.sql").read_text()

@st.cache_data(ttl=600, show_spinner="Loading market data…")
def load_market(op, muni):
    return query(market_sql, operation_type=op, municipality=muni)

df = load_market(op, muni)
df = df[df["property_type"] == prop]

if df.empty:
    st.warning("No data available for the selected filters.")
    st.stop()

# ── KPIs ──────────────────────────────────────────────────────────────────────
c1, c2, c3, c4 = st.columns(4)
c1.metric("Neighborhoods",       len(df))
c2.metric("Overall median €/sqm", f"€{df['median_ppsqm'].median():,.0f}")
c3.metric("Cheapest neighborhood", df.loc[df['median_ppsqm'].idxmin(), 'neighborhood'].title())
c4.metric("Most expensive",        df.loc[df['median_ppsqm'].idxmax(), 'neighborhood'].title())

st.markdown("---")

# ── Charts ────────────────────────────────────────────────────────────────────
col_left, col_right = st.columns(2)

with col_left:
    st.plotly_chart(
        bar_ppsqm_by_neighborhood(df, f"€/sqm by neighborhood · {op}"),
        use_container_width=True,
    )

with col_right:
    df_sorted = df.sort_values("median_ppsqm", ascending=False).head(15)
    fig = go.Figure()
    fig.add_trace(go.Bar(
        name="IQR range (p25–p75)",
        x=df_sorted["neighborhood"],
        y=df_sorted["p75_ppsqm"] - df_sorted["p25_ppsqm"],
        base=df_sorted["p25_ppsqm"],
        marker_color="rgba(37,99,235,0.3)",
    ))
    fig.add_trace(go.Scatter(
        name="Median",
        x=df_sorted["neighborhood"],
        y=df_sorted["median_ppsqm"],
        mode="markers",
        marker=dict(color="#2563eb", size=8),
    ))
    fig.update_layout(title="Price range by neighborhood (top 15)", margin=dict(l=0, r=0, t=40, b=0))
    st.plotly_chart(fig, use_container_width=True)

# ── Stats table ───────────────────────────────────────────────────────────────
st.markdown("#### Neighborhood benchmark table")
display_cols = {
    "neighborhood":  "Neighborhood",
    "total_listings": "Listings",
    "median_ppsqm":  "€/sqm median",
    "p25_ppsqm":     "P25",
    "p75_ppsqm":     "P75",
    "avg_ppsqm":     "€/sqm avg",
    "stddev_ppsqm":  "Std dev",
    "median_size_sqm": "Median sqm",
}
st.dataframe(
    df[list(display_cols.keys())].rename(columns=display_cols).sort_values("€/sqm median", ascending=False),
    use_container_width=True,
    hide_index=True,
)

# ── Price history ─────────────────────────────────────────────────────────────
st.markdown("---")
st.markdown("#### Price evolution over time")
st.caption("Available once multiple pipeline runs have accumulated data.")

history_sql = (Path(__file__).parent.parent / "queries" / "price_history.sql").read_text()

@st.cache_data(ttl=600)
def load_history(op, muni):
    return query(history_sql, operation_type=op, municipality=muni)

hist = load_history(op, muni)
hist = hist[hist["property_type"] == prop]

if len(hist["scraped_date"].unique()) > 1:
    top_hoods    = hist.groupby("neighborhood")["total_listings"].sum().nlargest(8).index
    hist_filtered = hist[hist["neighborhood"].isin(top_hoods)]
    st.plotly_chart(line_price_history(hist_filtered), use_container_width=True)
else:
    st.info("Not enough historical data yet. Come back after a few days of pipeline runs.")