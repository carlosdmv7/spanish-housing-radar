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
from theme import BORDER, INK, INK_MUTED, PETROL_900, RUST_500, RUST_900, TEAL_700

# Ordered tier axis, shared by the scatter and any other tier-coloured encoding,
# so the legend reads best-deal-first and matches the map's colours.
_TIER_KEYS = list(DEAL_TIER_LABELS.keys())
_TIER_DOMAIN = [DEAL_TIER_LABELS[k] for k in _TIER_KEYS]
_TIER_RANGE = [DEAL_TIER_COLORS[k] for k in _TIER_KEYS]
TIER_SCALE = alt.Scale(domain=_TIER_DOMAIN, range=_TIER_RANGE)


def _row_height(n: int, per_row: int = 24, minimum: int = 320) -> int:
    """Horizontal bar charts must grow with their categories, not squeeze."""
    return max(minimum, per_row * n)


def strip_deal_tiers(df: pd.DataFrame) -> alt.Chart:
    """
    One horizontal band, split by deal tier, cheapest-for-its-area on the left.

    No text inside the band. White labels were illegible on the amber and
    rust-500 segments — the brand allows white only on the 700-weight fills —
    and the "great deal" segment is usually too narrow to hold its own count,
    which is the one number a visitor wants. The caller prints a legend with
    every count underneath instead (`tier_legend`).
    """
    counts = (
        df["deal_tier"].value_counts()
        .reindex(_TIER_KEYS).fillna(0).astype(int)
        .rename(index=DEAL_TIER_LABELS)
        .rename_axis("tier").reset_index(name="listings")
    )
    counts["order"] = counts["tier"].map({t: i for i, t in enumerate(_TIER_DOMAIN)})
    return (
        alt.Chart(counts[counts["listings"] > 0])
        .mark_bar(height=22, cornerRadius=0)
        .encode(
            x=alt.X("listings:Q", stack="normalize", axis=None),
            order=alt.Order("order:Q"),
            color=alt.Color("tier:N", scale=TIER_SCALE, legend=None),
            tooltip=[alt.Tooltip("tier:N", title="Tier"),
                     alt.Tooltip("listings:Q", title="Listings")],
        )
        .properties(height=26)
    )


def tier_legend(df: pd.DataFrame) -> str:
    """The band's key, with a count per tier, as one line of native markdown."""
    counts = df["deal_tier"].value_counts()
    return "  ".join(
        f":color[●]{{foreground=\"{DEAL_TIER_COLORS[k]}\"}} {DEAL_TIER_LABELS[k]} "
        f"**{int(counts.get(k, 0))}**"
        for k in _TIER_KEYS
    )


def bar_flat_vs_area(ppsqm: float, bench: float, bench_label: str) -> alt.Chart:
    """This flat's €/m² against the benchmark it was scored on — two bars, no more."""
    d = pd.DataFrame({
        "what": ["This flat", bench_label],
        "ppsqm": [ppsqm, bench],
        "tone": ["flat", "bench"],
    })
    return (
        alt.Chart(d)
        .mark_bar(cornerRadiusEnd=3, height=18)
        .encode(
            y=alt.Y("what:N", title=None, sort=["This flat", bench_label]),
            x=alt.X("ppsqm:Q", title=None, axis=alt.Axis(format=",.0f", tickCount=3)),
            color=alt.Color(
                "tone:N", legend=None,
                scale=alt.Scale(domain=["flat", "bench"],
                                range=[TEAL_700 if ppsqm <= bench else RUST_500, INK_MUTED]),
            ),
            tooltip=[alt.Tooltip("what:N", title=""),
                     alt.Tooltip("ppsqm:Q", title="€/m²", format=",.0f")],
        )
        .properties(height=70)
    )


