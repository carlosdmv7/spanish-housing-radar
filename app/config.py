"""
App-wide constants: colours, labels, default values.
Single source of truth — import from here, never hardcode elsewhere.
"""
from __future__ import annotations

from pathlib import Path

from theme import AMBER_500, INK_MUTED, RUST_500, RUST_900, TEAL_500, TEAL_700

# ── Deal tier ─────────────────────────────────────────────────────────────────
# The five tiers are an ordered diverging axis, so they take the brand's
# diverging ramp: teal = below benchmark, rust = above. Never a green→red scale.
DEAL_TIER_COLORS: dict[str, str] = {
    "great_deal":      TEAL_700,
    "good_deal":       TEAL_500,
    "fair":            AMBER_500,
    "overpriced":      RUST_500,
    "very_overpriced": RUST_900,
}

# No coloured-circle emoji: they would assert a green/red palette the charts and
# map deliberately don't use, and the two would disagree on screen.
DEAL_TIER_LABELS: dict[str, str] = {
    "great_deal":      "Great deal",
    "good_deal":       "Good deal",
    "fair":            "Fair price",
    "overpriced":      "Overpriced",
    "very_overpriced": "Very overpriced",
}

DEAL_TIER_FALLBACK_COLOR = INK_MUTED

# ── Property type ─────────────────────────────────────────────────────────────
PROPERTY_TYPE_LABELS: dict[str, str] = {
    "apartment": "Apartment / Flat",
    "house":     "House / Villa",
    "other":     "Other",
}

# ── Operations ────────────────────────────────────────────────────────────────
OPERATION_LABELS: dict[str, str] = {
    "sale": "Buy",
    "rent": "Rent",
}

# ── Economic assumptions: provenance ──────────────────────────────────────────
# Every rate and income default below is a published figure with a citation and
# a consultation date, not a plausible-looking round number. The app's whole
# claim is that it is honest about where its numbers come from; a mortgage
# simulator running on undocumented constants would break that claim on the two
# pages where a visitor is most likely to act on the output.
#
# The *_SOURCE strings are what the Mortgage and Affordability pages render in a
# caption, so the citation and the constant it describes live in one place and
# cannot drift apart. Refresh both together, and move the date.
SOURCES_CONSULTED_ON = "2026-07-30"

# ── Mortgage defaults ─────────────────────────────────────────────────────────
# Banco de España, "tipo medio de los préstamos hipotecarios a más de tres años
# para adquisición de vivienda libre, conjunto de entidades de crédito" —
# an official reference rate published monthly in the BOE. June 2026: 3.049%.
# Resolución de 17/07/2026 (BOE-A-2026-15738). Consulted 2026-07-30.
MORTGAGE_DEFAULT_RATE_FIXED:    float = 3.0

# The bank's spread over Euribor on a variable mortgage. This is the one number
# here with NO official source: no supervisor publishes an average commercial
# differential, because it is negotiated per customer. Spanish comparators put
# 2026 offers at roughly +0.8 to +1.2 pp, so this is the midpoint of an observed
# market range, not a statistic — and it is labelled as such in the app.
# Consulted 2026-07-30.
MORTGAGE_DEFAULT_RATE_VARIABLE: float = 1.0

# 12-month Euribor, last *closed* monthly average — the figure Spanish variable
# mortgages actually reset against. Source: EMMI, published by Banco de España.
# June 2026: 2.795%. The in-progress month is deliberately not used: it is
# provisional and no loan is revised on it. Consulted 2026-07-30.
EURIBOR_CURRENT:                float = 2.8

# Conventional Spanish mortgage terms — the modal product, not a measured
# statistic. 30 years is the standard maximum term offered to a median borrower
# and 80% LTV is the regulatory/commercial norm for a primary residence
# (Banco de España flags lending above 80% LTV as higher-risk).
MORTGAGE_DEFAULT_YEARS:         int   = 30
MORTGAGE_DEFAULT_LTV:           float = 80.0

