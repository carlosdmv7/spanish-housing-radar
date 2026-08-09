"""
Mortgage — what it really costs to buy, and whether buying is the better use of
the money at all.

The page answers one question — *can I afford this, and should I?* — and is laid
out so that question is answered before any control is touched. Everything a
buyer does not need to change lives behind `st.expander`: the previous version
put fourteen inputs in a single column, which asks a visitor to have opinions
about the Euribor stress delta before it will tell them anything.
"""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from components.charts import bar_amortisation, bar_mortgage_cost
from components.filters import load_municipalities
from components.mortgage import (
    compute_mortgage,
    compute_variable_mortgage,
    max_affordable_loan,
    required_income,
)
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
    EURIBOR_CURRENT,
    MORTGAGE_DEFAULT_LTV,
    MORTGAGE_DEFAULT_RATE_FIXED,
    MORTGAGE_DEFAULT_RATE_VARIABLE,
    MORTGAGE_DEFAULT_YEARS,
    MORTGAGE_SOURCE_NOTE,
)
from connection import query
import pandas as pd
import streamlit as st
from theme import INK_MUTED, RUST_700, TEAL_700, altair_chart, page_hero, section

page_hero(
    "Can I afford this?",
    "The instalment is the easy part. This adds the transfer tax and fees that "
    "buying really costs, prices what a bank's tie-ins are worth, and checks the "
    "whole thing against simply renting and investing the difference.",
)
st.caption(MORTGAGE_SOURCE_NOTE)


# ── Region ────────────────────────────────────────────────────────────────────
# ITP is ceded to the comunidades and varies from 4% to 11%, which on a €400,000
# flat is a €28,000 swing — larger than every other closing cost combined. The
# region is derived from the city rather than asked for: the listing already
# knows where it is, and one more dropdown is one more thing to get wrong.
@st.cache_data(ttl=3600)
def load_region_map() -> dict[str, str]:
    try:
        df = query("SELECT municipality, ine_region FROM spanish_housing_radar.main_silver.ccaa_by_municipality")
        return dict(zip(df["municipality"], df["ine_region"], strict=True))
    except Exception:
        return {}


region_map = load_region_map()
try:
    cities = load_municipalities()
except Exception:
    cities = sorted(region_map) or ["valència"]

with st.sidebar:
    st.header("Your purchase")
    city = st.selectbox(
        "City",
        options=cities,
        index=cities.index("valència") if "valència" in cities else 0,
        format_func=str.title,
        help="Sets the transfer tax: it is a regional tax, not a national one.",
    )
    price = st.number_input(
        "Property price (€)", min_value=30_000, max_value=5_000_000,
        value=250_000, step=5_000, format="%d",
    )
    savings = st.number_input(
        "Savings available (€)", min_value=0, max_value=2_000_000,
        value=70_000, step=5_000, format="%d",
        help="Everything you can put in, including what the tax and fees will eat.",
    )
    net_income = st.number_input(
        "Monthly net income (€)", min_value=500, max_value=20_000,
        value=2_000, step=100, format="%d",
    )
    young_first_home = st.toggle(
        "Under 35, first habitual residence",
        value=True,
        help="Several regions cut the transfer tax sharply for this. Valencia "
             "charges 6% instead of 9% below €180,000.",
    )

    with st.expander("Loan terms"):
        ltv = st.slider("LTV — % financed", 50, 100, int(MORTGAGE_DEFAULT_LTV))
        years = st.slider("Term (years)", 5, 40, MORTGAGE_DEFAULT_YEARS)
        fixed_rate = st.number_input(
            "Fixed rate (%)", 0.1, 15.0, MORTGAGE_DEFAULT_RATE_FIXED, 0.05, "%.2f",
        )
        euribor = st.number_input(
            "Euribor 12m (%)", -2.0, 10.0, EURIBOR_CURRENT, 0.05, "%.2f",
        )
        spread = st.number_input(
            "Bank spread (%)", 0.1, 5.0, MORTGAGE_DEFAULT_RATE_VARIABLE, 0.05, "%.2f",
        )
        stress = st.number_input(
            "Stress · Euribor +(%)", 0.0, 5.0, 1.0, 0.25, "%.2f",
            help="What the variable instalment becomes if rates rise by this much.",
        )

    with st.expander("Fees"):
        include_gestoria = st.toggle("Use a gestoría", value=True)

    with st.expander("Buying vs investing"):
        horizon = st.slider("How long you'd stay (years)", 3, 40, 15)
        monthly_rent = st.number_input(
            "Rent for a similar home (€/mo)", 200, 10_000, 1_000, 50, "%d",
        )
        invest_return = st.slider(
            "Return if you invested instead (%/yr)", 0.0, 12.0, 7.0, 0.5,
            help="Nobody knows this number. It is the single biggest driver of "
                 "the verdict below, which is why it is yours to set.",
        )
        property_growth = st.slider(
            "House price growth (%/yr)", -3.0, 10.0, 2.0, 0.5,
            help="Also unknowable. Rents are indexed at this same rate.",
        )

