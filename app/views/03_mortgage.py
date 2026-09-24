"""
Budget — what buying really costs, and whether it beats renting.

Answer first: four inputs in one row, then a verdict, four numbers and two
charts before anything else asks for attention. Everything a buyer rarely
changes — loan terms, fees, bank tie-ins, the full schedule, where each default
comes from — sits behind a popover or an expander instead of in a sidebar of
fourteen inputs that had to be filled in before the page would say anything.
"""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from chrome import page_header
from components.charts import bar_amortisation, bar_signing_day, line_buy_vs_rent
from components.filters import load_municipalities
from components.mortgage import compute_mortgage, compute_variable_mortgage, max_affordable_loan
from components.purchase_costs import (
    DEFAULT_BONIFICATIONS,
    ITP_BY_CCAA,
    TAX_SOURCES_CONSULTED_ON,
    apply_bonifications,
    balance_after,
    buy_vs_invest,
    purchase_costs,
)
from config import (
    AFFORDABILITY_RATIO_MAX,
    AFFORDABILITY_SOURCE_NOTE,
    EURIBOR_CURRENT,
    MORTGAGE_DEFAULT_LTV,
    MORTGAGE_DEFAULT_RATE_FIXED,
    MORTGAGE_DEFAULT_RATE_VARIABLE,
    MORTGAGE_DEFAULT_YEARS,
    MORTGAGE_SOURCE_NOTE,
    VALENCIA_AVG_NET_SALARY_MONTHLY,
)
from connection import query
import pandas as pd
import streamlit as st
from theme import altair_chart

page_header(
    "What will buying really cost me?",
    "The cash to sign, the monthly payment, and when buying starts to beat renting.",
)


# ITP is ceded to the comunidades and runs from 4% to 11% — on a €400,000 flat a
# €28,000 swing, bigger than every other closing cost combined. The region comes
# from the city, because the visitor knows their city and not always which
# regime it falls under.
@st.cache_data(ttl=3600)
def load_city_facts() -> pd.DataFrame:
    """Each city's region and its median asking €/m² to buy and to rent."""
    return query("""
        SELECT c.municipality, c.ine_region,
               MEDIAN(o.price_per_sqm) FILTER (WHERE o.operation_type = 'sale') AS sale_ppsqm,
               MEDIAN(o.price_per_sqm) FILTER (WHERE o.operation_type = 'rent') AS rent_ppsqm
        FROM spanish_housing_radar.main_silver.ccaa_by_municipality c
        LEFT JOIN spanish_housing_radar.main_gold.rpt_opportunities o
          ON o.municipality = c.municipality AND o.property_type = 'apartment'
        GROUP BY 1, 2
    """).set_index("municipality")


try:
    facts = load_city_facts()
except Exception:
    facts = pd.DataFrame(columns=["ine_region", "sale_ppsqm", "rent_ppsqm"])
try:
    cities = load_municipalities()
except Exception:
    cities = sorted(facts.index) or ["valència"]

# ── Inputs: four in a row, the rest one click away ────────────────────────────
c_city, c_price, c_savings, c_income, c_more = st.columns(
    [1.2, 1.2, 1.2, 1.2, 1], vertical_alignment="bottom")
with c_city:
    city = st.selectbox(
        "City", cities, index=cities.index("valència") if "valència" in cities else 0,
        format_func=str.title, help="Sets the transfer tax, which is regional.")
with c_price:
    # €180,000 is where València's under-35 transfer-tax cut stops, so the
    # opening example shows the one lever most first-time buyers miss.
    price = st.number_input(
        "Price (€)", 30_000, 5_000_000, 180_000, 5_000, "%d",
        help="€180,000 is the ceiling for València's reduced 6% transfer tax "
             "for buyers under 35.")
with c_savings:
    savings = st.number_input(
        "Savings (€)", 0, 2_000_000, 50_000, 5_000, "%d",
        help="Everything you can put in, including what tax and fees will take.")
