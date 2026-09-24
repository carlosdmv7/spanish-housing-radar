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
from theme import BORDER, INK, INK_MUTED, PETROL_900, RUST_500, RUST_700, TEAL_700

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


def scatter_price_vs_yield(df: pd.DataFrame, city_price: float,
                           city_yield: float) -> alt.LayerChart:
    """
    Each barrio's asking €/m² against the gross yield its rents give on that
    price, split by the city's two medians.

    The yield is the question "is the area itself overpriced?" made measurable:
    rent is what a flat is worth to live in, the price is what it costs to own,
    and where the price has run ahead of the rent the yield falls. Bottom right
    is dear *and* poorly backed by rents; top left is cheap and well backed.
    """
    d = df.copy()
    d["area"] = d["neighborhood"].str.title()
    d["reading"] = "Neither"
    d.loc[(d["sale_ppsqm"] >= city_price) & (d["yield_pct"] < city_yield),
          "reading"] = "Price ahead of rent"
    d.loc[(d["sale_ppsqm"] < city_price) & (d["yield_pct"] >= city_yield),
          "reading"] = "Rent backs the price"
    # Only the readings that occur, so the legend never names an empty group.
    readings = {"Rent backs the price": TEAL_700, "Neither": INK_MUTED,
                "Price ahead of rent": RUST_700}
    present = [k for k in readings if (d["reading"] == k).any()]
    scale = alt.Scale(domain=present, range=[readings[k] for k in present])

    # Explicit domains, padded, so the label placement below maps data to the
    # same pixels the chart does — a "nice" domain would move every point.
    xdom = _padded(pd.concat([d["sale_ppsqm"], pd.Series([city_price])]), 0.05)
    ydom = _padded(pd.concat([d["yield_pct"], pd.Series([city_yield])]), 0.08)
    x = alt.X("sale_ppsqm:Q", title="Asking price to buy, €/m²",
              scale=alt.Scale(domain=xdom, nice=False), axis=alt.Axis(format=",.0f"))
    y = alt.Y("yield_pct:Q", title="Gross rental yield",
              scale=alt.Scale(domain=ydom, nice=False),
              axis=alt.Axis(format=".1f", labelExpr="datum.label + '%'"))
    base = alt.Chart(d).encode(x=x, y=y)
    dots = base.mark_circle(size=140, opacity=0.95).encode(
        color=alt.Color("reading:N", scale=scale, title=None,
                        legend=alt.Legend(orient="top", direction="horizontal")),
        tooltip=[
            alt.Tooltip("area:N", title="Barrio"),
            alt.Tooltip("sale_ppsqm:Q", title="Buy, €/m²", format=",.0f"),
            alt.Tooltip("rent_ppsqm:Q", title="Rent, €/m² a month", format=",.1f"),
            alt.Tooltip("yield_pct:Q", title="Gross yield %", format=".1f"),
            alt.Tooltip("listings:Q", title="Listings behind it"),
        ],
    )
    d = _place_labels(d, "sale_ppsqm", "yield_pct", xdom, ydom)
    labels = [
        alt.Chart(d).transform_filter(alt.datum.side == side)
        .mark_text(align=side, dx=dx, baseline="middle", fontSize=11, color=INK)
        .encode(x=x, y=alt.Y("label_y:Q", scale=alt.Scale(domain=ydom, nice=False)),
                text="area:N")
        for side, dx in (("left", 9), ("right", -9), ("center", 0))
    ]
    rules = (
        alt.Chart(pd.DataFrame({"sale_ppsqm": [city_price]}))
        .mark_rule(stroke=INK_MUTED, strokeDash=[4, 3]).encode(x=x)
        + alt.Chart(pd.DataFrame({"yield_pct": [city_yield]}))
        .mark_rule(stroke=INK_MUTED, strokeDash=[4, 3]).encode(y=y)
    )
    return alt.layer(rules, dots, *labels).properties(height=420)


