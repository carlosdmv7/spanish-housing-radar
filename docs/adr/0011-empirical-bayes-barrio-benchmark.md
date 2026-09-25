# ADR 0011 — Trust a barrio as far as its data earns: empirical-Bayes weights

**Status:** accepted · refines [ADR 0004](0004-hierarchical-benchmark-grain.md)

## Context
ADR 0004 picked the finest grain with at least 8 comparables: a barrio with 8
listings was the whole benchmark, a barrio with 7 counted for nothing. The
cut-off was a guess about how much a barrio median can be trusted, and it was
never checked.

Checked on València (2026-09-25, apartments): listings vary within a barrio far
more than barrios differ within a district. For sales, the ratio of the two
variances — the shrinkage constant k — was about 6 (3.6–11 depending on which
barrios inform it). A barrio of 8 therefore carries roughly 57% signal, not
100%, and one of 5 carries 45%, not 0. For rents the between-barrio variance
within a district was indistinguishable from noise at every cut: a barrio's rent
median says nothing its district's does not.

## Decision
`fct_listings_scored` keeps ADR 0004's parent area — the district when it has
8+ comparables, else the city — and lets the barrio move the benchmark towards
its own median by an empirical-Bayes weight:

    benchmark = w · barrio median + (1 − w) · parent median,   w = n / (n + k)

The spread blends the same way, as variances. k is estimated on every build,
per city × operation × property type, by the method of moments over barrios
with 3+ listings. No k, so no barrio weight, when fewer than 5 barrios inform it
or when the between-barrio variance is not positive.

`benchmark_level` names the area carrying most of the weight (the barrio when
w ≥ 0.5). `barrio_weight` and `shrinkage_k` record the exact blend.

## Consequences
- Barrios of 3–7 listings contribute instead of being ignored; barrios of 8–15
  stop being trusted as if they were exact. Sale listings scored mostly on
  their own barrio went from 61% to about 75%.
- Rents are scored against their district. That is what the data supports, and
  the app says so rather than implying a barrio comparison it cannot make.
- Fewer extreme scores. The blended spread is larger and more honest than a
  small barrio's own, so fewer listings reach "great deal". On 2026-09-25, sale
  great deals in València went from 9 to 3.
- k moves with the data. It is shown, live, on How it works, so a change in the
  method's behaviour is visible without reading SQL.

## Alternatives rejected
- **Keep the cut-off and tune it.** Any single number is wrong for most barrios:
  too trusting just above it, too dismissive just below.
- **A fixed k.** Simpler, but it hides the rent finding. The point of estimating k
  is that the data can say "barrios here do not differ".
- **A full hierarchical model (PyMC, a Stan fit).** Better estimates for a few
  hundred listings, but out of reach of a dbt build and far harder to explain on
  one page. The method of moments is ten lines of SQL.
