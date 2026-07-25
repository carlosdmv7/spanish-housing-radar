"""
Chart builders — Altair only.

Every function returns an `alt.Chart`; the caller renders it with
`theme.altair_chart()`, which is what actually applies the brand theme. Colour,
fonts, gridlines and axis furniture come from the registered Altair theme, so
these builders set colour **only** where the encoding carries meaning (deal tier,
affordability, principal vs interest) and never for decoration.
"""
from __future__ import annotations

import altair as alt
from config import DEAL_TIER_COLORS, DEAL_TIER_LABELS
import pandas as pd
from theme import BORDER, INK_MUTED, RUST_500, RUST_900, TEAL_700

# Ordered tier axis, shared by the scatter and any other tier-coloured encoding,
# so the legend reads best-deal-first and matches the map's colours.
_TIER_KEYS = list(DEAL_TIER_LABELS.keys())
_TIER_DOMAIN = [DEAL_TIER_LABELS[k] for k in _TIER_KEYS]
_TIER_RANGE = [DEAL_TIER_COLORS[k] for k in _TIER_KEYS]
TIER_SCALE = alt.Scale(domain=_TIER_DOMAIN, range=_TIER_RANGE)


def _row_height(n: int, per_row: int = 24, minimum: int = 320) -> int:
    """Horizontal bar charts must grow with their categories, not squeeze."""
    return max(minimum, per_row * n)


def bar_deal_tiers(df: pd.DataFrame) -> alt.Chart:
    """How the current result set splits across the five deal tiers."""
    counts = (
        df["deal_tier"].value_counts()
        .reindex(_TIER_KEYS).fillna(0).astype(int)
        .rename(index=DEAL_TIER_LABELS)
        .rename_axis("tier").reset_index(name="listings")
    )
    return (
        alt.Chart(counts)
        .mark_bar()
        .encode(
            x=alt.X("listings:Q", title="Listings"),
            y=alt.Y("tier:N", title=None, sort=_TIER_DOMAIN),
            color=alt.Color("tier:N", scale=TIER_SCALE, legend=None),
            tooltip=[alt.Tooltip("tier:N", title="Tier"),
                     alt.Tooltip("listings:Q", title="Listings", format=",")],
        )
        .properties(height=_row_height(len(counts), per_row=34, minimum=180))
    )


def bar_ppsqm_with_range(df: pd.DataFrame, top_n: int = 18) -> alt.LayerChart:
    """
    Median €/m² per neighbourhood with a P25–P75 whisker, so the reader sees both
    the typical price and how much it varies — a median alone hides a wide spread.
    """
    d = df.nlargest(top_n, "median_ppsqm").copy()
    d["area"] = d["neighborhood"].str.title()

    base = alt.Chart(d).encode(
        y=alt.Y("area:N", title=None, sort="-x"),
    )
    bars = base.mark_bar().encode(
        x=alt.X("median_ppsqm:Q", title="€/m²"),
        tooltip=[
            alt.Tooltip("area:N", title="Neighbourhood"),
            alt.Tooltip("median_ppsqm:Q", title="Median €/m²", format=",.0f"),
            alt.Tooltip("p25_ppsqm:Q", title="P25", format=",.0f"),
            alt.Tooltip("p75_ppsqm:Q", title="P75", format=",.0f"),
            alt.Tooltip("total_listings:Q", title="Listings"),
        ],
    )
    spread = base.mark_rule(stroke=INK_MUTED, strokeWidth=1.4, opacity=0.8).encode(
        x="p25_ppsqm:Q", x2="p75_ppsqm:Q",
    )
    return (
        (bars + spread)
        .properties(
            height=_row_height(len(d)),
            title=alt.Title(
                "Median €/m² by neighbourhood",
                subtitle="Whisker spans the P25–P75 spread of listings in the area",
            ),
        )
    )


def line_price_history(df: pd.DataFrame) -> alt.Chart:
    """Median €/m² over time, one line per neighbourhood."""
    d = df.copy()
    d["area"] = d["neighborhood"].str.title()
    return (
        alt.Chart(d)
        .mark_line(point=True)
        .encode(
            x=alt.X("scraped_date:T", title=None),
            y=alt.Y("median_ppsqm:Q", title="€/m²", scale=alt.Scale(zero=False)),
            color=alt.Color("area:N", title="Neighbourhood"),
            tooltip=[
                alt.Tooltip("area:N", title="Neighbourhood"),
                alt.Tooltip("scraped_date:T", title="Date"),
                alt.Tooltip("median_ppsqm:Q", title="€/m²", format=",.0f"),
            ],
        )
        .properties(title="Median €/m² over time")
    )


