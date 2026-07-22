"""
Market — neighbourhood €/sqm benchmarks, price spread, historical evolution.
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
from styles import page_hero, section

page_hero(
    "📊",
    "Market Overview",
    "Benchmark €/sqm across neighbourhoods, see how wide the price spread is, "
    "and track how prices move over time.",
)


# ── Filters ───────────────────────────────────────────────────────────────────
@st.cache_data(ttl=3600)
def load_municipalities():
    df = query("SELECT DISTINCT municipality FROM spanish_housing_radar.main_silver.int_listings_current ORDER BY 1")
    return df["municipality"].tolist()


munis = load_municipalities()

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
    st.warning("No data for this combination. Try another city or property type.")
    st.stop()

# ── KPIs ──────────────────────────────────────────────────────────────────────
unit = "€/sqm" if op == "sale" else "€/sqm rent"
c1, c2, c3, c4 = st.columns(4)
c1.metric("Neighbourhoods", len(df))
c2.metric(f"Median {unit}", f"€{df['median_ppsqm'].median():,.0f}")
c3.metric("Cheapest area", df.loc[df["median_ppsqm"].idxmin(), "neighborhood"].title(),
          help=f"€{df['median_ppsqm'].min():,.0f}/sqm")
c4.metric("Priciest area", df.loc[df["median_ppsqm"].idxmax(), "neighborhood"].title(),
          help=f"€{df['median_ppsqm'].max():,.0f}/sqm")

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
        st.caption(
            "Transaction-based reality check (INE IPV, latest quarter). Scraped "
            "prices above are *asking* prices; this is where the market actually is."
        )
        row = ctx.iloc[0] if muni != "all" else None
        if row is not None:
            region = str(row["region"]).title()
            k1, k2, k3 = st.columns(3)
            k1.metric(f"{region} · index (2015=100)", f"{row['hpi_index_general']:.1f}")
            k2.metric("YoY · all housing", f"{row['hpi_yoy_general']:+.1f}%")
            sh = row["hpi_yoy_second_hand"]
            k3.metric("YoY · second-hand", f"{sh:+.1f}%" if pd.notna(sh) else "—")
            st.caption(f"Reference quarter: {row['latest_period']}")
        else:
            ctx["region"] = ctx["region"].str.title()
            st.dataframe(
                ctx[["municipality", "region", "hpi_yoy_general", "hpi_yoy_second_hand"]]
                .rename(columns={
                    "municipality": "City", "region": "Region",
                    "hpi_yoy_general": "YoY % (all)",
                    "hpi_yoy_second_hand": "YoY % (2nd hand)",
                }),
                use_container_width=True, hide_index=True,
            )
        st.markdown("")
except Exception as exc:  # market context is a nice-to-have, never block the page
    st.caption(f"Market context unavailable: {exc}")

# ── Ranked €/sqm chart ────────────────────────────────────────────────────────
section("Price per m² by neighbourhood")
st.plotly_chart(bar_ppsqm_with_range(df), use_container_width=True)

# ── Benchmark table ───────────────────────────────────────────────────────────
section("Neighbourhood benchmark")
display_cols = {
    "neighborhood": "Neighbourhood",
    "total_listings": "Listings",
    "median_ppsqm": "Median €/sqm",
    "p25_ppsqm": "P25",
    "p75_ppsqm": "P75",
    "avg_ppsqm": "Avg €/sqm",
    "stddev_ppsqm": "Std dev",
    "median_size_sqm": "Median sqm",
}
st.dataframe(
    df[list(display_cols.keys())].rename(columns=display_cols)
    .sort_values("Median €/sqm", ascending=False),
    use_container_width=True,
    hide_index=True,
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

if len(hist["scraped_date"].unique()) > 1:
    top_hoods = hist.groupby("neighborhood")["total_listings"].sum().nlargest(8).index
    st.plotly_chart(
        line_price_history(hist[hist["neighborhood"].isin(top_hoods)]),
        use_container_width=True,
    )
else:
    st.info("📈 Only one snapshot so far — price trends unlock once the daily pipeline has run a few days.")