ine_region = region_map.get(city)
principal = price * ltv / 100

costs = purchase_costs(
    price,
    ltv_pct=ltv,
    ine_region=ine_region,
    young_first_home=young_first_home,
    include_gestoria=include_gestoria,
)
fixed = compute_mortgage(principal, fixed_rate, years)
var_base, var_stress = compute_variable_mortgage(principal, spread, euribor, years, stress)


# ══════════════════════════════════════════════════════════════════════════════
# The answer, before any detail
# ══════════════════════════════════════════════════════════════════════════════
shortfall = costs.cash_needed - savings
ratio = fixed.monthly_payment / net_income * 100
affordable_monthly = ratio <= AFFORDABILITY_RATIO_MAX
have_the_cash = shortfall <= 0

if have_the_cash and affordable_monthly:
    st.success(
        f"**On these numbers, yes.** You need **€{costs.cash_needed:,.0f}** on the "
        f"day you sign and the instalment is **€{fixed.monthly_payment:,.0f}/month**, "
        f"which is {ratio:.0f}% of your net income."
    )
elif not have_the_cash:
    st.error(
        f"**You are €{shortfall:,.0f} short of signing day.** Buying at "
        f"€{price:,.0f} needs **€{costs.cash_needed:,.0f}** in cash — "
        f"€{costs.deposit:,.0f} deposit plus €{costs.total_costs:,.0f} of tax and "
        f"fees — and you have €{savings:,.0f}."
    )
else:
    st.warning(
        f"**The cash works, the monthly does not.** €{fixed.monthly_payment:,.0f}/month "
        f"is {ratio:.0f}% of your net income, above the {AFFORDABILITY_RATIO_MAX:.0f}% "
        "guideline Spanish lenders apply."
    )

c1, c2, c3 = st.columns(3)
c1.metric("Cash needed to sign", f"€{costs.cash_needed:,.0f}",
          help="Deposit plus every tax and fee. This is the number that surprises people.")
c2.metric("Monthly payment", f"€{fixed.monthly_payment:,.0f}",
          help=f"Fixed at {fixed_rate:.2f}% over {years} years.")
c3.metric("Tax and fees", f"€{costs.total_costs:,.0f}",
          delta=f"{costs.costs_pct_of_price:.1f}% of the price", delta_color="off")

st.markdown("")


# ══════════════════════════════════════════════════════════════════════════════
tab_costs, tab_loan, tab_bank, tab_invest = st.tabs(
    ["What it costs to buy", "The loan", "Bank tie-ins", "Buy or invest?"]
)

