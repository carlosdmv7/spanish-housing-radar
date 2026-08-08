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

## Alternatives rejected
- **One fixed grain for everything.** City-wide is always well-populated and
  always answers the wrong question ("cheap for Valencia" is not "cheap for this
  street"). Barrio-only is the right question and unanswerable across most of the
  country. The fallback exists because the correct grain is a property of the
  *listing's own data density*, not of the project.
- **Barrio-only, dropping listings with too few comparables.** Rejected on the
  grounds ADR 0005 develops: the dropped rows do not stop existing, and an app
  that silently omits them claims a coverage it does not have.
- **Shrinkage toward the city median (empirical-Bayes style) instead of a hard
  cutoff.** Statistically the better answer, and honestly the one a larger team
  should build: it degrades smoothly rather than stepping at n=8, and it has no
  arbitrary threshold. Rejected here because the resulting score is not
  explainable to a visitor — "scored against 6 flats in your barrio, pulled 40%
  toward the city median" cannot be put next to a number on a card, and this
  product's whole claim is that its verdicts are auditable. A discrete
  `benchmark_level` can be shown; a shrinkage weight cannot.
- **k-nearest comparables by distance rather than by administrative boundary.**
  The right shape for a benchmark, and blocked upstream: ADR 0001 buys coverage
  at the cost of per-listing coordinates, so the finest location available *is*
  the barrio. This becomes possible only if detail-page scraping ever does.
- **A lower threshold than 8 to raise the barrio-grain share.** Rejected
  explicitly, and worth stating because it is the tempting metric fix: the number
  is a statistical floor, not a coverage dial. Lowering it manufactures
  confidence rather than earning it.
