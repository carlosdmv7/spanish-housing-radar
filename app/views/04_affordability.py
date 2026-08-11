"""
Affordability — income required per neighbourhood, years of salary, buy vs rent.
"""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from components.charts import bar_buy_vs_rent, bar_required_income, bar_years_of_salary
from components.filters import load_municipalities, municipality_filter
from components.mortgage import compute_mortgage, max_affordable_loan, required_income
from config import (
    AFFORDABILITY_RATIO_MAX,
    AFFORDABILITY_SOURCE_NOTE,
    MORTGAGE_DEFAULT_RATE_FIXED,
    MORTGAGE_DEFAULT_YEARS,
    OVERBURDEN_PCT,
    VALENCIA_AVG_NET_SALARY_MONTHLY,
)
from connection import query
import pandas as pd
import streamlit as st
from theme import altair_chart, page_hero, section

page_hero(
    "Affordability Index",
    "What you need to earn to buy in each neighbourhood, how many years of salary a "
    "flat costs, and whether buying beats renting the same street.",
)

# The verdict "this barrio is out of reach" is only as trustworthy as the income
# and rate it was computed from, so both are cited before any verdict is shown.
st.caption(AFFORDABILITY_SOURCE_NOTE)

with st.sidebar:
    st.header("Parameters")
    net_income = st.number_input(
        "Monthly net income (€)", min_value=500, max_value=20_000,
        value=int(VALENCIA_AVG_NET_SALARY_MONTHLY), step=100, format="%d",
        help="Defaults to the Comunitat Valenciana average, derived from INE's 2024 "
             "salary survey — see the note under the page title.",
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
    # This list used to be hardcoded to valència/madrid/barcelona, so the five
    # other cities in the warehouse -- bilbao, málaga, sevilla, valladolid,
    # zaragoza -- were simply unreachable from this page. A filter that silently
    # omits data is the same failure as dropping low-confidence rows: the visitor
    # cannot see what is missing. Read the list from the warehouse instead, so it
    # can never drift from what is actually there again.
    muni = municipality_filter(load_municipalities())

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

# ── Against what the district actually earns ──────────────────────────────────
# Everything above answers "can *I* afford this?" from the income in the sidebar.
# This answers a different question the app could not previously ask at all: can
# the people who already live there afford it? A barrio can be cheap because it
# is a bargain or because nobody in it can pay more, and €/m² cannot tell those
# apart. INE's household income is the denominator that can.
st.markdown("")
section("Priced against the people who live there")


@st.cache_data(ttl=3600, show_spinner=False)
def load_district_income(muni):
    return query(
        "SELECT * FROM spanish_housing_radar.main_gold.rpt_district_affordability "
        "WHERE ($m = 'all' OR municipality = $m) "
        "AND property_type = 'apartment'",
        m=muni,
    )


try:
    dist_all = load_district_income(muni)
except Exception as exc:
    dist_all = pd.DataFrame()
    st.caption(f"District income is unavailable right now: {exc}")

# The rent half of this table has existed in gold since the model was written and
# nothing read it, because this page hard-coded operation_type = 'sale'. With 73
# València rentals in the warehouse that was defensible; at 308 it is a column
# going to waste, and it carries the harder finding of the two.
if dist_all.empty:
    dist = dist_rent = dist_all
else:
    dist = (
        dist_all[dist_all["years_of_household_income"].notna()]
        .sort_values("years_of_household_income", ascending=False)
    )
    dist_rent = (
        dist_all[dist_all["rent_pct_of_household_income"].notna()]
        .sort_values("rent_pct_of_household_income", ascending=False)
    )

if dist.empty and dist_rent.empty:
    st.info(
        "**No official income figures for this city's districts yet.** The mapping "
        "from INE's numbered districts to the names used here exists for València "
        "only — every other city needs its own official district list before its "
        "figures can be trusted."
    )
else:
    ref_year = int(dist_all["income_reference_year"].max())
    tab_buy, tab_rent = st.tabs(["To buy", "To rent"])

    with tab_buy:
        if dist.empty:
            st.info("**No sale listings in these districts yet.**")
        else:
            st.markdown(
                ":small[Years of **median household income** to buy the median flat "
                "outright, ignoring financing entirely. The moment a mortgage rate "
                "enters, the number stops describing the district and starts "
                "describing the borrower.]"
            )
            st.dataframe(
                dist.assign(area=dist["district"].str.title())[[
                    "area", "listings", "median_price_eur", "median_ppsqm",
                    "net_income_per_household", "years_of_household_income",
                ]],
                width="stretch",
                hide_index=True,
                column_config={
                    "area": st.column_config.TextColumn("District", pinned=True),
                    "listings": st.column_config.NumberColumn("Listings", format="%d"),
                    "median_price_eur": st.column_config.NumberColumn(
                        "Median price", format="€%,d"),
                    "median_ppsqm": st.column_config.NumberColumn("€/m²", format="€%,d"),
                    "net_income_per_household": st.column_config.NumberColumn(
                        "Household income", format="€%,d",
                        help=f"INE Atlas de Distribución de Renta, reference year {ref_year}.",
                    ),
                    "years_of_household_income": st.column_config.NumberColumn(
                        "Years to buy", format="%.1f",
                        help="Median asking price ÷ median net household income.",
                    ),
                },
            )

            # The comparison that makes the point: the priciest per m² is not the
            # least affordable, because the two are decoupled by income.
            dearest = dist.loc[dist["median_ppsqm"].idxmax()]
            hardest = dist.loc[dist["years_of_household_income"].idxmax()]
            if dearest["district"] != hardest["district"]:
                st.markdown(
                    f":small[**{dearest['district'].title()}** has the highest €/m² "
                    f"(€{dearest['median_ppsqm']:,.0f}) yet takes "
                    f"{dearest['years_of_household_income']:.1f} years of local "
                    f"income, while **{hardest['district'].title()}** is cheaper per "
                    f"m² (€{hardest['median_ppsqm']:,.0f}) and takes "
                    f"{hardest['years_of_household_income']:.1f}. Price and "
                    "affordability are not the same ranking — which is the whole "
                    "reason this table exists.]"
                )

    with tab_rent:
        if dist_rent.empty:
            st.info(
                "**No rental listings in these districts yet.** This is the same "
                "question asked of renting, and it needs rent scraped in the same "
                "districts the income figures cover."
            )
        else:
            st.markdown(
                f":small[Share of **median net household income** the median asking "
                f"rent consumes. Above **{OVERBURDEN_PCT:.0f}%** is the threshold "
                "Eurostat and INE treat as housing-cost overburden.]"
            )
            over = dist_rent[dist_rent["rent_pct_of_household_income"] > OVERBURDEN_PCT]
            if not over.empty:
                st.warning(
                    f"**{len(over)} of {len(dist_rent)} districts sit above the "
                    f"{OVERBURDEN_PCT:.0f}% overburden line**, from "
                    f"{over['rent_pct_of_household_income'].min():.0f}% to "
                    f"{over['rent_pct_of_household_income'].max():.0f}%. Read that as "
                    "the gap between the market and the residents, not as what "
                    "households pay: these are asking rents for flats available "
                    "today, while the income is the district's median across "
                    "everyone — most of whom are not moving, and many of whom own."
                )
            st.dataframe(
                dist_rent.assign(area=dist_rent["district"].str.title())[[
                    "area", "listings", "median_price_eur", "median_ppsqm",
                    "net_income_per_household", "rent_pct_of_household_income",
                ]],
                width="stretch",
                hide_index=True,
                column_config={
                    "area": st.column_config.TextColumn("District", pinned=True),
                    "listings": st.column_config.NumberColumn("Listings", format="%d"),
                    "median_price_eur": st.column_config.NumberColumn(
                        "Median rent", format="€%,d", help="Monthly asking rent."),
                    "median_ppsqm": st.column_config.NumberColumn(
                        "€/m²/mo", format="€%.1f"),
                    "net_income_per_household": st.column_config.NumberColumn(
                        "Household income", format="€%,d",
                        help=f"INE Atlas de Distribución de Renta, reference year {ref_year}.",
                    ),
                    "rent_pct_of_household_income": st.column_config.ProgressColumn(
                        "% of income", min_value=0, max_value=100, format="%.0f%%",
                        help="Median asking rent × 12 ÷ median net household income.",
                    ),
                },
            )

    st.caption(
        f"Income: INE Atlas de Distribución de Renta de los Hogares, table 30824, "
        f"reference year {ref_year} — published with a ~2-year lag, so it is the "
        "latest official figure, not a current one. Prices are asking prices from "
        "today's listings, so the ratio mixes two dates and reads as a direction, "
        "not a precise multiple."
    )

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