with c_income:
    net_income = st.number_input(
        "Net income (€/month)", 500, 20_000, int(VALENCIA_AVG_NET_SALARY_MONTHLY), 100,
        "%d", help="Defaults to the Comunitat Valenciana average — see the sources "
                   "at the bottom.")
with c_more, st.popover("Loan terms", icon=":material/tune:", width="stretch"):
    young_first_home = st.toggle(
        "Under 35, first home", value=True,
        help="Several regions cut the transfer tax for this. València charges 6% "
             "instead of 9% below €180,000.")
    include_gestoria = st.toggle("Use a gestoría", value=True)
    ltv = st.slider("Share financed (LTV %)", 50, 100, int(MORTGAGE_DEFAULT_LTV))
    years = st.slider("Term (years)", 5, 40, MORTGAGE_DEFAULT_YEARS)
    fixed_rate = st.number_input("Fixed rate (%)", 0.1, 15.0,
                                 MORTGAGE_DEFAULT_RATE_FIXED, 0.05, "%.2f")
    euribor = st.number_input("Euribor 12m (%)", -2.0, 10.0, EURIBOR_CURRENT, 0.05, "%.2f")
    spread = st.number_input("Bank spread (%)", 0.1, 5.0,
                             MORTGAGE_DEFAULT_RATE_VARIABLE, 0.05, "%.2f")
    stress = st.number_input("Stress: Euribor + (%)", 0.0, 5.0, 1.0, 0.25, "%.2f",
                             help="What the variable payment becomes if rates rise "
                                  "this much.")

ine_region = facts["ine_region"].get(city) if not facts.empty else None
principal = price * ltv / 100


def costs_at(p: float):
    return purchase_costs(p, ltv_pct=ltv, ine_region=ine_region,
                          young_first_home=young_first_home,
                          include_gestoria=include_gestoria)


costs = costs_at(price)
fixed = compute_mortgage(principal, fixed_rate, years)
var_base, var_stress = compute_variable_mortgage(principal, spread, euribor, years, stress)


def most_you_could_buy() -> tuple[float, str]:
    """The dearest home both your savings and your income can carry."""
    by_income = max_affordable_loan(net_income, AFFORDABILITY_RATIO_MAX,
                                    fixed_rate, years) / (ltv / 100)
    # Cash needed rises with price but not linearly (the ITP band can step), so
    # search rather than invert.
    lo, hi = 0.0, 5_000_000.0
    for _ in range(40):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if costs_at(mid).cash_needed <= savings else (lo, mid)
    by_savings = lo
    return ((by_income, "your income") if by_income < by_savings
            else (by_savings, "your savings"))


# ── The answer ────────────────────────────────────────────────────────────────
shortfall = costs.cash_needed - savings
ratio = fixed.monthly_payment / net_income * 100
if shortfall > 0:
    st.badge(f"€{shortfall:,.0f} short of signing day", icon=":material/block:",
             color="red")
elif ratio > AFFORDABILITY_RATIO_MAX:
    st.badge(f"The cash works; the payment is {ratio:.0f}% of your income",
             icon=":material/warning:", color="orange")
else:
    st.badge("Within reach on these numbers", icon=":material/check_circle:",
             color="green")

most, limit = most_you_could_buy()
m1, m2, m3, m4 = st.columns(4)
m1.metric("Cash to sign", f"€{costs.cash_needed:,.0f}",
          delta=f"you have €{savings:,.0f}", delta_color="off", delta_arrow="off",
          help="Deposit plus every tax and fee, paid on or around the day of the deed.")
m2.metric("Monthly payment", f"€{fixed.monthly_payment:,.0f}",
          delta=f"{ratio:.0f}% of your income", delta_color="off", delta_arrow="off",
          help=f"Fixed at {fixed_rate:.2f}% over {years} years. Lenders rarely go past "
               f"{AFFORDABILITY_RATIO_MAX:.0f}%.")
m3.metric("Tax and fees", f"€{costs.total_costs:,.0f}",
          delta=f"{costs.costs_pct_of_price:.1f}% of the price", delta_color="off",
          delta_arrow="off", help="Money that buys nothing you can later sell.")
