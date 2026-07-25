"""
App-wide constants: colours, labels, default values.
Single source of truth — import from here, never hardcode elsewhere.
"""
from __future__ import annotations

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

# ── Mortgage defaults ─────────────────────────────────────────────────────────
MORTGAGE_DEFAULT_RATE_FIXED:    float = 3.0
MORTGAGE_DEFAULT_RATE_VARIABLE: float = 1.5
EURIBOR_CURRENT:                float = 2.5
MORTGAGE_DEFAULT_YEARS:         int   = 30
MORTGAGE_DEFAULT_LTV:           float = 80.0

# ── Affordability ─────────────────────────────────────────────────────────────
VALENCIA_AVG_NET_SALARY_MONTHLY: float = 1_650.0
AFFORDABILITY_RATIO_MAX:         float = 35.0

# ── UI ────────────────────────────────────────────────────────────────────────
PAGE_TITLE = "Spanish Housing Radar"
PAGE_ICON  = "🏘️"
