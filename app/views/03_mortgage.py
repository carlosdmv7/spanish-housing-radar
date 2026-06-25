"""
Page 3 — Mortgage Calculator
Fixed vs variable, French amortisation schedule, affordability check.
"""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from components.charts import line_amortisation, waterfall_mortgage
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
)
import pandas as pd
import streamlit as st
from styles import page_hero

page_hero(
    "🧮",
    "Mortgage Calculator",
    "Compare fixed vs variable mortgages with a full French amortisation "
    "schedule and a stress scenario. All figures are indicative.",
)

# ── Inputs ────────────────────────────────────────────────────────────────────
col_in, col_out = st.columns([1, 2])

with col_in:
    st.markdown("#### Property")
    property_price = st.number_input(
        "Property price (€)", min_value=50_000, max_value=5_000_000,
        value=350_000, step=5_000, format="%d",
    )
    ltv = st.slider("LTV — % financed", min_value=50, max_value=100, value=int(MORTGAGE_DEFAULT_LTV))
    down_payment = property_price * (1 - ltv / 100)
    principal    = property_price * ltv / 100

    st.info(f"**Down payment:** €{down_payment:,.0f}  ·  **Loan:** €{principal:,.0f}")

    st.markdown("#### Terms")
    years = st.slider("Term (years)", 5, 40, MORTGAGE_DEFAULT_YEARS)

    st.markdown("#### Fixed rate")
    fixed_rate = st.number_input(
        "Fixed rate (%)", min_value=0.1, max_value=15.0,
        value=MORTGAGE_DEFAULT_RATE_FIXED, step=0.05, format="%.2f",
    )

    st.markdown("#### Variable rate")
    euribor = st.number_input(
        "Euribor 12m (%)", min_value=-2.0, max_value=10.0,
        value=EURIBOR_CURRENT, step=0.05, format="%.2f",
    )
    spread = st.number_input(
        "Bank spread (%)", min_value=0.1, max_value=5.0,
        value=MORTGAGE_DEFAULT_RATE_VARIABLE, step=0.05, format="%.2f",
    )
    stress = st.number_input(
        "Stress scenario Euribor +(%)", min_value=0.0, max_value=5.0,
        value=1.0, step=0.25, format="%.2f",
    )

    st.markdown("#### Personal affordability")
    net_income = st.number_input(
        "Monthly net income (€)", min_value=500, max_value=20_000,
        value=2_000, step=100, format="%d",
    )

# ── Compute ───────────────────────────────────────────────────────────────────
fixed                = compute_mortgage(principal, fixed_rate, years)
var_base, var_stress = compute_variable_mortgage(principal, spread, euribor, years, stress)

# ── Results ───────────────────────────────────────────────────────────────────
with col_out:
    st.markdown("#### Scenario comparison")

    r1, r2, r3 = st.columns(3)

    def scenario_col(col, label: str, result, highlight: bool = False):
        border = "2px solid #3b82f6" if highlight else "1px solid rgba(148,163,184,0.18)"
        bg = "rgba(59,130,246,0.10)" if highlight else "#161b26"
        col.markdown(
            f"<div style='border:{border};background:{bg};border-radius:12px;padding:16px'>"
            f"<div style='font-weight:700;margin-bottom:8px'>{label}</div>"
            f"<div style='font-size:1.6rem;font-weight:800'>€{result.monthly_payment:,.0f}"
            f"<span style='font-size:1rem;font-weight:400;color:#94a3b8'>/month</span></div>"
            f"<div style='color:#94a3b8;font-size:0.85rem;margin-top:4px'>Total paid: €{result.total_paid:,.0f}</div>"
            f"<div style='color:#f87171;font-size:0.85rem'>Interest: €{result.total_interest:,.0f}</div>"
            f"</div>",
            unsafe_allow_html=True,
        )

    scenario_col(r1, f"🔒 Fixed {fixed_rate:.2f}%",                fixed,      highlight=True)
    scenario_col(r2, f"📈 Variable {euribor+spread:.2f}%",         var_base)
    scenario_col(r3, f"⚠️ Stress {euribor+spread+stress:.2f}%",   var_stress)

    st.markdown("---")

    # Affordability check
    st.markdown("#### Affordability check")
    max_ratio   = AFFORDABILITY_RATIO_MAX
    max_payment = net_income * max_ratio / 100

    def affordability_badge(result, label):
        pct   = result.monthly_payment / net_income * 100
        ok    = pct <= max_ratio
        color = "#22c55e" if ok else "#ef4444"
        icon  = "✅" if ok else "❌"
        st.markdown(
            f"{icon} **{label}**: monthly payment **€{result.monthly_payment:,.0f}** = "
            f"<span style='color:{color};font-weight:700'>{pct:.1f}% of your income</span> "
            f"(recommended max: {max_ratio:.0f}%)",
            unsafe_allow_html=True,
        )

    affordability_badge(fixed,      f"Fixed {fixed_rate:.2f}%")
    affordability_badge(var_base,   f"Variable base {euribor+spread:.2f}%")
    affordability_badge(var_stress, f"Variable stress {euribor+spread+stress:.2f}%")

    max_loan   = max_affordable_loan(net_income, max_ratio, fixed_rate, years)
    min_income = required_income(principal, fixed_rate, years, max_ratio)
    st.info(
        f"With €{net_income:,}/month you can afford a loan of up to **€{max_loan:,.0f}** "
        f"(fixed {fixed_rate:.2f}%, {years} years).  \n"
        f"For a loan of €{principal:,.0f} you need at least **€{min_income:,.0f}/month net**."
    )

    st.markdown("---")

    col_wf, col_am = st.columns(2)
    with col_wf:
        st.plotly_chart(waterfall_mortgage(fixed), use_container_width=True)
    with col_am:
        st.plotly_chart(line_amortisation(fixed.schedule), use_container_width=True)

    with st.expander("📋 Full amortisation schedule (fixed rate)"):
        schedule_df = pd.DataFrame(fixed.schedule)
        schedule_df.columns = ["Month", "Year", "Payment (€)", "Interest (€)", "Principal (€)", "Balance (€)"]
        st.dataframe(schedule_df, use_container_width=True, hide_index=True)
