"""
App-wide constants: colours, labels, default values.
Single source of truth — import from here, never hardcode elsewhere.
"""
from __future__ import annotations

# ── Deal tier ─────────────────────────────────────────────────────────────────
DEAL_TIER_COLORS: dict[str, str] = {
    "great_deal":      "#22c55e",
    "good_deal":       "#84cc16",
    "fair":            "#f59e0b",
    "overpriced":      "#f97316",
    "very_overpriced": "#ef4444",
}

DEAL_TIER_LABELS: dict[str, str] = {
    "great_deal":      "🟢 Great deal",
    "good_deal":       "🟡 Good deal",
    "fair":            "⚪ Fair price",
    "overpriced":      "🟠 Overpriced",
    "very_overpriced": "🔴 Very overpriced",
}

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
PAGE_ICON  = "🏠"
ACCENT     = "#2563eb"