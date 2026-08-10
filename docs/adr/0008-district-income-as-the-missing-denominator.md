# ADR 0008 — Ground prices in district income, at district grain, from a bulk CSV

**Status:** accepted

## Context
Every figure in this warehouse compares a flat to other flats. That answers *is
this cheap for the area?* and cannot answer *is this area cheap?* — a barrio can
be inexpensive because it is a bargain or because nobody living there can pay
more, and €/m² does not distinguish those. The product's central claim is about
value, and it had no denominator.

Listing prices also share a weakness: they evaporate. An advert comes down and
the evidence goes with it, which is why a paused scraper leaves the warehouse
ageing. Official income does not behave that way.

## Decision
Ingest INE's **Atlas de Distribución de Renta de los Hogares** (ADRH, table
30824) and publish `rpt_district_affordability`: median asking price and €/m²
per district alongside median household income, plus the ratio between them —
years of household income to buy outright for sales, and rent as a percentage of
household income for rentals.

Three sub-decisions carry most of the weight.

**Bulk CSV, not the API.** The Tempus3 JSON API cannot serve this table:
unfiltered it returns `"No puede mostrarse por restricciones de volumen"`, and
every documented `tv=` filter combination returns HTTP 500. The 64 MB bulk export
is the only route that works. It is streamed and filtered against a set of INE
municipality codes, discarding ~99.9% of three million rows.

**District grain, not census section.** ADRH publishes sections too, which are
finer than any location this app holds. Ingesting them would multiply the table
twentyfold for data nothing can join to.

**The district mapping is seeded from the Ajuntament, not inferred.** INE says
"València distrito 01"; a listing says "ciutat vella". Nothing in either dataset
connects them. The mapping in `ine_districts.csv` comes from València's own
published list of its 19 districts. Deriving it from the data would mean deciding
which barrio sits in which district using the very prices the join exists to
divide by income — circular, and unfalsifiable.

The headline ratio is deliberately **gross and unfinanced**. The moment a
mortgage rate enters, the number stops describing the district and starts
describing the borrower.

## Consequences
- The app can now say something €/m² never could. València's Eixample is among
  the dearest per m² (€5,000) yet takes **10.0 years** of local household income,
  while Camins al Grau is cheaper per m² (€4,769) and takes **15.4**. Price and
  affordability are not the same ranking.
- The feed is **annual and lagged ~2 years**, so the ratio mixes today's asking
  prices with a 2023 income. It reads as a direction, not a precise multiple, and
  the app says so rather than letting the precision imply currency.
- Source freshness for this table warns at 400 days, not 10. A normal publication
  gap must not turn the build red — but a feed that has genuinely stopped still
  surfaces.
- **València only, for now.** Every other city needs its own official district
  list first. The app states this rather than showing an empty table.
- `rpt_district_affordability` LEFT joins income, so a district with no figure
  keeps its row with a null ratio. Dropping it would silently shrink the table to
  the districts INE happens to cover — the omission ADR 0005 argues against.

## Alternatives rejected
- **Municipality-level income (table 31097), which the API *does* serve.**
  Immediate and useless: it says Madrid and Valladolid differ in income, which
  nobody needed a pipeline to learn. The signal is *within* a city, and that
  requires the grain the API refuses to give.
- **Fill the district seed for all eight cities from memory.** The fastest way to
  make the table look complete and the surest way to corrupt it: one wrong
  barrio-to-district assignment silently rewrites an affordability figure, and no
  test in this repo could catch it.
- **Infer districts from the listings themselves.** Same objection as above with
  extra circularity — the prices would be defining the geography they are then
  measured against.
- **Fold income into the opportunity score.** Tempting, and rejected: the score
  is a claim about *price relative to comparables*, and mixing a second axis into
  one number would make it unexplainable at exactly the moment the app has to
  justify it on a listing card. Income sits beside the score, not inside it.
- **Use gross income instead of net.** Larger numbers, worse meaning. What a
  household can service a mortgage from is what reaches its account.
