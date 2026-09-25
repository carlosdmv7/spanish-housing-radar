-- Fails if a benchmark lies outside the two medians it blends (ADR-0011).
--
-- The empirical-Bayes benchmark is w · barrio + (1 − w) · parent with w in
-- [0, 1], so it can only ever sit between the barrio's median and its parent
-- area's. A value outside that interval means the weight or one of the medians
-- was joined from the wrong row — the kind of error that still produces a
-- plausible-looking score, and that no range test on the score would catch.
select
    listing_pk,
    barrio_weight,
    barrio_median_ppsqm,
    parent_median_ppsqm,
    benchmark_median_ppsqm
from {{ ref('fct_listings_scored') }}
where barrio_weight > 0
  and (benchmark_median_ppsqm < least(barrio_median_ppsqm, parent_median_ppsqm) - 0.01
    or benchmark_median_ppsqm > greatest(barrio_median_ppsqm, parent_median_ppsqm) + 0.01)
   or (barrio_weight = 0 and abs(benchmark_median_ppsqm - parent_median_ppsqm) > 0.01)
