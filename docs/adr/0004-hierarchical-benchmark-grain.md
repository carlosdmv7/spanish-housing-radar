# ADR 0004 — Hierarchical benchmark grain with fallback

**Status:** accepted

## Context
The Opportunity Score compares a listing's €/m² against the median of comparable
listings. The *right* comparison set is the flat's own barrio — that is the whole
premise of the product. But Spanish listing data is sparse at barrio level: a
neighbourhood holding two listings cannot benchmark anything, because the flat is
effectively being compared against itself. The z-score collapses to ~0 and every
such flat scores a meaningless "fair" 50, which is worse than useless — it looks
like a real verdict.

## Decision
Build three benchmark grains in `fct_listings_scored`, always within the same
`operation_type × property_type`, and per listing pick the **finest grain holding
at least `min_comps_for_benchmark` comparables** (dbt var, default **8**):

```
neighbourhood  →  district  →  city (municipality)
```

Each row records which grain actually scored it (`benchmark_level`) and how many
comparables stood behind it (`benchmark_comp_count`), and both are surfaced in the
app per listing. Where a benchmark has no price dispersion (a single comparable →
`stddev` 0 or NULL), the z-score is coalesced to 0 rather than snapping to ±3.

## Consequences
- The score is meaningful everywhere data exists, instead of being right in
  Valencia and silently degenerate elsewhere.
- **Grain is per-row, not per-city**, so two listings on the same street can be
  scored at different grains. `benchmark_level` is part of the gold contract and
  the app must always show it — a score without its grain is not interpretable.
- A city-grain score answers a weaker question ("cheap for this city") than a
  barrio-grain one ("cheap for this street"). ADR 0005 covers how that is
  disclosed rather than hidden.
- The threshold is a **statistical** floor, not a coverage dial: lowering it to
  make more rows look barrio-scored would manufacture confidence. The fix for
  city-grain dominance is sustained scraping.
- 8 is a judgement call, not a derived optimum, and it is one `vars` edit to
  revisit.
