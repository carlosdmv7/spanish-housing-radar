# ADR 0006 — Coalesce a zero-dispersion benchmark to a neutral z-score

**Status:** accepted

## Context
The Opportunity Score is a z-score: how many standard deviations a listing's
€/m² sits from its benchmark's median. ADR 0004 guarantees the benchmark has at
least `min_comps_for_benchmark` comparables *when a grain qualifies*, but the
city grain is the terminal fallback — it is used whether or not it clears the
threshold. A city × operation × property type cell can therefore hold a single
listing, and `stddev_pop` over one row is **0** (or NULL when the join misses).

That divisor is where the score becomes dangerous. With `stddev = 0` the ratio
`(price_per_sqm − median) / 0` is undefined; in DuckDB the raw division raises,
and the obvious defensive fix — `nullif(stddev, 0)` alone — yields NULL, which
then propagates into a NULL score the app has to special-case everywhere.

The tempting third option is to let the clamp absorb it: treat the undefined
ratio as "infinitely far from the median" and let `greatest(-3, least(3, …))`
snap it to ±3. That is the worst of the three. A single-comparable benchmark is
a listing being compared **against itself**: `price_per_sqm − median` is exactly
0, there is no evidence of anything, and yet the row would emerge as a hard
`-3` → **score 100 → `great_deal`**. The pipeline would manufacture its most
confident possible verdict out of its least possible evidence, and it would do
it precisely in the thin, sparse cells where nobody is checking. One row of data
would become a headline bargain on the Opportunities page.

## Decision
Divide by `nullif(benchmark_stddev_ppsqm, 0)` and `coalesce` the result to
**0** — a neutral z-score — before clamping
(`transform/models/3_gold/fct_listings_scored.sql`, `with_zscore`):

```sql
greatest(-3.0, least(3.0,
    coalesce(
        (price_per_sqm - benchmark_median_ppsqm)
        / nullif(benchmark_stddev_ppsqm, 0),
        0
    )
))
```

A benchmark with no dispersion produces `z = 0` → **score 50 → `fair`**. The row
is still emitted, still carries its `benchmark_level` and `benchmark_comp_count`,
and is still caught by `low_confidence_flag` (ADR 0005) whenever the city grain
is thin — so the weakness is disclosed rather than encoded in the number.

## Consequences
- **The failure mode is now a shrug, not a lie.** Absent evidence scores at the
  midpoint. A 50 is wrong in the sense that it is uninformative; a fabricated
  100 would be wrong in the sense that it sends someone to view a flat.
- The score is defined for every row, so `opportunity_score` stays `not_null`
  under the gold contract and no downstream surface needs a NULL branch.
- **A 50 is now ambiguous by construction:** it means either "genuinely at the
  median" or "no dispersion to measure against". The two are indistinguishable
  from the score alone, which is exactly why ADR 0005's rule — never show a
  score without its grain and comparable count — is load-bearing here rather
  than merely nice. `benchmark_comp_count = 1` is what separates the two cases.
- It biases the deal-tier distribution toward `fair` in sparse cities. That is a
  reported symptom of thin data, not a modelling artefact to be tuned away — the
  freshness header's neighbourhood-grain share is where it should be read.
- The clamp at ±3 survives for its intended job: capping genuine outliers
  (a mispriced garage, a data-entry error) at a bounded score, on benchmarks
  that do have dispersion.

## Alternatives rejected
- **Let the clamp snap it to ±3.** Fabricates `great_deal` / `very_overpriced`
  verdicts from single-comparable benchmarks. This is the decision's whole
  motivation; it is rejected outright.
- **Emit NULL for the score.** Honest, but pushes a three-state score (good /
  bad / unknown) into every consumer — the map, the ranking, the deal-tier
  chart, the contract. The neutral value plus the existing confidence flags
  carries the same information at a fraction of the surface area.
- **Drop rows with a degenerate benchmark.** Rejected by ADR 0005: the listing
  exists, and silently omitting it makes the app claim coverage it lacks.
- **Fall back to a coarser dispersion** (e.g. the city σ when the barrio σ is 0).
  There is no coarser grain than city — it *is* the fallback. A national σ would
  mean benchmarking a Valencia flat's spread against Madrid's, which is not a
  comparable set in any sense the product claims.
- **Lower `min_comps_for_benchmark` so more cells qualify.** Solves nothing: the
  threshold governs which grain is chosen, not whether the terminal city grain
  has data. It would also manufacture confidence, per ADR 0004.
