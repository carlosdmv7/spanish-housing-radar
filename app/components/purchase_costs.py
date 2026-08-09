"""
What a purchase actually costs, and what the money would have done elsewhere.

Pure functions — no Streamlit, no I/O, all deterministic and unit-testable.

Two things live here that the mortgage page was silently ignoring.

**Buying is not the price.** A €300,000 flat in València costs about €335,000 to
take possession of: transfer tax, notary, land registry, an appraisal the bank
requires, and a gestoría most buyers use. The old page computed an instalment
from a price and called it affordability, which understates the cash a buyer
must actually have by roughly a third of their deposit.

**The alternative is not nothing.** The deposit and closing costs are capital
that could sit in an index fund. Comparing a mortgage against paying rent while
investing the difference is the comparison a buyer is really making, and it is
the one no mortgage calculator shows them.

Every rate carries its source and the date it was checked, for the same reason
`config.py` does: this project's claim is that its numbers are auditable.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# Checked against the sources cited on each regime below.
TAX_SOURCES_CONSULTED_ON = "2026-08-08"


@dataclass(frozen=True)
class ItpRegime:
    """
    Transfer-tax treatment of second-hand housing in one autonomous community.

    ITP is ceded to the comunidades, so the same flat is taxed at 4% in Bilbao
    and 10% in Barcelona — a €24,000 difference on €400,000, which is larger
    than every other closing cost combined. Modelling it as one national number
    would be the single biggest lie this page could tell.
    """

    ccaa: str
    general_rate: float
    # Some communities step the rate up above a value threshold rather than
    # applying one flat percentage.
    upper_rate: float | None = None
    upper_threshold: float | None = None
    # Reduced rate for a young buyer's first habitual residence, where one
    # exists. `young_max_price` is the ceiling above which it no longer applies.
    young_rate: float | None = None
    young_max_price: float | None = None
    young_max_age: int | None = None
    notes: str = ""
    source: str = ""

    def rate_for(
        self,
        price: float,
        *,
        young_first_home: bool = False,
    ) -> tuple[float, str]:
        """
        Return (rate %, a one-line explanation of why that rate).

        The explanation is returned rather than logged because the page shows it:
        a buyer who sees "6%" and cannot tell whether the under-35 relief was
        applied has no way to check the figure against their own situation.
        """
        if (
            young_first_home
            and self.young_rate is not None
            and (self.young_max_price is None or price <= self.young_max_price)
        ):
            ceiling = (
                f" on purchases up to €{self.young_max_price:,.0f}"
                if self.young_max_price
                else ""
            )
            age = f" under {self.young_max_age}" if self.young_max_age else ""
            return self.young_rate, (
                f"reduced rate for a first habitual residence{age}{ceiling}"
            )

        if (
            self.upper_rate is not None
            and self.upper_threshold is not None
            and price > self.upper_threshold
        ):
            return self.upper_rate, (
                f"higher band, above €{self.upper_threshold:,.0f}"
            )

        if young_first_home and self.young_rate is not None:
            return self.general_rate, (
                "general rate — the reduced band does not reach this price"
            )
        return self.general_rate, "general rate"


# Only the communities this app actually holds listings for. Adding a rate for a
# region with no coverage would be inventing precision: it could never be checked
# against a listing, and a wrong number nobody exercises is a wrong number that
# survives.
ITP_BY_CCAA: dict[str, ItpRegime] = {
    "comunitat valenciana": ItpRegime(
        ccaa="Comunitat Valenciana",
        general_rate=9.0,
        upper_rate=11.0,
        upper_threshold=1_000_000,
        young_rate=6.0,
        young_max_price=180_000,
        young_max_age=35,
        notes=(
            "The general rate fell from 10% to 9% on 1 June 2026. The 6% band "
            "also requires an IRPF base under €30,000 (individual) or €47,000 "
            "(joint), which this tool does not ask for and cannot verify."
        ),
        source="Generalitat Valenciana, Art. 13 Ley 13/1997 (hisenda.gva.es)",
    ),
    "madrid, comunidad de": ItpRegime(
        ccaa="Comunidad de Madrid",
        general_rate=6.0,
        source="Comunidad de Madrid — general ITP rate on second-hand housing",
    ),
    "cataluña": ItpRegime(
        ccaa="Cataluña",
        general_rate=10.0,
        upper_rate=11.0,
        upper_threshold=1_000_000,
        source="Generalitat de Catalunya — tiered ITP on second-hand housing",
    ),
    "andalucía": ItpRegime(
        ccaa="Andalucía",
        general_rate=7.0,
        source="Junta de Andalucía — general ITP rate on second-hand housing",
    ),
    "país vasco": ItpRegime(
        ccaa="País Vasco",
        general_rate=4.0,
        notes="Foral tax regime; the rate is set by each provincial diputación.",
        source="Foral regime (Bizkaia/Gipuzkoa/Álava)",
    ),
    "aragón": ItpRegime(
        ccaa="Aragón",
        general_rate=8.0,
        upper_rate=10.0,
        upper_threshold=400_000,
        young_rate=4.0,
        young_max_price=100_000,
        young_max_age=35,
        source="Gobierno de Aragón — tiered ITP on second-hand housing",
    ),
    "castilla y león": ItpRegime(
        ccaa="Castilla y León",
        general_rate=8.0,
        upper_rate=10.0,
        upper_threshold=250_000,
        source="Junta de Castilla y León — tiered ITP on second-hand housing",
    ),
}

# Fallback when the city's community is unknown. Deliberately the *median* of the
# general rates above rather than a comfortable low number: an unknown region
# should not quietly produce the cheapest possible answer.
DEFAULT_ITP_RATE = 8.0


# ── Fixed closing costs ───────────────────────────────────────────────────────
# These barely move with price — a notary charges roughly the same to witness a
# €200,000 deed as a €400,000 one — so they are modelled as a range in euros
# rather than a percentage, with the midpoint used for the estimate. Sourced
# from idealista's own 2026 cost guide and arquitasa; both agree on these bands.
NOTARY_EUR = (600.0, 1_200.0)
REGISTRY_EUR = (400.0, 650.0)
GESTORIA_EUR = (300.0, 400.0)
APPRAISAL_EUR = (250.0, 600.0)


def _midpoint(band: tuple[float, float]) -> float:
    return (band[0] + band[1]) / 2


@dataclass(frozen=True)
class PurchaseCosts:
    price: float
    itp_rate: float
    itp_reason: str
    itp: float
    notary: float
    registry: float
    gestoria: float
    appraisal: float
    deposit: float

    @property
    def fees(self) -> float:
        """Everything that is not tax and not the deposit."""
        return self.notary + self.registry + self.gestoria + self.appraisal

    @property
    def total_costs(self) -> float:
        """Tax plus fees — the money that buys nothing you can later sell."""
        return self.itp + self.fees

    @property
    def cash_needed(self) -> float:
        """Deposit plus costs: what must be in the bank on signing day."""
        return self.deposit + self.total_costs

    @property
    def costs_pct_of_price(self) -> float:
        return self.total_costs / self.price * 100 if self.price else 0.0


def purchase_costs(
    price: float,
    *,
    ltv_pct: float,
    ine_region: str | None = None,
    young_first_home: bool = False,
    include_gestoria: bool = True,
) -> PurchaseCosts:
    """
    Full cash cost of acquiring a second-hand home.

    `ine_region` is the community name as it appears in the `ccaa_by_municipality`
    seed, so the caller passes a city and never has to ask the user which
    autonomous community they are in — the listing already knows.
    """
    regime = ITP_BY_CCAA.get((ine_region or "").strip().lower())
    if regime is None:
        rate, reason = DEFAULT_ITP_RATE, "national median — region unknown"
    else:
        rate, reason = regime.rate_for(price, young_first_home=young_first_home)

    return PurchaseCosts(
        price=price,
        itp_rate=rate,
        itp_reason=reason,
        itp=round(price * rate / 100, 2),
        notary=_midpoint(NOTARY_EUR),
        registry=_midpoint(REGISTRY_EUR),
        gestoria=_midpoint(GESTORIA_EUR) if include_gestoria else 0.0,
        appraisal=_midpoint(APPRAISAL_EUR),
        deposit=round(price * (100 - ltv_pct) / 100, 2),
    )


# ── Bank tie-ins ──────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class Bonification:
    """
    One rate discount and what the bank charges you for it.

    A "bonificación" is not a discount, it is a trade: the bank cuts the rate in
    exchange for products that cost money. Home insurance bought through the
    lender is routinely dearer than the same cover on the open market, and life
    insurance may be something the buyer neither needs nor would otherwise buy.
    Modelling only the rate cut — which is what every bank's own simulator does —
    makes every tie-in look free.
    """

    label: str
    rate_cut_pct: float
    annual_cost_eur: float = 0.0
    note: str = ""


DEFAULT_BONIFICATIONS: list[Bonification] = [
    Bonification("Salary paid into the account", 0.30, 0.0,
                 "Usually free, and usually the largest single cut."),
    Bonification("Home insurance with the lender", 0.10, 250.0,
                 "Comparable cover on the open market is typically cheaper."),
    Bonification("Life insurance with the lender", 0.20, 350.0,
                 "Cost rises with age; the quote here is indicative only."),
    Bonification("Pension plan contributions", 0.10, 0.0,
                 "No direct cost, but it locks up savings until retirement."),
    Bonification("Card / recurring direct debits", 0.05, 0.0),
]


@dataclass(frozen=True)
class BonificationOutcome:
    base_rate: float
    final_rate: float
    total_rate_cut: float
    annual_tie_in_cost: float
    monthly_saving: float
    monthly_tie_in_cost: float
    net_monthly_benefit: float
    worth_it: bool
    selected: list[Bonification] = field(default_factory=list)


def apply_bonifications(
    principal: float,
    base_rate: float,
    years: int,
    selected: list[Bonification],
) -> BonificationOutcome:
    """
    Net effect of a set of tie-ins: rate cut *minus* what the products cost.

    Imported lazily to keep this module free of a circular import with
    `components.mortgage`, which does not depend on this one.
    """
    from components.mortgage import compute_mortgage

    total_cut = sum(b.rate_cut_pct for b in selected)
    final_rate = max(0.0, base_rate - total_cut)

    before = compute_mortgage(principal, base_rate, years)
    after = compute_mortgage(principal, final_rate, years)

    monthly_saving = before.monthly_payment - after.monthly_payment
    annual_cost = sum(b.annual_cost_eur for b in selected)
    monthly_cost = annual_cost / 12

    return BonificationOutcome(
        base_rate=base_rate,
        final_rate=round(final_rate, 3),
        total_rate_cut=round(total_cut, 3),
        annual_tie_in_cost=round(annual_cost, 2),
        monthly_saving=round(monthly_saving, 2),
        monthly_tie_in_cost=round(monthly_cost, 2),
        net_monthly_benefit=round(monthly_saving - monthly_cost, 2),
        worth_it=(monthly_saving - monthly_cost) > 0,
        selected=list(selected),
    )


# ── Buying versus investing ───────────────────────────────────────────────────
@dataclass(frozen=True)
class OpportunityComparison:
    years: int
    # Buying
    cash_invested: float
    total_mortgage_paid: float
    equity_at_horizon: float
    property_value_at_horizon: float
    outstanding_balance: float
    net_worth_buying: float
    # Renting and investing the difference
    total_rent_paid: float
    portfolio_at_horizon: float
    net_worth_renting: float
    # Verdict
    difference: float
    buying_wins: bool


def buy_vs_invest(
    *,
    price: float,
    costs: PurchaseCosts,
    monthly_payment: float,
    years: int,
    horizon_years: int,
    monthly_rent: float,
    investment_return_pct: float,
    property_growth_pct: float,
    outstanding_balance_at_horizon: float,
) -> OpportunityComparison:
    """
    Compare buying against renting the same home and investing the difference.

    This is the comparison a buyer is actually making and the one no mortgage
    calculator shows, because it is the only one where the answer can be "don't
    buy". The deposit and closing costs are not spent in the renting branch, so
    they are invested from day one; the monthly gap between the instalment and
    the rent is invested as it arises.

    Two honesty constraints are built into the shape of this function rather than
    left to the caller:

    * Closing costs enter the buying branch as **spent**, never as equity. ITP
      buys nothing resaleable, and treating it as part of the asset is the most
      common way these comparisons flatter buying.
    * `property_growth_pct` and `investment_return_pct` are both required. A
      default on either would smuggle in a prediction, and the entire verdict is
      a function of two numbers nobody knows.
    """
    months = horizon_years * 12
    r_invest = investment_return_pct / 100 / 12

    # ── Buying ────────────────────────────────────────────────────────────────
    property_value = price * (1 + property_growth_pct / 100) ** horizon_years
    equity = property_value - outstanding_balance_at_horizon
    total_mortgage_paid = monthly_payment * months
    # Cash gone: the deposit and every closing cost.
    net_worth_buying = equity - costs.total_costs

    # ── Renting and investing ─────────────────────────────────────────────────
    # The cash that would have been the deposit and costs is invested up front.
    portfolio = costs.cash_needed
    total_rent = 0.0
    rent = monthly_rent
    for month in range(1, months + 1):
        portfolio *= 1 + r_invest
        # Whatever buying would have cost above the rent is invested instead.
        # When rent exceeds the instalment the gap is negative and the portfolio
        # is drawn down, which is the honest treatment: that money is really gone.
        portfolio += monthly_payment - rent
        total_rent += rent
        if month % 12 == 0:
            # Rents track inflation far more closely than they track a fixed
            # instalment; holding rent flat for 20 years would be the thumb on
            # the scale that makes buying always win.
            rent *= 1 + property_growth_pct / 100

    net_worth_renting = portfolio

    return OpportunityComparison(
        years=years,
        cash_invested=costs.cash_needed,
        total_mortgage_paid=round(total_mortgage_paid, 2),
        equity_at_horizon=round(equity, 2),
        property_value_at_horizon=round(property_value, 2),
        outstanding_balance=round(outstanding_balance_at_horizon, 2),
        net_worth_buying=round(net_worth_buying, 2),
        total_rent_paid=round(total_rent, 2),
        portfolio_at_horizon=round(portfolio, 2),
        net_worth_renting=round(net_worth_renting, 2),
        difference=round(net_worth_buying - net_worth_renting, 2),
        buying_wins=net_worth_buying > net_worth_renting,
    )


def balance_after(schedule: list[dict], horizon_years: int) -> float:
    """Outstanding principal after `horizon_years`, from an amortisation schedule."""
    idx = horizon_years * 12 - 1
    if idx < 0:
        return schedule[0]["balance"] if schedule else 0.0
    if idx >= len(schedule):
        return 0.0
    return float(schedule[idx]["balance"])