# ── What it costs to buy ──────────────────────────────────────────────────────
with tab_costs:
    section("Cash needed on signing day")
    st.markdown(
        ":small[A mortgage covers a share of the *price*. It covers none of the "
        "tax and none of the fees, and those are paid in cash within 30 days of "
        "the deed.]"
    )

    breakdown = pd.DataFrame([
        {"item": "Deposit", "amount": costs.deposit,
         "note": f"{100 - ltv:.0f}% of the price — the part the bank will not lend"},
        {"item": "Transfer tax (ITP)", "amount": costs.itp,
         "note": f"{costs.itp_rate:.1f}% · {costs.itp_reason}"},
        {"item": "Notary", "amount": costs.notary, "note": "Witnessing the deed"},
        {"item": "Land registry", "amount": costs.registry, "note": "Recording you as owner"},
        {"item": "Appraisal", "amount": costs.appraisal, "note": "Required by the lender"},
        {"item": "Gestoría", "amount": costs.gestoria,
         "note": "Optional — handles the paperwork" if include_gestoria else "Not used"},
    ])
    st.dataframe(
        breakdown, width="stretch", hide_index=True,
        column_config={
            "item": st.column_config.TextColumn("Item", pinned=True),
            "amount": st.column_config.NumberColumn("Amount", format="€%,d"),
            "note": st.column_config.TextColumn("What it is"),
        },
    )

    regime = ITP_BY_CCAA.get((ine_region or "").lower())
    if regime is not None:
        note = f" {regime.notes}" if regime.notes else ""
        st.caption(
            f"Transfer tax for **{regime.ccaa}**: {costs.itp_rate:.1f}% "
            f"({costs.itp_reason}).{note} Source: {regime.source}. "
            f"Checked {TAX_SOURCES_CONSULTED_ON}."
        )
    else:
        st.caption(
            f"No transfer-tax rate on file for {city.title()}, so this uses the "
            f"{costs.itp_rate:.0f}% national median. Treat the total as indicative."
        )
    st.caption(
        "Notary, registry, appraisal and gestoría are midpoints of the ranges "
        "published for 2026 — they barely move with price, so they are modelled "
        "in euros rather than as a percentage. Your quotes will differ."
    )

# ── The loan ──────────────────────────────────────────────────────────────────
with tab_loan:
    section("Fixed, variable, and variable if rates rise")
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

    section("Against your income")
    for label, result in scenarios:
        pct = result.monthly_payment / net_income * 100
        within = pct <= AFFORDABILITY_RATIO_MAX
        colour = TEAL_700 if within else RUST_700
        st.markdown(
            f"**{label}** · €{result.monthly_payment:,.0f}/month = "
            f":color[{pct:.1f}% of your net income]{{foreground=\"{colour}\"}} "
            f"— {'within' if within else 'over'} the "
            f"{AFFORDABILITY_RATIO_MAX:.0f}% guideline."
        )

    max_loan = max_affordable_loan(net_income, AFFORDABILITY_RATIO_MAX, fixed_rate, years)
    min_income = required_income(principal, fixed_rate, years, AFFORDABILITY_RATIO_MAX)
    st.info(
        f"On €{net_income:,}/month you can service a loan of about "
        f"**€{max_loan:,.0f}** at {fixed_rate:.2f}% over {years} years — a home of "
        f"roughly **€{max_loan / (ltv / 100):,.0f}** at {ltv:.0f}% LTV. The "
        f"€{principal:,.0f} loan above needs at least **€{min_income:,.0f}/month net**."
    )

    st.markdown("")
    altair_chart(bar_mortgage_cost(fixed))
    altair_chart(bar_amortisation(fixed.schedule))

    with st.expander("Full amortisation schedule (fixed rate)"):
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

