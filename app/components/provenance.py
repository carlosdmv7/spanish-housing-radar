"""
Score provenance — the words that say what a score was measured against.

ADR-0005 makes this a correctness requirement, not a nicety: any surface that
shows an opportunity score must also show the grain it was computed at and how
many comparables backed it. A score of 82 against 9 city-wide flats and a score
of 82 against 60 flats in the same barrio are not the same claim.

This module used to also render a whole listing card. The Deals page now shows
listings as a ranked table with one detail card, built in the view, so only the
shared wording lives here.
"""
from __future__ import annotations

# Wording for each benchmark grain: what the listing was compared against, and
# the noun for the median shown next to it.
GRAIN_WORDING: dict[str, tuple[str, str]] = {
    # "Benchmark", not "median": since ADR-0011 the number is the parent area's
    # median pulled towards the barrio's, so calling it either median was wrong.
    "neighbourhood": ("its own barrio", "Barrio benchmark"),
    "district": ("its district", "District benchmark"),
    "city": ("the whole city", "City benchmark"),
}


def _grain_wording(level: str) -> tuple[str, str]:
    return GRAIN_WORDING.get(level, (f"the {level} level", "Benchmark"))


def confidence_note(row: dict) -> str | None:
    """
    Why this particular score deserves less trust, or None when it doesn't.

    Two separate weaknesses, deliberately worded differently: falling back off
    barrio grain (coarse comparison) and the model's own `low_confidence_flag`
    (thin city grain). The second is worse and says so.
    """
    level = row.get("benchmark_level", "city")
    comps = int(row.get("benchmark_comp_count") or 0)

    if row.get("low_confidence_flag"):
        return (
            f"**Low confidence** — only {comps} comparable listings city-wide, "
            "below the 8 this benchmark needs. Treat the score as a hint, not a verdict."
        )
    if level != "neighbourhood":
        compared_to, _ = _grain_wording(level)
        return (
            f"**Reduced confidence** — the score mostly reads {compared_to}: this "
            "barrio has too few listings, or differs too little from its district, "
            "to carry the benchmark. It reads the market, not the street."
        )
    return None
