"""
Mortgage — fixed vs variable, French amortisation schedule, affordability check.
"""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from components.charts import bar_amortisation, bar_mortgage_cost
from components.mortgage import (
    compute_mortgage,
    compute_variable_mortgage,
    max_affordable_loan,
    required_income,
)
from config import (
    AFFORDABILITY_RATIO_MAX,
    EURIBOR_CURRENT,
    MORTGAGE_DEFAULT_LTV,
    MORTGAGE_DEFAULT_RATE_FIXED,
    MORTGAGE_DEFAULT_RATE_VARIABLE,
    MORTGAGE_DEFAULT_YEARS,
    MORTGAGE_SOURCE_NOTE,
)
import pandas as pd
import streamlit as st
from theme import RUST_700, TEAL_700, altair_chart, page_hero, section

page_hero(
    "🧮",
    "Mortgage Calculator",
    "Compare fixed against variable with a full French amortisation schedule and a "
    "rate-rise stress scenario. Indicative maths, not an offer.",
)

# Every prefilled rate on this page is a published figure with a citation, and
# the visitor sees that before the first payment number — same contract as the
# freshness header: state the data's provenance ahead of any figure drawn from it.
st.caption(MORTGAGE_SOURCE_NOTE)

col_in, col_out = st.columns([1, 2])

# ── Inputs ────────────────────────────────────────────────────────────────────
with col_in:
    section("Property")
    property_price = st.number_input(
        "Property price (€)", min_value=50_000, max_value=5_000_000,
        value=350_000, step=5_000, format="%d",
    )
    ltv = st.slider("LTV — % financed", min_value=50, max_value=100,
                    value=int(MORTGAGE_DEFAULT_LTV))
    down_payment = property_price * (1 - ltv / 100)
    principal = property_price * ltv / 100

    d1, d2 = st.columns(2)
    d1.metric("Down payment", f"€{down_payment:,.0f}")
    d2.metric("Loan", f"€{principal:,.0f}")

    section("Terms")
    years = st.slider("Term (years)", 5, 40, MORTGAGE_DEFAULT_YEARS)
    fixed_rate = st.number_input(
        "Fixed rate (%)", min_value=0.1, max_value=15.0,
        value=MORTGAGE_DEFAULT_RATE_FIXED, step=0.05, format="%.2f",
    )

    section("Variable rate")
    euribor = st.number_input(
        "Euribor 12m (%)", min_value=-2.0, max_value=10.0,
        value=EURIBOR_CURRENT, step=0.05, format="%.2f",
    )
    spread = st.number_input(
        "Bank spread (%)", min_value=0.1, max_value=5.0,
        value=MORTGAGE_DEFAULT_RATE_VARIABLE, step=0.05, format="%.2f",
    )
    stress = st.number_input(
        "Stress scenario · Euribor +(%)", min_value=0.0, max_value=5.0,
        value=1.0, step=0.25, format="%.2f",
    )

    section("Your income")
    net_income = st.number_input(
        "Monthly net income (€)", min_value=500, max_value=20_000,
        value=2_000, step=100, format="%d",
    )

# ── Compute ───────────────────────────────────────────────────────────────────
fixed = compute_mortgage(principal, fixed_rate, years)
var_base, var_stress = compute_variable_mortgage(principal, spread, euribor, years, stress)

# ── Results ───────────────────────────────────────────────────────────────────
with col_out:
    section("Scenario comparison")
    scenarios = [
        (f"Fixed · {fixed_rate:.2f}%", fixed),
        (f"Variable · {euribor + spread:.2f}%", var_base),
        (f"Stressed · {euribor + spread + stress:.2f}%", var_stress),
    ]
    for col, (label, result) in zip(st.columns(3), scenarios, strict=True):
        with col.container(border=True):
            st.markdown(f"**{label}**")
            st.metric("Monthly payment", f"€{result.monthly_payment:,.0f}",
                      label_visibility="collapsed")
            st.markdown(
                f":small[Total paid €{result.total_paid:,.0f}  ·  "
                f"of which interest €{result.total_interest:,.0f}]"
            )

    section("Affordability check")
    max_ratio = AFFORDABILITY_RATIO_MAX
    for label, result in scenarios:
        pct = result.monthly_payment / net_income * 100
        within = pct <= max_ratio
        colour = TEAL_700 if within else RUST_700
        verdict = "within the guideline" if within else "over the guideline"
        st.markdown(
            f"**{label}** · €{result.monthly_payment:,.0f}/month = "
            f":color[{pct:.1f}% of your net income]{{foreground=\"{colour}\"}} "
            f"— {verdict} of {max_ratio:.0f}%."
        )

    max_loan = max_affordable_loan(net_income, max_ratio, fixed_rate, years)
    min_income = required_income(principal, fixed_rate, years, max_ratio)
    st.info(
        f"On €{net_income:,}/month you can service a loan of about "
        f"**€{max_loan:,.0f}** at {fixed_rate:.2f}% over {years} years. The "
        f"€{principal:,.0f} loan above needs at least **€{min_income:,.0f}/month net**."
    )

    st.markdown("")
    altair_chart(bar_mortgage_cost(fixed))
    altair_chart(bar_amortisation(fixed.schedule))

    with st.expander("Full amortisation schedule (fixed rate)"):
        schedule = pd.DataFrame(fixed.schedule)
        st.dataframe(
            schedule, width="stretch", hide_index=True,
            column_config={
                "month": st.column_config.NumberColumn("Month", format="%d"),
                "year": st.column_config.NumberColumn("Year", format="%d"),
                "payment": st.column_config.NumberColumn("Payment", format="€%,.2f"),
                "interest": st.column_config.NumberColumn("Interest", format="€%,.2f"),
                "amortisation": st.column_config.NumberColumn("Principal", format="€%,.2f"),
                "balance": st.column_config.NumberColumn("Balance", format="€%,.0f"),
            },
        )
