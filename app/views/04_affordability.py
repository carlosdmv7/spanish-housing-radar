"""
Value check — is the area itself overpriced?

Deals asks whether a flat is cheap *for its barrio*. This page asks whether the
barrio is, and it measures that against the two things a price should answer
to: what a flat rents for, and what the people who live there earn (ADR-0008).

Nothing here depends on the visitor's own income. The old page asked for it
and then drew every barrio as out of reach — the default was an average
salary, so the person reading it was almost always under the line, which says
something about them and nothing about the area. "Can I afford it?" is the
Budget page's question.
"""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from chrome import page_header
from components.charts import bar_district_burden, scatter_price_vs_yield
from components.filters import city_picker, load_municipalities
from config import OVERBURDEN_PCT
from connection import query
import pandas as pd
import streamlit as st
from theme import altair_chart

# transform/dbt_project.yml → vars.min_listings_for_area_stat, the threshold
# behind rpt_district_affordability.low_sample_flag. The barrio yields below use
# the same bar on *both* sides — 8 flats for sale and 8 for rent — because a
# yield is a ratio of two medians and is only as solid as the thinner one.
MIN_LISTINGS = 8
GOLD = "spanish_housing_radar.main_gold"
MARKET_SQL = (Path(__file__).parent.parent / "queries" / "market.sql").read_text()

page_header(
    "Is the area itself overpriced?",
    "What a barrio asks, against what its flats rent for and what its residents earn.",
)

try:
    munis = load_municipalities()
except Exception as exc:
    st.error(
        "**Can't reach the warehouse.** Locally that needs `MOTHERDUCK_TOKEN` in "
        "`.env`; on Streamlit Cloud it comes from the app's Secrets."
    )
    st.caption(f"Underlying error: {exc}")
    st.stop()

if len(munis) > 1:
    c_city, _ = st.columns([1.4, 4.6])
    with c_city:
        city = city_picker(munis)
else:
    city = city_picker(munis)


@st.cache_data(ttl=600, show_spinner="Loading prices and incomes…")
def load(city: str) -> tuple[pd.Series, pd.DataFrame, pd.DataFrame]:
    medians = query(f"""
        SELECT MEDIAN(price_per_sqm) FILTER (WHERE operation_type = 'sale') AS sale,
               MEDIAN(price_per_sqm) FILTER (WHERE operation_type = 'rent') AS rent
        FROM {GOLD}.rpt_opportunities
        WHERE municipality = $city AND property_type = 'apartment'
    """, city=city).iloc[0]

    sale = query(MARKET_SQL, operation_type="sale", municipality=city)
    rent = query(MARKET_SQL, operation_type="rent", municipality=city)
    keep = ["neighborhood", "median_ppsqm", "total_listings"]
    barrios = (
        sale[sale["property_type"] == "apartment"][keep]
        .merge(rent[rent["property_type"] == "apartment"][keep],
               on="neighborhood", suffixes=("_sale", "_rent"))
        .rename(columns={"median_ppsqm_sale": "sale_ppsqm",
                         "median_ppsqm_rent": "rent_ppsqm"})
    )
    barrios = barrios[(barrios["total_listings_sale"] >= MIN_LISTINGS)
                      & (barrios["total_listings_rent"] >= MIN_LISTINGS)]
    barrios = barrios.assign(
        yield_pct=barrios["rent_ppsqm"] * 12 / barrios["sale_ppsqm"] * 100,
        listings=barrios["total_listings_sale"] + barrios["total_listings_rent"],
    )

    districts = query(f"""
        SELECT district, operation_type, listings, low_sample_flag, median_price_eur,
               net_income_per_household, years_of_household_income,
               rent_pct_of_household_income, income_reference_year
        FROM {GOLD}.rpt_district_affordability
        WHERE municipality = $city AND property_type = 'apartment'
          AND net_income_per_household IS NOT NULL
    """, city=city)
    return medians, barrios, districts


try:
    medians, barrios, districts = load(city)
except Exception as exc:
    st.error("**The price and income query failed.**")
    st.caption(f"Underlying error: {exc}")
    st.stop()

place = city.title()
if pd.isna(medians["sale"]):
    st.info(f"No flats for sale in {place} yet.")
    st.stop()

city_yield = (medians["rent"] * 12 / medians["sale"] * 100
              if pd.notna(medians["rent"]) else None)
buy = districts[(districts["operation_type"] == "sale") & ~districts["low_sample_flag"]]
rent = districts[(districts["operation_type"] == "rent") & ~districts["low_sample_flag"]]

# ── Four numbers ──────────────────────────────────────────────────────────────
m1, m2, m3, m4 = st.columns(4)
m1.metric("Gross rental yield", f"{city_yield:.1f}%" if city_yield else "—",
          help="A year's asking rent as a share of the asking price, per m², city "
               "median. Before costs and tax. The lower it is, the further prices "
               "have run ahead of what flats earn.")
m2.metric("Years of local income to buy",
          f"{buy['years_of_household_income'].median():.1f}" if not buy.empty else "—",
          help="The median flat's asking price ÷ the median household's net income "
               f"in its district, median across districts with {MIN_LISTINGS}+ listings.")
m3.metric("Rent as a share of local income",
          f"{rent['rent_pct_of_household_income'].median():.0f}%" if not rent.empty
          else "—",
          help="The median asking rent × 12 ÷ the median household's net income, "
               f"median across districts with {MIN_LISTINGS}+ rentals.")