def bar_barrio_ppsqm(df: pd.DataFrame, city_median: float) -> alt.LayerChart:
    """
    Median asking €/m² per barrio, cheapest to dearest, against the city median.

    Only barrios the caller has already filtered to a reliable sample should reach
    this. Bars run from the city median rather than from zero because the story
    is the gap — "this barrio asks 30% under the city" — and a bar from zero makes
    €3,100 and €3,700 look nearly the same.
    """
    d = df.copy()
    d["area"] = d["neighborhood"].str.title()
    d["city_median"] = city_median
    d["side"] = (d["median_ppsqm"] >= city_median).map({True: "above", False: "below"})

    base = alt.Chart(d).encode(
        y=alt.Y("area:N", title=None, sort=alt.EncodingSortField("median_ppsqm")),
    )
    bars = base.mark_bar(cornerRadiusEnd=3).encode(
        x=alt.X("median_ppsqm:Q", title="Median asking €/m²",
                scale=alt.Scale(zero=False), axis=alt.Axis(format=",.0f")),
        x2="city_median:Q",
        color=alt.Color(
            "side:N", legend=None,
            scale=alt.Scale(domain=["below", "above"], range=[TEAL_700, RUST_500]),
        ),
        tooltip=[
            alt.Tooltip("area:N", title="Barrio"),
            alt.Tooltip("median_ppsqm:Q", title="Median €/m²", format=",.0f"),
            alt.Tooltip("listings:Q", title="Listings behind it"),
        ],
    )
    rule = alt.Chart(pd.DataFrame({"x": [city_median]})).mark_rule(
        stroke=INK_MUTED, strokeDash=[4, 3],
    ).encode(x="x:Q")
    return (bars + rule).properties(height=_row_height(len(d), per_row=22, minimum=260))


def dot_barrio_range(df: pd.DataFrame, city_median: float, unit: str) -> alt.LayerChart:
    """
    Each barrio as a dot on its median, with a band over the middle half of its
    listings (P25–P75), against the city median.

    Replaces a bar per barrio. A bar says "this is the price"; the band says
    "most flats here ask between these two", which is the honest reading of a
    median of a dozen asking prices — and it shows at a glance when two barrios
    whose medians differ are really the same market.
    """
    d = df.copy()
    d["area"] = d["neighborhood"].str.title()
    d["side"] = (d["median_ppsqm"] >= city_median).map({True: "above", False: "below"})
    fmt = ",.1f" if unit.endswith("/mo") else ",.0f"

    base = alt.Chart(d).encode(
        y=alt.Y("area:N", title=None, sort=alt.EncodingSortField("median_ppsqm")),
        tooltip=[
            alt.Tooltip("area:N", title="Barrio"),
            alt.Tooltip("median_ppsqm:Q", title=f"Median {unit}", format=fmt),
            alt.Tooltip("p25_ppsqm:Q", title="Cheaper quarter below", format=fmt),
            alt.Tooltip("p75_ppsqm:Q", title="Dearer quarter above", format=fmt),
            alt.Tooltip("total_listings:Q", title="Listings behind it"),
        ],
    )
    band = base.mark_bar(height=8, cornerRadius=4, color=INK_MUTED, opacity=0.28).encode(
        x=alt.X("p25_ppsqm:Q", title=unit, scale=alt.Scale(zero=False),
                axis=alt.Axis(format=fmt)),
        x2="p75_ppsqm:Q",
    )
    dots = base.mark_circle(size=110, opacity=1).encode(
        x="median_ppsqm:Q",
        color=alt.Color(
            "side:N", legend=None,
            scale=alt.Scale(domain=["below", "above"], range=[TEAL_700, RUST_500]),
        ),
    )
    rule = alt.Chart(pd.DataFrame({"x": [city_median]})).mark_rule(
        stroke=INK_MUTED, strokeDash=[4, 3],
    ).encode(x="x:Q")
    return (band + rule + dots).properties(
        height=_row_height(len(d), per_row=24, minimum=260))