# ── Bank tie-ins ──────────────────────────────────────────────────────────────
with tab_bank:
    section("What the bank's discounts are actually worth")
    st.markdown(
        ":small[A bonificación is a trade, not a gift: the bank cuts the rate in "
        "exchange for products that cost money. Every bank simulator shows the "
        "cut and hides the price. Tick what you would sign up for.]"
    )

    chosen = []
    for i, bon in enumerate(DEFAULT_BONIFICATIONS):
        cols = st.columns([3, 1])
        with cols[0]:
            take = st.checkbox(
                f"{bon.label} · −{bon.rate_cut_pct:.2f}%",
                value=bon.annual_cost_eur == 0,
                key=f"bon_{i}",
                help=bon.note or None,
            )
        with cols[1]:
            st.markdown(
                f":small[{'free' if bon.annual_cost_eur == 0 else f'€{bon.annual_cost_eur:,.0f}/yr'}]"
            )
        if take:
            chosen.append(bon)

    outcome = apply_bonifications(principal, fixed_rate, years, chosen)

    b1, b2, b3 = st.columns(3)
    b1.metric("Rate after tie-ins", f"{outcome.final_rate:.2f}%",
              delta=f"−{outcome.total_rate_cut:.2f}pp" if outcome.total_rate_cut else None,
              delta_color="inverse")
    b2.metric("Saved on the instalment", f"€{outcome.monthly_saving:,.0f}/mo")
    b3.metric("Cost of the products", f"€{outcome.monthly_tie_in_cost:,.0f}/mo")

    if not chosen:
        st.info("No tie-ins selected — the rate stays at the headline figure.")
    elif outcome.worth_it:
        st.success(
            f"**Worth it: €{outcome.net_monthly_benefit:,.0f}/month better off.** "
            f"The rate cut saves more than the products cost, over "
            f"€{outcome.net_monthly_benefit * 12 * years:,.0f} across {years} years."
        )
    else:
        st.error(
            f"**Not worth it: €{abs(outcome.net_monthly_benefit):,.0f}/month worse off.** "
            "The products cost more than the rate cut saves — the headline rate "
            "looks better while you pay for the privilege."
        )
    st.caption(
        "Insurance premiums are indicative placeholders, not quotes: real ones "
        "depend on your age, the property and the insurer. Replace them with the "
        "figures your bank actually offers before deciding anything."
    )

# ── Buy or invest ─────────────────────────────────────────────────────────────
with tab_invest:
    section(f"Buying versus renting and investing, over {horizon} years")
    st.markdown(
        ":small[The deposit and the tax are not spent if you rent — they are "
        "capital that could be invested. This compares where you end up either "
        "way, and it is the only view here whose answer can be *don't buy*.]"
    )

    cmp = buy_vs_invest(
        price=price,
        costs=costs,
        monthly_payment=fixed.monthly_payment,
        years=years,
        horizon_years=horizon,
        monthly_rent=monthly_rent,
        investment_return_pct=invest_return,
        property_growth_pct=property_growth,
        outstanding_balance_at_horizon=balance_after(fixed.schedule, horizon),
    )

    left, right = st.columns(2)
    with left.container(border=True):
        st.markdown("**Buy**")
        st.metric("Net worth after " + f"{horizon}y", f"€{cmp.net_worth_buying:,.0f}",
                  label_visibility="collapsed")
        st.markdown(
            f":small[Home worth €{cmp.property_value_at_horizon:,.0f}, "
            f"€{cmp.outstanding_balance:,.0f} still owed, "
            f"€{costs.total_costs:,.0f} of tax and fees gone for good.]"
        )
    with right.container(border=True):
        st.markdown("**Rent and invest**")
        st.metric("Net worth after " + f"{horizon}y", f"€{cmp.net_worth_renting:,.0f}",
                  label_visibility="collapsed")
        st.markdown(
            f":small[€{cmp.cash_invested:,.0f} invested up front at "
            f"{invest_return:.1f}%/yr, €{cmp.total_rent_paid:,.0f} paid in rent.]"
        )

    if cmp.buying_wins:
        st.success(
            f"**Buying comes out €{abs(cmp.difference):,.0f} ahead** over "
            f"{horizon} years, assuming {property_growth:.1f}% house-price growth "
            f"and {invest_return:.1f}% on investments."
        )
    else:
        st.warning(
            f"**Renting and investing comes out €{abs(cmp.difference):,.0f} ahead** "
            f"over {horizon} years at {invest_return:.1f}% returns against "
            f"{property_growth:.1f}% house-price growth."
        )

    st.markdown(
        f":small[:color[This verdict is a function of two numbers nobody knows — "
        f"the {invest_return:.1f}% return and the {property_growth:.1f}% growth. "
        f"Move either slider and it can flip. Treat it as a way to see how much "
        f"the answer depends on your assumptions, not as a "
        f"forecast.]{{foreground=\"{INK_MUTED}\"}}]"
    )
    st.caption(
        "Not modelled: IBI and community fees, maintenance, the tax treatment of "
        "investment gains, transaction costs on selling, or the value of not "
        "having a landlord. The first three favour renting; the last does not "
        "have a number."
    )