def scatter_size_vs_price(df: pd.DataFrame) -> alt.Chart:
    """Size vs price, coloured by deal tier — cheap-for-their-size flats sit low."""
    d = df.copy()
    d["tier"] = d["deal_tier"].map(DEAL_TIER_LABELS).fillna(d["deal_tier"])
    d["area"] = d["neighborhood"].str.title()
    return (
        alt.Chart(d)
        .mark_circle(size=70, opacity=0.75)
        .encode(
            x=alt.X("size_sqm:Q", title="Size (m²)", scale=alt.Scale(zero=False)),
            y=alt.Y("price_eur:Q", title="Price (€)", scale=alt.Scale(zero=False)),
            color=alt.Color("tier:N", title="Deal tier", scale=TIER_SCALE,
                            sort=_TIER_DOMAIN),
            tooltip=[
                alt.Tooltip("area:N", title="Neighbourhood"),
                alt.Tooltip("price_eur:Q", title="Price €", format=",.0f"),
                alt.Tooltip("size_sqm:Q", title="m²", format=".0f"),
                alt.Tooltip("price_per_sqm:Q", title="€/m²", format=",.0f"),
                alt.Tooltip("opportunity_score:Q", title="Score", format=".0f"),
            ],
        )
        .properties(height=420)
        .interactive()
    )


def bar_mortgage_cost(result) -> alt.Chart:
    """
    What the loan actually costs: principal against interest, stacked to the
    total paid. A waterfall said the same thing with more ink.
    """
    d = pd.DataFrame([
        {"part": "Principal", "eur": result.principal},
        {"part": "Interest", "eur": result.total_interest},
    ])
    d["share"] = d["eur"] / d["eur"].sum()
    return (
        alt.Chart(d)
        .mark_bar()
        .encode(
            x=alt.X("eur:Q", title="€", stack="zero"),
            y=alt.Y("part:N", title=None, sort=["Principal", "Interest"]),
            color=alt.Color(
                "part:N", title=None,
                scale=alt.Scale(domain=["Principal", "Interest"],
                                range=[TEAL_700, RUST_500]),
                legend=None,
            ),
            tooltip=[
                alt.Tooltip("part:N", title=None),
                alt.Tooltip("eur:Q", title="€", format=",.0f"),
                alt.Tooltip("share:Q", title="Share of total", format=".1%"),
            ],
        )
        .properties(
            height=180,
            title=alt.Title(
                "Total cost of the loan",
                subtitle=f"€{result.total_paid:,.0f} paid over the full term",
            ),
        )
    )


def bar_amortisation(schedule: list[dict]) -> alt.Chart:
    """Yearly split of each payment between interest and principal repaid."""
    agg = (
        pd.DataFrame(schedule)
        .groupby("year", as_index=False)
        .agg(Interest=("interest", "sum"), **{"Principal repaid": ("amortisation", "sum")})
        .melt(id_vars="year", var_name="part", value_name="eur")
    )
    return (
        alt.Chart(agg)
        .mark_bar()
        .encode(
            x=alt.X("year:O", title="Year", axis=alt.Axis(labelAngle=0)),
            y=alt.Y("eur:Q", title="€", stack="zero"),
            color=alt.Color(
                "part:N", title=None,
                scale=alt.Scale(domain=["Principal repaid", "Interest"],
                                range=[TEAL_700, RUST_500]),
            ),
            tooltip=[
                alt.Tooltip("year:O", title="Year"),
                alt.Tooltip("part:N", title=None),
                alt.Tooltip("eur:Q", title="€", format=",.0f"),
            ],
        )
        .properties(title="Where each year's payments go")
    )


