"""
Page 4 — Affordability Index
Buy vs rent, years-of-salary, income required per neighborhood.
"""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from components.mortgage import compute_mortgage, max_affordable_loan, required_income
from config import (
    AFFORDABILITY_RATIO_MAX,
    MORTGAGE_DEFAULT_RATE_FIXED,
    MORTGAGE_DEFAULT_YEARS,
    PAGE_ICON,
    VALENCIA_AVG_NET_SALARY_MONTHLY,
)
from connection import query
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

st.set_page_config(page_title="Affordability · SHR", page_icon=PAGE_ICON, layout="wide")
st.title("💰 Affordability Index")
st.caption("How much do you need to earn to live in each neighborhood? Buy vs rent comparison.")

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("Parameters")

    net_income = st.number_input(
        "Monthly net income (€)", min_value=500, max_value=20_000,
        value=int(VALENCIA_AVG_NET_SALARY_MONTHLY), step=100, format="%d",
    )
    ltv = st.slider("LTV (%)", 50, 100, 80)
    rate = st.number_input(
        "Fixed mortgage rate (%)", min_value=0.5, max_value=10.0,
        value=MORTGAGE_DEFAULT_RATE_FIXED, step=0.1, format="%.1f",
    )
    years     = st.slider("Mortgage term (years)", 10, 40, MORTGAGE_DEFAULT_YEARS)
    max_ratio = st.slider("Max payment/income ratio (%)", 20, 50, int(AFFORDABILITY_RATIO_MAX))
    muni      = st.selectbox(
        "City",
        options=["all", "valència", "madrid", "barcelona"],
        format_func=lambda k: "All cities" if k == "all" else k.title(),
    )

# ── Load data ─────────────────────────────────────────────────────────────────
aff_sql = (Path(__file__).parent.parent / "queries" / "affordability.sql").read_text()

@st.cache_data(ttl=600)
def load_data(muni):
    sale = query(aff_sql, operation_type="sale", municipality=muni)
    rent = query(aff_sql, operation_type="rent", municipality=muni)
    return sale, rent

df_sale, df_rent = load_data(muni)

if df_sale.empty:
    st.warning("No sale data available for the selected filters.")
    st.stop()

# ── Per-neighborhood affordability ────────────────────────────────────────────
hood_stats = (
    df_sale.groupby("neighborhood")
    .agg(
        median_price=("price_eur", "median"),
        median_ppsqm=("price_per_sqm", "median"),
        listings=("listing_pk", "count"),
    )
    .reset_index()
)

hood_stats["required_income"] = hood_stats["median_price"].apply(
    lambda p: required_income(p * ltv / 100, rate, years, max_ratio)
)
hood_stats["affordable"]      = hood_stats["required_income"] <= net_income
hood_stats["years_of_salary"] = hood_stats["median_price"] / (net_income * 12)

# ── KPIs ──────────────────────────────────────────────────────────────────────
affordable_count = hood_stats["affordable"].sum()
total_hoods      = len(hood_stats)
max_budget       = max_affordable_loan(net_income, max_ratio, rate, years) / (ltv / 100)

c1, c2, c3, c4 = st.columns(4)
c1.metric("Affordable neighborhoods", f"{affordable_count} / {total_hoods}")
c2.metric("Min income needed",        f"€{hood_stats['required_income'].min():,.0f}/mo",
          help="Cheapest neighborhood")
c3.metric("Median years of salary",   f"{hood_stats['years_of_salary'].median():.1f} yrs")
c4.metric("Your max budget",          f"€{max_budget:,.0f}",
          help=f"Max property price at {ltv}% LTV")

st.markdown("---")

# ── Charts ────────────────────────────────────────────────────────────────────
col_l, col_r = st.columns(2)

with col_l:
    st.markdown("#### Minimum income by neighborhood")
    fig = px.bar(
        hood_stats.sort_values("required_income"),
        x="required_income",
        y="neighborhood",
        orientation="h",
        color="affordable",
        color_discrete_map={True: "#22c55e", False: "#ef4444"},
        labels={
            "required_income": "Min income (€/month)",
            "neighborhood":    "",
            "affordable":      "Affordable",
        },
        title=f"Reference line: €{net_income:,}/month",
    )
    fig.add_vline(
        x=net_income, line_dash="dash", line_color="#2563eb",
        annotation_text=f"Your income: €{net_income:,}",
    )
    fig.update_layout(margin={"l":0, "r":0, "t":40, "b":0}, showlegend=False)
    st.plotly_chart(fig, use_container_width=True)

with col_r:
    st.markdown("#### Years of salary needed")
    fig2 = px.bar(
        hood_stats.sort_values("years_of_salary"),
        x="years_of_salary",
        y="neighborhood",
        orientation="h",
        color="years_of_salary",
        color_continuous_scale="RdYlGn_r",
        labels={"years_of_salary": "Years of net salary", "neighborhood": ""},
        title="Median price / annual net salary",
    )
    fig2.update_layout(coloraxis_showscale=False, margin={"l":0, "r":0, "t":40, "b":0})
    st.plotly_chart(fig2, use_container_width=True)

# ── Buy vs Rent ───────────────────────────────────────────────────────────────
st.markdown("---")
st.markdown("#### Buy vs Rent by neighborhood")
st.caption("Estimated monthly mortgage payment vs median rent for the same neighborhood.")

if not df_rent.empty:
    rent_stats = (
        df_rent.groupby("neighborhood")
        .agg(median_rent=("price_eur", "median"))
        .reset_index()
    )

    hood_stats["monthly_mortgage"] = hood_stats["median_price"].apply(
        lambda p: compute_mortgage(p * ltv / 100, rate, years).monthly_payment
    )

    merged = hood_stats.merge(rent_stats, on="neighborhood", how="inner")
    merged["buy_vs_rent_ratio"] = merged["monthly_mortgage"] / merged["median_rent"]

    fig3 = go.Figure()
    fig3.add_trace(go.Bar(
        name="Monthly mortgage (€)",
        x=merged["neighborhood"],
        y=merged["monthly_mortgage"],
        marker_color="#2563eb",
    ))
    fig3.add_trace(go.Bar(
        name="Median rent (€/month)",
        x=merged["neighborhood"],
        y=merged["median_rent"],
        marker_color="#f97316",
    ))
    fig3.update_layout(
        barmode="group",
        title="Monthly mortgage vs median rent",
        xaxis_title="",
        yaxis_title="€/month",
        margin={"l":0, "r":0, "t":40, "b":0},
    )
    st.plotly_chart(fig3, use_container_width=True)

    st.markdown("#### Summary table")
    st.dataframe(
        merged[[
            "neighborhood", "median_price", "monthly_mortgage",
            "median_rent", "buy_vs_rent_ratio", "years_of_salary", "required_income",
        ]].rename(columns={
            "neighborhood":      "Neighborhood",
            "median_price":      "Median price (€)",
            "monthly_mortgage":  "Monthly mortgage (€)",
            "median_rent":       "Median rent (€/mo)",
            "buy_vs_rent_ratio": "Buy/rent ratio",
            "years_of_salary":   "Years of salary",
            "required_income":   "Min income (€/mo)",
        }).sort_values("Min income (€/mo)"),
        use_container_width=True,
        hide_index=True,
    )
else:
    st.info("No rental data available to compare buy vs rent.")