m4.metric("The most you could buy", f"€{most:,.0f}",
          delta=f"limited by {limit}", delta_color="off", delta_arrow="off",
          help=f"The dearest home your savings cover the cash for and your income "
               f"covers the payment on, at {ltv}% financed and "
               f"{AFFORDABILITY_RATIO_MAX:.0f}% of income.")

st.divider()

# ── Where the cash goes · the loan ────────────────────────────────────────────
left, right = st.columns(2, gap="large")
with left:
    st.markdown("#### Where the cash goes")
    items = pd.DataFrame([
        {"item": "Deposit", "eur": costs.deposit,
         "note": f"{100 - ltv}% of the price, the part the bank will not lend"},
        {"item": "Transfer tax", "eur": costs.itp,
         "note": f"{costs.itp_rate:.1f}%, {costs.itp_reason}"},
        {"item": "Notary", "eur": costs.notary, "note": "Witnessing the deed"},
        {"item": "Land registry", "eur": costs.registry, "note": "Recording you as owner"},
        {"item": "Appraisal", "eur": costs.appraisal, "note": "Required by the lender"},
        {"item": "Gestoría", "eur": costs.gestoria, "note": "Handles the paperwork"},
    ])
    altair_chart(bar_signing_day(items))
    st.caption(f"The mortgage covers {ltv}% of the price and none of the tax or fees.")

with right:
    st.markdown("#### The loan")
    scenarios = [
        ("Fixed", fixed_rate, fixed),
        ("Variable", euribor + spread, var_base),
        ("If Euribor rises", euribor + spread + stress, var_stress),
    ]
    for col, (label, rate, result) in zip(st.columns(3), scenarios, strict=True):
        col.metric(f"{label} · {rate:.2f}%", f"€{result.monthly_payment:,.0f}/mo",
                   help=f"€{result.total_interest:,.0f} of interest over {years} years.")
    altair_chart(bar_amortisation(fixed.schedule).properties(height=220, title=""))
    st.caption(f"Fixed rate: €{fixed.total_interest:,.0f} of interest on a "
               f"€{principal:,.0f} loan. Early payments are mostly interest.")

st.divider()

# ── Buy, or rent and invest ───────────────────────────────────────────────────
st.markdown("#### When does buying beat renting?")

# The rent for a comparable home, from this city's own asking prices: the price
# times the city's rent-to-price ratio per m². A made-up round number here would
# decide the verdict below more than anything the visitor typed.
sale_ppsqm = facts["sale_ppsqm"].get(city) if not facts.empty else None
rent_ppsqm = facts["rent_ppsqm"].get(city) if not facts.empty else None
default_rent = (int(round(price * rent_ppsqm / sale_ppsqm, -1))
                if pd.notna(sale_ppsqm) and pd.notna(rent_ppsqm) else 1_000)

r1, r2, r3 = st.columns(3)
monthly_rent = r1.number_input(
    "Rent for a similar home (€/month)", 200, 10_000, default_rent, 50, "%d",
    help=f"Suggested from {city.title()}'s asking rents and prices per m²."
    if default_rent != 1_000 else None)
invest_return = r2.slider(
    "Return if you invested instead (%/yr)", 0.0, 12.0, 7.0, 0.5,
    help="Nobody knows this. It moves the answer more than anything else here.")
property_growth = r3.slider(
    "House prices and rents grow (%/yr)", -3.0, 10.0, 2.0, 0.5,
    help="Also unknowable. Rents are indexed at the same rate.")


def compare(horizon: int):
    return buy_vs_invest(
        price=price, costs=costs, monthly_payment=fixed.monthly_payment, years=years,
        horizon_years=horizon, monthly_rent=monthly_rent,
        investment_return_pct=invest_return, property_growth_pct=property_growth,
        outstanding_balance_at_horizon=balance_after(fixed.schedule, horizon))