def _padded(values: pd.Series, share: float) -> list[float]:
    lo, hi = float(values.min()), float(values.max())
    pad = (hi - lo) * share or 1.0
    return [lo - pad, hi + pad]


def _place_labels(d: pd.DataFrame, x: str, y: str, xdom: list[float],
                  ydom: list[float], width: int = 620, height: int = 400,
                  char_px: float = 6.6, line_px: int = 13) -> pd.DataFrame:
    """
    Where each point's name goes, so no name overlaps another name or dot and
    none runs off the plot.

    Vega-Lite has no label collision handling, and two barrios a few euros
    apart printed their names on top of each other. This works in approximate
    pixels: each name tries right of its dot, then left, above and below, and
    takes the first spot that clears everything already placed. Approximate is
    enough — exact would need the browser.
    """
    d = d.copy()
    (x0, x1), (y0, y1) = xdom, ydom
    px = (d[x] - x0) / (x1 - x0) * width
    py = (y1 - d[y]) / (y1 - y0) * height
    boxes = [(px[i] - 6, py[i] - 6, px[i] + 6, py[i] + 6) for i in d.index]

    def clear(box):
        l_, t, r, b = box
        inside = l_ >= 0 and r <= width and t >= 0 and b <= height
        return inside and not any(l_ < r2 and r > l2 and t < b2 and b > t2
                                  for l2, t2, r2, b2 in boxes)

    align, offset = {}, {}
    for i in py.sort_values().index:
        w, h = len(str(d.at[i, "area"])) * char_px, line_px
        cx, cy = px[i], py[i]
        candidates = [
            ("left", 0, (cx + 9, cy - h / 2, cx + 9 + w, cy + h / 2)),
            ("right", 0, (cx - 9 - w, cy - h / 2, cx - 9, cy + h / 2)),
            ("center", -h, (cx - w / 2, cy - 1.5 * h, cx + w / 2, cy - h / 2)),
            ("center", h, (cx - w / 2, cy + h / 2, cx + w / 2, cy + 1.5 * h)),
        ]
        side, dy, box = next((c for c in candidates if clear(c[2])), candidates[0])
        boxes.append(box)
        align[i], offset[i] = side, dy
    d["side"] = pd.Series(align)
    d["label_y"] = d[y] - pd.Series(offset) * (y1 - y0) / height
    return d


def bar_district_burden(df: pd.DataFrame, value: str, line: float, line_label: str,
                        fmt: str, axis_fmt: str | None = None) -> alt.LayerChart:
    """
    One bar per district for a housing-cost burden, with a reference line.

    Teal under the line, rust over it — the same reading as every other chart
    in the app: rust is where the price is the problem.
    """
    d = df.copy()
    d["area"] = d["district"].str.title()
    d["over"] = (d[value] > line).map({True: "over", False: "under"})
    base = alt.Chart(d).encode(
        y=alt.Y("area:N", title=None, sort=alt.EncodingSortField(value, order="descending")),
    )
    bars = base.mark_bar(cornerRadiusEnd=3).encode(
        x=alt.X(f"{value}:Q", title=None, axis=alt.Axis(format=axis_fmt or fmt)),
        color=alt.Color("over:N", legend=None,
                        scale=alt.Scale(domain=["under", "over"],
                                        range=[TEAL_700, RUST_500])),
        tooltip=[alt.Tooltip("area:N", title="District"),
                 alt.Tooltip(f"{value}:Q", title=line_label, format=fmt),
                 alt.Tooltip("net_income_per_household:Q",
                             title="Household income €/yr", format=",.0f"),
                 alt.Tooltip("listings:Q", title="Listings behind it")],
    )
    rule = alt.Chart(pd.DataFrame({"x": [line]})).mark_rule(
        stroke=INK, strokeDash=[4, 3], strokeWidth=1.5).encode(x="x:Q")
    return (bars + rule).properties(height=_row_height(len(d), per_row=24, minimum=240))


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
