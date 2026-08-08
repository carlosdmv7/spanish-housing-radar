# ADR 0007 — Repair scraped locations in silver, and let evidence outrank the pattern

**Status:** accepted

## Context
ADR 0001 buys coverage by scraping search cards, which means the only location
information available is the listing title, and Idealista titles do not label
their segments. `_parse_location` therefore guesses which comma-separated part is
an area — and it guessed wrong often enough that the warehouse accumulated
barrios called `34`, `7 -5`, `chalet adosado en russafa` and
`piso en calle dels vivons`, plus districts called `12` and `29`.

Two consequences made this worse than a display defect:

* `fct_listings_scored` groups by `neighborhood` to build the barrio benchmark.
  A street name is a perfectly valid grouping key, so the pipeline was capable of
  publishing a "neighbourhood benchmark" for a place that does not exist.
* When a street landed in `neighborhood`, the **real** barrio was pushed one slot
  along into `district`. Russafa held 11 correctly-parsed listings and 4 more
  filed under a street name, and those 4 fell all the way to city grain — flats
  in Russafa scored against the whole of València.

None of the 89 existing tests caught any of it. They assert ranges, uniqueness
and nullity, all of which garbage satisfies perfectly.

A `neighborhood_is_canonical` flag already existed, set by a lookup against the
`barrios_es` seed, and 42% of rows were flagged false. Nothing consumed it.

## Decision
Fix the parser, but treat the parser as the *second* line of defence rather than
the only one.

1. **Keep the source text.** `raw.idealista_listings` gains `raw_title`. A
   heuristic that discards its input cannot be corrected: with the title gone,
   the 646 existing rows could not be re-derived at any price short of
   re-scraping them.
2. **Repair in silver, not at extraction.** Silver rebuilds from raw on every
   `dbt build`, so a fix to the repair logic is *retroactive*. A fix to the
   Python parser only ever helps rows scraped afterwards.
3. **Consult the seed first; let the pattern judge only what the seed cannot
   confirm.** The `is_not_an_area` macro rejects streets, portal numbers and
   property types — but "Carretera de Cádiz" is one of Málaga's eleven official
   districts, and the first version of this test threw it and its ten listings
   away for containing the word *carretera*. Positive evidence outranks a
   pattern in both directions.
4. **Probe the seed against both the neighbourhood and the district slot.** This
   is what recovers the mis-shifted rows without re-scraping one of them.
5. **Split the flag in two.** `neighborhood_is_canonical` answers "did a source
   confirm this is a real barrio?" and drives displayed confidence.
   `neighborhood_is_benchmarkable` answers "may this form a barrio benchmark?"
   and gates the grain.

## Consequences
- Obvious garbage in the neighbourhood column fell from 35 rows to 1, and 19
  listings moved from city grain to a finer one.
- **The barrio grain barely moved: 44 → 45 of 646.** The parsing was never the
  binding constraint; density is. The best blocked group has 7 comparables
  against a threshold of 8, and Valladolid's Centro splits 6 sale / 6 rent. This
  is the single most useful thing measuring the fix revealed, and it points all
  future effort at scraping depth rather than breadth.
- A location error is now visible instead of silent: `assert_no_streets_as_barrios`
  fails the build.
- `raw_title` makes every future parser improvement retroactive — but only for
  rows scraped from now on. The existing 646 predate the column and can only be
  repaired by the seed lookup.
- The seed is now load-bearing in a way it was not designed for, and it covers
  five cities. That gap is handled explicitly (below) rather than silently.

## Alternatives rejected
- **Gate the benchmark on `neighborhood_is_canonical`.** The first
  implementation, and wrong. The seed holds Madrid, València, Barcelona, Málaga
  and Sevilla and not one row for Bilbao, Valladolid or Zaragoza, so it converts
  "our reference data has never heard of this city" into "this is not a real
  barrio" — disqualifying Valladolid's Centro (12 listings) and Bilbao's
  Ensanche-Moyua for a defect in *our* data rather than theirs. Measuring the
  change is what exposed it; it looked correct in review.
- **Fix only the Python parser.** Cheaper, and it leaves every existing row
  broken forever, since raw no longer holds what they were parsed from.
- **Drop rows whose location cannot be confirmed.** Would make the barrio grain
  look trustworthy by deleting the evidence of how thin it is. ADR 0005 rejects
  exactly this trade.
- **Expand the seed from the observed data.** Tempting — most unconfirmed names
  *are* real barrios — but it launders the pipeline's own output into the
  reference data that validates it, and the coordinates would have to be
  invented. The seed must grow from an external source (INE or catastro barrio
  geometries), which is tracked as real work rather than done by hand here.
- **Lower `min_comps_for_benchmark` so more barrios qualify.** Would turn a
  measured coverage weakness into a manufactured strength. ADR 0004 already
  rejects this and the measurement above is the reason it keeps being tempting.