runs = [compare(h) for h in range(1, years + 1)]
series = pd.DataFrame({
    "year": range(1, years + 1),
    "Buy": [c.net_worth_buying for c in runs],
    "Rent and invest": [c.net_worth_renting for c in runs],
})
# The year from which buying *stays* ahead, not the first year it touches: a
# path that crosses and falls back again has not broken even.
behind = series.loc[series["Buy"] < series["Rent and invest"], "year"]
breakeven = (1 if behind.empty
             else int(behind.max()) + 1 if behind.max() < years else None)

altair_chart(line_buy_vs_rent(series, breakeven))
if breakeven is None:
    st.caption(f"On these assumptions renting and investing stays ahead for the whole "
               f"{years}-year term.")
elif breakeven == 1:
    st.caption("On these assumptions buying is ahead from the first year.")
else:
    st.caption(f"On these assumptions buying pulls ahead after **{breakeven} years** — "
               "sell sooner and the tax and fees have not been earned back. Move either "
               "slider and the year moves: it is a sensitivity, not a forecast.")

# ── The detail, for whoever wants it ──────────────────────────────────────────
with st.expander("Bank tie-ins: are the discounts worth it?"):
    st.caption("A bonificación trades a lower rate for products that cost money. "
               "Tick what you would sign up for.")
    chosen = [
        bon for i, bon in enumerate(DEFAULT_BONIFICATIONS)
        if st.checkbox(
            f"{bon.label} · −{bon.rate_cut_pct:.2f}% · "
            + ("free" if bon.annual_cost_eur == 0 else f"€{bon.annual_cost_eur:,.0f}/yr"),
            value=bon.annual_cost_eur == 0, key=f"bon_{i}", help=bon.note or None)
    ]
    outcome = apply_bonifications(principal, fixed_rate, years, chosen)
    b1, b2, b3 = st.columns(3)
    b1.metric("Rate after tie-ins", f"{outcome.final_rate:.2f}%")
    b2.metric("Saved on the payment", f"€{outcome.monthly_saving:,.0f}/mo")
    b3.metric("Cost of the products", f"€{outcome.monthly_tie_in_cost:,.0f}/mo")
    if chosen:
        if outcome.worth_it:
            st.badge(f"Worth it: €{outcome.net_monthly_benefit:,.0f}/month better off",
                     icon=":material/check_circle:", color="green")
        else:
            st.badge(f"Not worth it: €{abs(outcome.net_monthly_benefit):,.0f}/month "
                     "worse off", icon=":material/block:", color="red")
    st.caption("Insurance premiums are indicative, not quotes. Use your bank's.")

with st.expander("Full amortisation schedule"):
    st.dataframe(
        pd.DataFrame(fixed.schedule), width="stretch", hide_index=True,
        column_config={
            "month": st.column_config.NumberColumn("Month", format="%d"),
            "year": st.column_config.NumberColumn("Year", format="%d"),
            "payment": st.column_config.NumberColumn("Payment", format="€%,.2f"),
            "interest": st.column_config.NumberColumn("Interest", format="€%,.2f"),
            "amortisation": st.column_config.NumberColumn("Principal", format="€%,.2f"),
            "balance": st.column_config.NumberColumn("Balance", format="€%,.0f"),
        },
    )

with st.expander("Where these numbers come from"):
    st.markdown(MORTGAGE_SOURCE_NOTE)
    st.markdown(AFFORDABILITY_SOURCE_NOTE)
    regime = ITP_BY_CCAA.get((ine_region or "").lower())
    if regime is not None:
        st.markdown(f"**Transfer tax, {regime.ccaa}** — {costs.itp_rate:.1f}% "
                    f"({costs.itp_reason}). {regime.notes} Source: {regime.source}. "
                    f"Checked {TAX_SOURCES_CONSULTED_ON}.")
    else:
        st.markdown(f"**Transfer tax** — no rate on file for {city.title()}, so the "
                    f"{costs.itp_rate:.0f}% national median is used.")
    st.markdown("**Notary, registry, appraisal, gestoría** — midpoints of the ranges "
                "published for 2026, in euros rather than a percentage because they "
                "barely move with price. **Not modelled:** IBI and community fees, "
                "maintenance, tax on investment gains, the cost of selling.")