# ── Affordability ─────────────────────────────────────────────────────────────
# INE, Encuesta Anual de Estructura Salarial 2024 (definitive data published
# 2026-05-28): mean annual gross earnings per worker in the Comunitat
# Valenciana. Consulted 2026-07-30.
VALENCIA_AVG_GROSS_SALARY_ANNUAL: float = 26_817.0

# Gross → net is OUR approximation, not an INE figure: employee social-security
# contributions (~6.5%) plus an effective IRPF rate of ~13% at this income, for
# a single filer with no dependants. Kept as an explicit factor rather than
# folded into a magic number so the derivation is auditable and arguable.
_NET_OF_GROSS_APPROX: float = 0.805

# Monthly net over 12 payments (Spanish payrolls often use 14; 12 is the
# conservative reading for servicing a monthly mortgage). ≈ €1,800.
VALENCIA_AVG_NET_SALARY_MONTHLY: float = round(
    VALENCIA_AVG_GROSS_SALARY_ANNUAL * _NET_OF_GROSS_APPROX / 12, -1
)

# Spanish lenders' rule of thumb for the maximum share of net income committed
# to debt service. A supervisory guideline repeated in Banco de España's
# borrower guidance, not a legal cap.
AFFORDABILITY_RATIO_MAX:         float = 35.0

# Housing-cost overburden: the share of disposable household income above which
# Eurostat (and INE, which reports the same indicator for Spain) classes a
# household as overburdened by housing. A statistical convention, not a rule any
# lender applies — it describes households, whereas AFFORDABILITY_RATIO_MAX
# above describes what a bank will underwrite.
OVERBURDEN_PCT:                  float = 30.0

# ── Source notes rendered in the app ──────────────────────────────────────────
MORTGAGE_SOURCE_NOTE = (
    f"**Where these defaults come from** — Fixed rate {MORTGAGE_DEFAULT_RATE_FIXED:.2f}%: "
    "Banco de España's official reference rate for mortgages over 3 years on free-market "
    "housing (3.049%, June 2026, BOE-A-2026-15738). "
    f"Euribor {EURIBOR_CURRENT:.2f}%: EMMI 12-month Euribor, last closed monthly average "
    "(2.795%, June 2026). "
    f"Bank spread {MORTGAGE_DEFAULT_RATE_VARIABLE:.2f}%: no official statistic exists — "
    "differentials are negotiated per customer, so this is the midpoint of the +0.8–1.2 pp "
    "range Spanish comparators advertised in 2026. "
    f"All consulted {SOURCES_CONSULTED_ON}. Every one of them is an input you can change "
    "above; your bank's offer is the only rate that binds you."
)

AFFORDABILITY_SOURCE_NOTE = (
    f"**Where these defaults come from** — Income €{VALENCIA_AVG_NET_SALARY_MONTHLY:,.0f}/month: "
    f"INE Encuesta Anual de Estructura Salarial 2024 (definitive, published 2026-05-28), mean "
    f"gross earnings in the Comunitat Valenciana of €{VALENCIA_AVG_GROSS_SALARY_ANNUAL:,.0f}/year, "
    "converted to net by us (≈6.5% social security + ~13% effective IRPF, single filer, no "
    "dependants) over 12 payments — the net figure is our arithmetic, not an INE statistic. "
    f"Mortgage rate {MORTGAGE_DEFAULT_RATE_FIXED:.2f}%: Banco de España official reference rate "
    "for mortgages over 3 years (3.049%, June 2026, BOE-A-2026-15738). "
    f"Ratio {AFFORDABILITY_RATIO_MAX:.0f}%: Spanish lenders' debt-service guideline, not a legal "
    f"cap. All consulted {SOURCES_CONSULTED_ON}. Override any of them in the sidebar."
)

# ── UI ────────────────────────────────────────────────────────────────────────
PAGE_TITLE = "Spanish Housing Radar"
# The portfolio's own favicon, copied in rather than an emoji house: the browser
# tab is the one piece of chrome a visitor sees before the page paints, and it
# should show the same mark as carlosdmv7.github.io. Kept in sync by hand — it
# is 8 KB and changes about once a year.
PAGE_ICON  = str(Path(__file__).parent / "assets" / "favicon.png")
