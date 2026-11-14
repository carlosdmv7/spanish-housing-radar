# ADR 0013 — Towns around València: one area search, benchmarked within their comarca

**Status:** accepted · extends [ADR 0004](0004-hierarchical-benchmark-grain.md) and [ADR 0011](0011-empirical-bayes-barrio-benchmark.md)

## Context
The owner is buying in the towns north and west of València — l'Horta Nord and
Camp de Túria (Burjassot, Godella, Paterna, Moncada, Alboraia, Puçol, Llíria,
Bétera, L'Eliana, Riba-roja…), sale only. Two constraints shape everything:

- **Credits.** Free Scrapfly tier, 1 000 credits a month. A search page was 25
  credits (ADR-0001); on 2026-11-14 it billed **30** (25 proxy + 5 browser).
  That is ~33 pages a month, ~7 a weekly run. One municipality URL per town is
  ~40 towns × 30 credits: the month in a single run.
- **Thin data.** A town gets a handful of listings a month and has no barrio
  seed, so neither the barrio blend nor the city fallback of ADR-0004/0011 gives
  it a benchmark worth reading: its "city" median is three flats.

Idealista has no listing URL per comarca (none is linked from the
València-province results page, captured 2026-11-14). What it does have, and
links from every results page, is the "draw your area" search:
`/areas/venta-viviendas/?shape=((<encoded polyline>))`, the polygon a Google
encoded polyline (precision 5), percent-encoded twice in Idealista's own links.

## Decision
**Scrape plan.** The single global page count is replaced by `SCRAPE_TARGETS`
(`target:operation:pages`, comma-separated; a repo variable), one scraper
process per target. A target is a city slug or a zone in
`extraction/config.py: IDEALISTA_ZONES`. Default:

    horta-nord-camp-turia:sale:5, valencia:sale:1, valencia:rent:1
    = 7 pages ≈ 210 credits a run, ≈ 840 a month on four Mondays

`horta-nord-camp-turia` is one polygon over both comarcas plus Paterna, drawn
along the València city boundary and clear of Manises, Quart, Sagunt and the
Serranos, sorted newest first (ADR-0010). A card is kept only if its title's
municipality has a `comarca` in `transform/seeds/ccaa_by_municipality.csv` —
the same list the gold test `assert_gold_municipality_is_known_city` checks —
and the drops are counted (`cards_out_of_area`) in the scrape summary. Town
names are folded to the seed's spelling (Alboraya → alboraia, Puzol → puçol,
"Pobla de Farnals (La)" → la pobla de farnals). A page that only repeats cards
already seen stops the target, so a polygon search that ignores pagination
costs one wasted page, not four.

**Benchmark.** For a municipality the seed puts in a comarca, the same
empirical-Bayes blend one level up:

    benchmark = w · municipality median + (1 − w) · comarca median,  w = n / (n + k)

n is the town's listing count (same operation × property type). k is estimated
as in ADR-0011 — pooled within-town variance over between-town variance within
comarcas, from towns with ≥ `min_listings_for_barrio_weight` listings — per
operation × property type, pooled across the comarcas, and only when at least
`min_barrios_for_shrinkage` towns inform it; otherwise w = 0 and the comarca
median is the benchmark. `parent_level` is `comarca`; `benchmark_level` is
`municipality` when w ≥ 0.5, else `comarca`; the `barrio_*` columns carry the
town's figures; `low_confidence_flag` covers a thin comarca as it covers a thin
city. Rows outside a comarca take exactly the path they took before.

Paterna is officially l'Horta Oest. It is grouped with l'Horta Nord, the towns
it borders and is searched with: l'Horta Oest is not scraped, so on its own it
would be a comarca of one town.

## Evidence that València did not move
Built the gold model from `main` and from this change on sandbox schemas
(`horta_base_*`, `horta_new_*`) over the same raw data, 2026-11-14: all 1 231
València rows, every column, identical once doubles are rounded to 6 dp
(EXCEPT ALL both ways = 0); the score columns — opportunity_score,
ppsqm_z_score, barrio_weight, deal_tier, benchmark_level, comp count, flags —
hash to the same md5. The unrounded stddev/k columns differ in the last digit,
and so does a second build of `main` against the first: the warehouse's parallel
aggregation is not bit-reproducible, with or without this change.

## Consequences
- Towns get a benchmark from the first week: the comarca median, moving towards
  the town's own as listings accumulate and as far as the data says towns differ.
- One polygon is one sort order over the whole area: a busy town (Paterna) can
  take most of a week's cards. Splitting the zone, or adding a second target,
  is a variable change.
- The area URL and its page-2 form (`/areas/venta-viviendas/pagina-2?shape=…`)
  are Idealista's own shape but were not fetched live with this polygon before
  merge (the verification budget was one page). The first scheduled run is the
  check: `scrape_targets` in docs/status.json shows pages and cards per target.
- Card attributes, INE context and the app work unchanged; towns have no barrio
  map and no district income (ADR-0008 is València-only).
