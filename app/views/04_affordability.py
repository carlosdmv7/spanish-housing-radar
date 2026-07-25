"""
Affordability — income required per neighbourhood, years of salary, buy vs rent.
"""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from components.charts import bar_buy_vs_rent, bar_required_income, bar_years_of_salary
from components.mortgage import compute_mortgage, max_affordable_loan, required_income
from config import (
    AFFORDABILITY_RATIO_MAX,
    MORTGAGE_DEFAULT_RATE_FIXED,
    MORTGAGE_DEFAULT_YEARS,
    VALENCIA_AVG_NET_SALARY_MONTHLY,
)
from connection import query
import streamlit as st
from theme import altair_chart, page_hero, section

page_hero(
    "💰",
    "Affordability Index",
    "What you need to earn to buy in each neighbourhood, how many years of salary a "
    "flat costs, and whether buying beats renting the same street.",
)

with st.sidebar:
    st.header("Parameters")
    net_income = st.number_input(
        "Monthly net income (€)", min_value=500, max_value=20_000,
        value=int(VALENCIA_AVG_NET_SALARY_MONTHLY), step=100, format="%d",
        help="Defaults to the average net salary in Valencia.",
    )
    ltv = st.slider("LTV (%)", 50, 100, 80)
    rate = st.number_input(
        "Fixed mortgage rate (%)", min_value=0.5, max_value=10.0,
        value=MORTGAGE_DEFAULT_RATE_FIXED, step=0.1, format="%.1f",
    )
    years = st.slider("Mortgage term (years)", 10, 40, MORTGAGE_DEFAULT_YEARS)
    max_ratio = st.slider(
        "Max payment/income ratio (%)", 20, 50, int(AFFORDABILITY_RATIO_MAX),
        help="Spanish lenders rarely go past 35% of net income.",
    )
    muni = st.selectbox(
        "City",
        options=["valència", "madrid", "barcelona", "all"],
        format_func=lambda k: "All cities" if k == "all" else k.title(),
    )

# ── Load data ─────────────────────────────────────────────────────────────────
aff_sql = (Path(__file__).parent.parent / "queries" / "affordability.sql").read_text()


@st.cache_data(ttl=600, show_spinner="Loading affordability data…")
def load_data(muni):
    sale = query(aff_sql, operation_type="sale", municipality=muni)
    rent = query(aff_sql, operation_type="rent", municipality=muni)
    return sale, rent


try:
    df_sale, df_rent = load_data(muni)
except Exception as exc:
    st.error(
        "**Can't reach the warehouse, so affordability can't be computed.** Check "
        "`MOTHERDUCK_TOKEN` in `.env` locally, or the app's Secrets on Streamlit Cloud."
    )
    st.caption(f"Underlying error: {exc}")
    st.stop()

if df_sale.empty:
    st.info(
        "**No sale listings for this city yet**, so there is nothing to price against "
        "an income. Coverage is deepest in **Valencia** — or pick *All cities*."
    )
    st.stop()

# ── Per-neighbourhood affordability ───────────────────────────────────────────
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
hood_stats["affordable"] = hood_stats["required_income"] <= net_income
hood_stats["years_of_salary"] = hood_stats["median_price"] / (net_income * 12)

# ── KPIs ──────────────────────────────────────────────────────────────────────
max_budget = max_affordable_loan(net_income, max_ratio, rate, years) / (ltv / 100)

c1, c2, c3, c4 = st.columns(4)
c1.metric("Within reach", f"{int(hood_stats['affordable'].sum())} / {len(hood_stats)}",
          help="Neighbourhoods whose median flat you could service at these terms.")
c2.metric("Cheapest entry", f"€{hood_stats['required_income'].min():,.0f}/mo",
          help="Income needed in the most affordable neighbourhood.")
c3.metric("Median years of salary", f"{hood_stats['years_of_salary'].median():.1f} yrs")
c4.metric("Your max budget", f"€{max_budget:,.0f}",
          help=f"Highest property price you could finance at {ltv}% LTV.")

st.markdown(
    ":small[Based on **asking** prices, not transactions, and on the median flat in "
    "each barrio — a barrio can be out of reach at the median and still hold something "
    "you can afford.]"
)
st.markdown("")

# ── Charts ────────────────────────────────────────────────────────────────────
col_l, col_r = st.columns(2)
with col_l:
    altair_chart(bar_required_income(hood_stats, net_income))
with col_r:
    altair_chart(bar_years_of_salary(hood_stats))

# ── Buy vs Rent ───────────────────────────────────────────────────────────────
st.markdown("")
section("Buy vs rent")

if df_rent.empty:
    st.info(
        "**No rental listings for this city**, so buy-vs-rent can't be computed. The "
        "comparison needs both operations scraped for the same neighbourhoods — switch "
        "city, or pick *All cities*."
    )
else:
    rent_stats = (
        df_rent.groupby("neighborhood")
        .agg(median_rent=("price_eur", "median"))
        .reset_index()
    )
    hood_stats["monthly_mortgage"] = hood_stats["median_price"].apply(
        lambda p: compute_mortgage(p * ltv / 100, rate, years).monthly_payment
    )
    merged = hood_stats.merge(rent_stats, on="neighborhood", how="inner")

    if merged.empty:
        st.info(
            "**No neighbourhood has both sale and rental listings in this selection**, "
            "so there is nothing to compare like-for-like."
        )
    else:
        merged["buy_vs_rent_ratio"] = merged["monthly_mortgage"] / merged["median_rent"]
        altair_chart(bar_buy_vs_rent(merged))

        st.markdown(
            ":small[A ratio above 1 means the mortgage payment exceeds the median rent "
            "for the same barrio — before service charges, tax and maintenance, which "
            "fall on the owner.]"
        )
        st.dataframe(
            merged.assign(area=merged["neighborhood"].str.title())[[
                "area", "median_price", "monthly_mortgage", "median_rent",
                "buy_vs_rent_ratio", "years_of_salary", "required_income",
            ]].sort_values("required_income"),
            width="stretch",
            hide_index=True,
            column_config={
                "area": st.column_config.TextColumn("Neighbourhood", pinned=True),
                "median_price": st.column_config.NumberColumn("Median price", format="€%,d"),
                "monthly_mortgage": st.column_config.NumberColumn(
                    "Mortgage/mo", format="€%,d"),
                "median_rent": st.column_config.NumberColumn("Rent/mo", format="€%,d"),
                "buy_vs_rent_ratio": st.column_config.NumberColumn(
                    "Buy/rent", format="%.2f×",
                    help="Mortgage payment ÷ median rent. Above 1 favours renting on "
                         "monthly cash flow alone.",
                ),
                "years_of_salary": st.column_config.NumberColumn(
                    "Years of salary", format="%.1f"),
                "required_income": st.column_config.NumberColumn(
                    "Income needed", format="€%,d"),
            },
        )