def bar_required_income(hood_stats: pd.DataFrame, net_income: float) -> alt.LayerChart:
    """
    Income needed per neighbourhood, with the user's own income as a rule — the
    comparison the page exists to make, so it belongs in the chart, not a caption.
    """
    d = hood_stats.copy()
    d["area"] = d["neighborhood"].str.title()
    d["verdict"] = d["affordable"].map({True: "Within reach", False: "Out of reach"})

    bars = (
        alt.Chart(d)
        .mark_bar()
        .encode(
            x=alt.X("required_income:Q", title="Net income needed (€/month)"),
            y=alt.Y("area:N", title=None, sort="x"),
            color=alt.Color(
                "verdict:N", title=None,
                scale=alt.Scale(domain=["Within reach", "Out of reach"],
                                range=[TEAL_700, RUST_500]),
            ),
            tooltip=[
                alt.Tooltip("area:N", title="Neighbourhood"),
                alt.Tooltip("required_income:Q", title="Income needed €/mo", format=",.0f"),
                alt.Tooltip("median_price:Q", title="Median price €", format=",.0f"),
                alt.Tooltip("listings:Q", title="Listings"),
            ],
        )
    )
    yours = (
        alt.Chart(pd.DataFrame({"x": [net_income]}))
        .mark_rule(stroke=RUST_900, strokeWidth=2, strokeDash=[4, 3])
        .encode(x="x:Q", tooltip=alt.Tooltip("x:Q", title="Your income", format=",.0f"))
    )
    return (
        (bars + yours)
        .properties(
            height=_row_height(len(d)),
            title=alt.Title(
                "Minimum income by neighbourhood",
                subtitle=f"Dashed line: your €{net_income:,.0f}/month",
            ),
        )
    )


def bar_years_of_salary(hood_stats: pd.DataFrame) -> alt.Chart:
    """Median price expressed in years of net salary — the affordability gut check."""
    d = hood_stats.copy()
    d["area"] = d["neighborhood"].str.title()
    return (
        alt.Chart(d)
        .mark_bar()
        .encode(
            x=alt.X("years_of_salary:Q", title="Years of net salary"),
            y=alt.Y("area:N", title=None, sort="x"),
            # Sequential ramp: more years = deeper rust. Ordered magnitude, so a
            # categorical scale would be the wrong encoding here.
            color=alt.Color("years_of_salary:Q", title="Years", legend=None),
            tooltip=[
                alt.Tooltip("area:N", title="Neighbourhood"),
                alt.Tooltip("years_of_salary:Q", title="Years of salary", format=".1f"),
                alt.Tooltip("median_price:Q", title="Median price €", format=",.0f"),
            ],
        )
        .properties(
            height=_row_height(len(d)),
            title=alt.Title("Years of salary needed",
                            subtitle="Median price ÷ annual net salary"),
        )
    )


def bar_buy_vs_rent(merged: pd.DataFrame) -> alt.Chart:
    """Monthly mortgage against median rent, per neighbourhood, side by side."""
    d = merged.copy()
    d["area"] = d["neighborhood"].str.title()
    long = d.melt(
        id_vars="area",
        value_vars=["monthly_mortgage", "median_rent"],
        var_name="kind", value_name="eur",
    )
    long["kind"] = long["kind"].map({
        "monthly_mortgage": "Monthly mortgage",
        "median_rent": "Median rent",
    })
    return (
        alt.Chart(long)
        .mark_bar()
        .encode(
            x=alt.X("eur:Q", title="€ / month"),
            y=alt.Y("area:N", title=None, sort="-x"),
            yOffset=alt.YOffset("kind:N", sort=["Monthly mortgage", "Median rent"]),
            color=alt.Color(
                "kind:N", title=None,
                scale=alt.Scale(domain=["Monthly mortgage", "Median rent"],
                                range=[RUST_500, TEAL_700]),
            ),
            tooltip=[
                alt.Tooltip("area:N", title="Neighbourhood"),
                alt.Tooltip("kind:N", title=None),
                alt.Tooltip("eur:Q", title="€/month", format=",.0f"),
            ],
        )
        .properties(
            height=_row_height(len(d), per_row=42),
            title=alt.Title(
                "Buying vs renting the same neighbourhood",
                subtitle="Mortgage payment at your terms against the median asking rent",
            ),
        )
    )


def bar_benchmark_grain(counts: pd.DataFrame) -> alt.Chart:
    """
    Share of listings scored at each benchmark grain. The headline data-quality
    chart: a tall city bar means most scores rest on a coarse comparison.
    """
    order = ["neighbourhood", "district", "city"]
    return (
        alt.Chart(counts)
        .mark_bar()
        .encode(
            x=alt.X("listings:Q", title="Listings"),
            y=alt.Y("benchmark_level:N", title=None, sort=order),
            color=alt.Color(
                "benchmark_level:N", legend=None,
                scale=alt.Scale(domain=order, range=[TEAL_700, "#7FB3A4", BORDER]),
            ),
            tooltip=[
                alt.Tooltip("benchmark_level:N", title="Scored against"),
                alt.Tooltip("listings:Q", title="Listings", format=","),
                alt.Tooltip("share:Q", title="Share", format=".1%"),
            ],
        )
        .properties(height=180)
    )