if not rent.empty:
    over = int((rent["rent_pct_of_household_income"] > OVERBURDEN_PCT).sum())
    m4.metric(f"Districts where rent tops {OVERBURDEN_PCT:.0f}%", f"{over} of {len(rent)}",
              help=f"Above {OVERBURDEN_PCT:.0f}% of income is what Eurostat and INE "
                   "call housing-cost overburden.")
else:
    m4.metric(f"Districts where rent tops {OVERBURDEN_PCT:.0f}%", "—")

st.divider()

left, right = st.columns([3, 2], gap="large")

with left:
    st.markdown("#### Is the price backed by rents?")
    if barrios.empty or city_yield is None:
        st.info(f"No barrio in {place} has {MIN_LISTINGS}+ flats both for sale and for "
                "rent yet, so no yield can be drawn.")
    else:
        altair_chart(scatter_price_vs_yield(barrios, float(medians["sale"]), city_yield))
        st.caption(f"Each dot is a barrio with {MIN_LISTINGS}+ flats for sale and "
                   f"{MIN_LISTINGS}+ for rent. Dashed lines: {place}. Low and to the "
                   "right, the price has run ahead of what the flat rents for.")

with right:
    st.markdown("#### Against what residents earn")
    if buy.empty and rent.empty:
        st.info(f"No official income figures for {place}'s districts yet — the "
                "district mapping exists for València only.")
    else:
        tab_buy, tab_rent = st.tabs(["Years to buy", "Share of income to rent"])
        with tab_buy:
            if buy.empty:
                st.info("Not enough flats for sale per district yet.")
            else:
                ref = float(buy["years_of_household_income"].median())
                altair_chart(bar_district_burden(
                    buy, "years_of_household_income", ref, "Years of income", ".1f",
                    axis_fmt=".0f"))
                st.caption(f"Years of the district's median household income to buy "
                           f"its median flat outright. Line: {place}, {ref:.1f} years.")
        with tab_rent:
            if rent.empty:
                st.info("Not enough rentals per district yet.")
            else:
                altair_chart(bar_district_burden(
                    rent.assign(share=rent["rent_pct_of_household_income"] / 100),
                    "share", OVERBURDEN_PCT / 100, "Share of income", ".0%"))
                st.caption(f"The median rent as a share of the district's median "
                           f"household income. Line: the {OVERBURDEN_PCT:.0f}% "
                           "overburden threshold.")

# ── The detail ────────────────────────────────────────────────────────────────
with st.expander("The numbers behind it"):
    if not districts.empty:
        wide = (
            districts.pivot_table(
                index=["district", "net_income_per_household"],
                columns="operation_type",
                values=["median_price_eur", "listings", "years_of_household_income",
                        "rent_pct_of_household_income"],
                aggfunc="first",
            )
        )
        wide.columns = [f"{a}_{b}" for a, b in wide.columns]
        wide = wide.reset_index()
        cols = ["district", "net_income_per_household", "median_price_eur_sale",
                "years_of_household_income_sale", "median_price_eur_rent",
                "rent_pct_of_household_income_rent", "listings_sale", "listings_rent"]
        wide = wide.reindex(columns=cols)
        st.dataframe(
            wide.assign(district=wide["district"].str.title())
                .sort_values("years_of_household_income_sale", ascending=False),
            width="stretch", hide_index=True,
            column_config={
                "district": st.column_config.TextColumn("District", pinned=True),
                "net_income_per_household": st.column_config.NumberColumn(
                    "Household income", format="€%,d", help="Net, per year."),
                "median_price_eur_sale": st.column_config.NumberColumn(
                    "Median price", format="€%,d"),
                "years_of_household_income_sale": st.column_config.NumberColumn(
                    "Years to buy", format="%.1f"),
                "median_price_eur_rent": st.column_config.NumberColumn(
                    "Median rent", format="€%,d", help="A month."),
                "rent_pct_of_household_income_rent": st.column_config.NumberColumn(
                    "Rent / income", format="%.0f%%"),
                "listings_sale": st.column_config.NumberColumn("For sale", format="%d"),
                "listings_rent": st.column_config.NumberColumn("For rent", format="%d"),
            },
        )
    if not barrios.empty:
        st.dataframe(
            barrios.assign(area=barrios["neighborhood"].str.title())[[
                "area", "sale_ppsqm", "rent_ppsqm", "yield_pct",
                "total_listings_sale", "total_listings_rent",
            ]].sort_values("yield_pct"),
            width="stretch", hide_index=True,
            column_config={
                "area": st.column_config.TextColumn("Barrio", pinned=True),
                "sale_ppsqm": st.column_config.NumberColumn("Buy €/m²", format="€%,d"),
                "rent_ppsqm": st.column_config.NumberColumn("Rent €/m²/mo",
                                                            format="€%.1f"),
                "yield_pct": st.column_config.NumberColumn("Gross yield",
                                                           format="%.1f%%"),
                "total_listings_sale": st.column_config.NumberColumn("For sale",
                                                                     format="%d"),
                "total_listings_rent": st.column_config.NumberColumn("For rent",
                                                                     format="%d"),
            },
        )

if not districts.empty:
    year = int(districts["income_reference_year"].max())
    st.caption(f"Prices: today's asking prices. Income: INE household income atlas, "
               f"{year} — the latest published, so the ratios mix two dates and read "
               "as a direction, not an exact multiple.")