def line_official_trend(df: pd.DataFrame) -> alt.LayerChart:
    """
    The INE index as the change since the first quarter shown, with the latest
    quarter labelled.

    Rebased because "index 111.7, base 2025" means nothing to a buyer, whereas
    "+37% since 2021" is the sentence they would say out loud.
    """
    d = df.sort_values("period_date").copy()
    d["change"] = d["hpi_index"] / d["hpi_index"].iloc[0] - 1
    d["quarter"] = (pd.to_datetime(d["period_date"]).dt.year.astype(str) + " Q"
                    + pd.to_datetime(d["period_date"]).dt.quarter.astype(str))
    last = d.tail(1)

    line = alt.Chart(d).mark_line(color=PETROL_900, strokeWidth=2.5).encode(
        x=alt.X("period_date:T", title=None, axis=alt.Axis(format="%Y", tickCount="year")),
        y=alt.Y("change:Q", title=None, axis=alt.Axis(format="+.0%")),
        tooltip=[alt.Tooltip("quarter:N", title="Quarter"),
                 alt.Tooltip("change:Q", title="Since start", format="+.1%"),
                 alt.Tooltip("hpi_yoy_pct:Q", title="Year on year %", format="+.1f")],
    )
    dot = alt.Chart(last).mark_circle(size=80, color=PETROL_900).encode(
        x="period_date:T", y="change:Q")
    label = alt.Chart(last).mark_text(
        align="right", dx=-8, dy=-12, fontWeight="bold", color=PETROL_900,
    ).encode(x="period_date:T", y="change:Q",
             text=alt.Text("change:Q", format="+.0%"))
    return (line + dot + label).properties(height=260)


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


def bar_signing_day(items: pd.DataFrame) -> alt.LayerChart:
    """
    Signing-day cash, one bar per item, coloured by whether it stays yours.

    The deposit becomes equity; tax and fees buy nothing that can be sold. That
    distinction is the whole reason first-time buyers get the number wrong, so
    it is the colour rather than a footnote.
    """
    d = items[items["eur"] > 0].sort_values("eur", ascending=False).copy()
    d["kind"] = d["item"].eq("Deposit").map({True: "Stays yours",
                                             False: "Gone on the day"})
    d["label"] = d["eur"].map(lambda v: f"€{v:,.0f}")
    base = alt.Chart(d).encode(
        # An explicit order: a sort field on a layered chart falls back to
        # alphabetical, which put Appraisal on top of a €36,000 deposit.
        y=alt.Y("item:N", title=None, sort=list(d["item"])),
        x=alt.X("eur:Q", title=None, axis=alt.Axis(format="~s", labelExpr="'€' + datum.label")),
    )
    bars = base.mark_bar(cornerRadiusEnd=3, height=20).encode(
        color=alt.Color("kind:N", title=None,
                        scale=alt.Scale(domain=["Stays yours", "Gone on the day"],
                                        range=[TEAL_700, RUST_500]),
                        legend=alt.Legend(orient="top", direction="horizontal")),
        tooltip=[alt.Tooltip("item:N", title=None),
                 alt.Tooltip("eur:Q", title="€", format=",.0f"),
                 alt.Tooltip("note:N", title="What it is")],
    )
    labels = base.mark_text(align="left", dx=5, color=INK, fontSize=12).encode(
        text="label:N")
    return (bars + labels).properties(height=_row_height(len(d), per_row=34, minimum=150))


def line_buy_vs_rent(series: pd.DataFrame, breakeven: int | None) -> alt.LayerChart:
    """
    Net worth year by year down each path, so the reader sees *when* buying
    starts to pay rather than a verdict for one horizon they had to pick.
    """
    long = series.melt(id_vars="year", value_vars=["Buy", "Rent and invest"],
                       var_name="path", value_name="eur")
    scale = alt.Scale(domain=["Buy", "Rent and invest"], range=[PETROL_900, RUST_500])
    lines = alt.Chart(long).mark_line(strokeWidth=2.5).encode(
        x=alt.X("year:Q", title="Years after buying", axis=alt.Axis(format="d")),
        y=alt.Y("eur:Q", title=None,
                axis=alt.Axis(format="~s", labelExpr="'€' + datum.label")),
        color=alt.Color("path:N", title=None, scale=scale,
                        legend=alt.Legend(orient="top", direction="horizontal")),
        tooltip=[alt.Tooltip("year:Q", title="Year"),
                 alt.Tooltip("path:N", title=None),
                 alt.Tooltip("eur:Q", title="Net worth €", format=",.0f")],
    )
    layers = [lines]
    if breakeven is not None:
        layers.append(
            alt.Chart(pd.DataFrame({"x": [breakeven]}))
            .mark_rule(stroke=INK_MUTED, strokeDash=[4, 3]).encode(x="x:Q")
        )
    return alt.layer(*layers).properties(height=300)
