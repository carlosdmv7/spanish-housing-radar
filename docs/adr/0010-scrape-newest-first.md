# ADR 0010 — Scrape the newest listings first

**Status:** accepted

## Context
The weekly run can afford four search pages per operation in València
(ADR-0001; Scrapfly credits). Those pages came in Idealista's default order,
"relevance", and relevance is sticky: of the 107 sale listings seen on
2026-09-22, 77 had already been seen in August. A week's credits bought about
30 new flats.

That was tolerable while every listing ever seen stayed "current". ADR-0009
set aside anything unseen for 60 days, which is right — a flat not seen for two
months is most likely gone — but with relevance ordering it would have shrunk
València's sale pool from ~460 to little more than one run's worth once the
August listings aged out, and taken most barrio benchmarks with it.

## Decision
Request every search page with `?ordenado-por=fecha-publicacion-desc`
(`IDEALISTA_SORT`, same credits). Each week then buys the newest page of the
market, and with the 60-day window the pool becomes roughly the last two months
of new listings: the set that is plausibly still for sale.

## Consequences
- The pool refills every week instead of re-reading the same flats; barrio
  benchmarks grow with scraping, not with how long the pipeline has run.
- A listing is rarely seen twice, so days on market and price cuts
  (`int_listing_lifecycle`) light up less often. Those signals were already thin
  — they need a listing to stay in the top four relevance pages for weeks — and
  a benchmark with enough comparables is worth more than a motivation badge on
  a handful of flats.
- The sample leans towards the newest listings. A newly listed flat has not
  had a price cut yet, so asking prices may read slightly higher than the
  market's average listing. The INE index on Neighbourhoods is the check.

## Alternatives rejected
- **More pages.** Same effect, several times the credits.
- **Split: some pages by relevance, some by newest.** Keeps a trickle of
  re-sightings for the lifecycle signals, at the cost of halving the new
  listings. Revisit if a deeper budget ever makes re-sighting cheap.
- **A longer stale window (90+ days).** Keeps the pool large by keeping flats
  that have most likely sold — the problem ADR-0009 exists to fix.
