"""
Reusable Plotly chart wrappers.
All functions return a plotly Figure — caller does st.plotly_chart().
"""
from __future__ import annotations

from config import ACCENT, DEAL_TIER_COLORS
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go


def bar_ppsqm_by_neighborhood(df: pd.DataFrame, title: str = "€/sqm by neighborhood") -> go.Figure:
    df = df.sort_values("median_ppsqm", ascending=True).tail(20)
    fig = px.bar(
        df,
        x="median_ppsqm",
        y="neighborhood",
        orientation="h",
        title=title,
        labels={"median_ppsqm": "€/sqm (median)", "neighborhood": ""},
        color="median_ppsqm",
        color_continuous_scale="Blues",
    )
    fig.update_layout(coloraxis_showscale=False, margin={"l":0, "r":0, "t":40, "b":0})
    return fig


def box_ppsqm_distribution(df: pd.DataFrame) -> go.Figure:
    fig = px.box(
        df,
        x="neighborhood",
        y="price_per_sqm",
        title="€/sqm distribution by neighborhood",
        labels={"price_per_sqm": "€/sqm", "neighborhood": ""},
        color_discrete_sequence=[ACCENT],
    )
    fig.update_layout(margin={"l":0, "r":0, "t":40, "b":0})
    return fig


def line_price_history(df: pd.DataFrame) -> go.Figure:
    fig = px.line(
        df,
        x="scraped_date",
        y="median_ppsqm",
        color="neighborhood",
        title="€/sqm evolution (median)",
        labels={"scraped_date": "", "median_ppsqm": "€/sqm", "neighborhood": "Neighborhood"},
        markers=True,
    )
    fig.update_layout(margin={"l":0, "r":0, "t":40, "b":0})
    return fig


def scatter_size_vs_price(df: pd.DataFrame) -> go.Figure:
    fig = px.scatter(
        df,
        x="size_sqm",
        y="price_eur",
        color="deal_tier",
        color_discrete_map=DEAL_TIER_COLORS,
        hover_data=["neighborhood", "rooms", "price_per_sqm"],
        title="Size vs Price",
        labels={"size_sqm": "sqm", "price_eur": "Price (€)"},
        opacity=0.7,
    )
    fig.update_layout(margin={"l":0, "r":0, "t":40, "b":0})
    return fig


def waterfall_mortgage(result) -> go.Figure:
    fig = go.Figure(go.Waterfall(
        orientation="v",
        measure=["relative", "relative", "total"],
        x=["Principal", "Total interest", "Total paid"],
        y=[result.principal, result.total_interest, 0],
        connector={"line": {"color": "#94a3b8"}},
        decreasing={"marker": {"color": "#22c55e"}},
        increasing={"marker": {"color": "#ef4444"}},
        totals={"marker": {"color": ACCENT}},
    ))
    fig.update_layout(
        title="Total cost breakdown",
        showlegend=False,
        margin={"l":0, "r":0, "t":40, "b":0},
    )
    return fig


def line_amortisation(schedule: list[dict]) -> go.Figure:
    df  = pd.DataFrame(schedule)
    agg = df.groupby("year").agg(
        interest=("interest", "sum"),
        amortisation=("amortisation", "sum"),
    ).reset_index()

    fig = go.Figure()
    fig.add_trace(go.Bar(name="Principal repaid", x=agg["year"], y=agg["amortisation"], marker_color=ACCENT))
    fig.add_trace(go.Bar(name="Interest",         x=agg["year"], y=agg["interest"],     marker_color="#f97316"))
    fig.update_layout(
        barmode="stack",
        title="Annual payment: principal vs interest",
        xaxis_title="Year",
        yaxis_title="€",
        margin={"l":0, "r":0, "t":40, "b":0},
    )
    return fig
