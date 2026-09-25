"""
Neighbourhoods — what a m² costs, barrio by barrio, and where prices are heading.

Two sources, kept visibly apart because they answer different questions:

* Scraped asking prices are the only data at barrio grain. They are drawn only
  where a barrio has enough listings to mean something, as a median with the
  middle half of its listings around it, so a barrio built on four flats never
  looks as solid as one built on forty. The thin ones stay in the table.
* The INE house-price index is transaction-based but regional and quarterly.
  It is the trend line — replacing a per-barrio line drawn from scraped
  snapshots, which mostly traced which flats happened to be listed that week.
"""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from chrome import page_header
from components.charts import dot_barrio_range, line_official_trend
from components.filters import city_picker, load_municipalities
from connection import query
import pandas as pd
import streamlit as st
from theme import altair_chart

# transform/dbt_project.yml → vars.min_comps_for_benchmark: the same bar a barrio
# must clear before the score will use it as a benchmark.
MIN_LISTINGS = 8
GOLD = "spanish_housing_radar.main_gold"
VIEWS = Path(__file__).parent  # absolute page_link targets; see views/home.py

page_header(
    "What does a m² cost, barrio by barrio?",
    "Asking prices for flats in every barrio, and where official prices are heading.",
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

c_op, c_city, _ = st.columns([1.2, 1.4, 3.4], vertical_alignment="bottom")
with c_op:
    op = st.segmented_control(
        "Prices to", ["sale", "rent"], default="sale", required=True,
        format_func=lambda k: {"sale": "Buy", "rent": "Rent"}[k],
    )
with c_city:
    city = city_picker(munis)

MARKET_SQL = (Path(__file__).parent.parent / "queries" / "market.sql").read_text()


@st.cache_data(ttl=600, show_spinner="Loading prices…")
def load_asking(op: str, city: str) -> tuple[pd.Series, pd.DataFrame]:
    summary = query(f"""
        SELECT MEDIAN(price_per_sqm)                          AS median_ppsqm,
               COUNT(*)                                       AS listings,
               COUNT(*) FILTER (WHERE price_dropped)          AS cuts,
               MEDIAN(price_change_pct) FILTER (WHERE price_dropped) AS median_cut,
               MAX(days_on_market)                            AS max_days
        FROM {GOLD}.rpt_opportunities
        WHERE municipality = $city AND operation_type = $op
          AND property_type = 'apartment'
    """, city=city, op=op).iloc[0]
    barrios = query(MARKET_SQL, operation_type=op, municipality=city)
    return summary, barrios[barrios["property_type"] == "apartment"]


@st.cache_data(ttl=3600)
def load_latest(city: str) -> pd.DataFrame:
    return query(f"SELECT * FROM {GOLD}.rpt_market_context WHERE municipality = $city",
                 city=city)


@st.cache_data(ttl=3600)
def load_trend(city: str) -> pd.DataFrame:
    return query(f"""
        SELECT period_date, hpi_index, hpi_yoy_pct
        FROM {GOLD}.rpt_market_trend
        WHERE municipality = $city AND housing_type = 'general'
        ORDER BY period_date
    """, city=city)


def _or_empty(load, city: str) -> pd.DataFrame:
    try:
        return load(city)
    except Exception:
        return pd.DataFrame()


try:
    summary, barrios = load_asking(op, city)
except Exception as exc:
    st.error("**The price query failed.**")
    st.caption(f"Underlying error: {exc}")
    st.stop()

# The INE feed is context, not the page: if it is unavailable the barrios still
# render, and the gap is said out loud rather than left blank.
latest, trend = _or_empty(load_latest, city), _or_empty(load_trend, city)

place = city.title()
rent = op == "rent"
unit = "€/m²/mo" if rent else "€/m²"
money = (lambda v: f"€{v:,.1f}") if rent else (lambda v: f"€{v:,.0f}")

if barrios.empty or pd.isna(summary["median_ppsqm"]):
    st.info(f"No flats {'for rent' if rent else 'for sale'} in {place} yet.")
    st.stop()

solid = barrios[barrios["total_listings"] >= MIN_LISTINGS]
city_median = float(summary["median_ppsqm"])

# ── Four numbers ──────────────────────────────────────────────────────────────
m1, m2, m3, m4 = st.columns(4)
m1.metric("Typical asking rent" if rent else "Typical asking price",
          f"{money(city_median)}{unit[1:]}",
          help=f"Median across {int(summary['listings']):,} flats "
               f"{'for rent' if rent else 'for sale'} in {place}.")

if len(solid) >= 2:
    lo = solid.loc[solid["median_ppsqm"].idxmin()]
    hi = solid.loc[solid["median_ppsqm"].idxmax()]
    m2.metric("Priciest vs cheapest barrio",
              f"{hi['median_ppsqm'] / lo['median_ppsqm']:.1f}×",
              help=f"{hi['neighborhood'].title()} ({money(hi['median_ppsqm'])}) against "
                   f"{lo['neighborhood'].title()} ({money(lo['median_ppsqm'])}), among "
                   f"barrios with {MIN_LISTINGS}+ listings.")
else:
    m2.metric("Priciest vs cheapest barrio", "—",
              help=f"Needs two barrios with {MIN_LISTINGS}+ listings.")

if not latest.empty and pd.notna(latest.iloc[0]["hpi_yoy_general"]):
    row = latest.iloc[0]
    period = pd.Timestamp(row["latest_period"])
    m3.metric("Official prices, last 12 months", f"{row['hpi_yoy_general']:+.1f}%",
              help=f"INE house price index for {str(row['region']).title()}, "
                   f"Q{period.quarter} {period.year} against a year earlier. Prices "
                   "of real sales, not asking prices — and regional, not per barrio.")
else:
    m3.metric("Official prices, last 12 months", "—",
              help="The INE index is unavailable right now.")

if summary["max_days"] and int(summary["max_days"]) > 0:
    cuts = int(summary["cuts"])
    m4.metric("Sellers who cut the price", f"{cuts:,}",
              delta=f"{cuts / int(summary['listings']):.0%} of listings",
              delta_color="off", delta_arrow="off",
              help="Listings whose asking price dropped since the scraper first saw "
                   "them" + (f". Median cut: {summary['median_cut']:.0f}%."
                             if cuts else "."))
else:
    m4.metric("Sellers who cut the price", "—",
              help=f"{place} has been scraped once, so no price has had the chance "
                   "to move yet.")

st.divider()

# ── Barrios · official trend ──────────────────────────────────────────────────
left, right = st.columns([3, 2], gap="large")

with left:
    st.markdown("#### Where each barrio sits")
    if solid.empty:
        st.info(f"No barrio in {place} has {MIN_LISTINGS}+ listings yet, so none is "
                "drawn. The table below has what there is.")
    else:
        altair_chart(dot_barrio_range(solid, city_median, unit))
        thin = len(barrios) - len(solid)
        st.caption(
            f"Dot: the barrio's median. Band: where the middle half of its listings "
            f"sit. Dashed: {place}. Only barrios with {MIN_LISTINGS}+ listings"
            + (f" — {thin} thinner ones are in the table below." if thin else ".")
        )
    st.page_link(str(VIEWS / "01_opportunities.py"), label="See the flats behind these",
                 icon=":material/arrow_forward:")

with right:
    if trend.empty:
        st.markdown("#### Official prices")
        st.info("The INE index is unavailable right now.")
    else:
        first = pd.Timestamp(trend["period_date"].iloc[0])
        last = pd.Timestamp(trend["period_date"].iloc[-1])
        region = str(latest.iloc[0]["region"]).title() if not latest.empty else "the region"
        st.markdown(f"#### Official prices since {first.year}")
        altair_chart(line_official_trend(trend))
        st.caption(
            f"INE house price index for {region}, to Q{last.quarter} {last.year}. "
            "What homes actually sold for, region-wide: the direction of the market, "
            "not a barrio's price."
        )

# ── The detail, for whoever wants it ──────────────────────────────────────────
with st.expander(f"Every barrio in {place}, in numbers"):
    fmt = "€%.1f" if rent else "€%,d"
    st.dataframe(
        barrios.assign(
            area=barrios["neighborhood"].str.title(),
            district_name=barrios["district"].str.title(),
            solid=barrios["total_listings"] >= MIN_LISTINGS,
        )[["area", "district_name", "total_listings", "solid", "median_ppsqm",
           "p25_ppsqm", "p75_ppsqm", "median_size_sqm"]]
        .sort_values("median_ppsqm", ascending=False),
        width="stretch",
        hide_index=True,
        column_config={
            "area": st.column_config.TextColumn("Barrio", pinned=True),
            "district_name": st.column_config.TextColumn("District"),
            "total_listings": st.column_config.NumberColumn("Listings", format="%d"),
            "solid": st.column_config.CheckboxColumn(
                f"{MIN_LISTINGS}+", help="Enough listings to be drawn above and to "
                "serve as a benchmark for the score."),
            "median_ppsqm": st.column_config.NumberColumn(f"Median {unit}", format=fmt),
            "p25_ppsqm": st.column_config.NumberColumn(
                "P25", format=fmt, help="A quarter of listings ask less than this."),
            "p75_ppsqm": st.column_config.NumberColumn(
                "P75", format=fmt, help="A quarter of listings ask more than this."),
            "median_size_sqm": st.column_config.NumberColumn("Typical size",
                                                             format="%.0f m²"),
        },
    )
