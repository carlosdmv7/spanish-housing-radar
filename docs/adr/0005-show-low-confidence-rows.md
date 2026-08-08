# ADR 0005 — Show low-confidence rows, flagged, rather than dropping them

**Status:** accepted

## Context
ADR 0004 leaves some listings scored against a thin city grain. The tempting move
is to filter them out of the app: every remaining row would then carry a
well-supported score and the product would look finished. But the rows do not stop
existing — dropping them makes the app quietly claim coverage it does not have,
and a visitor comparing it against Idealista would find flats missing with no
explanation. For a portfolio piece whose subject *is* data trust, hiding the weak
rows is the one unrecoverable mistake.

## Decision
Never filter on confidence in the transformation layer. `fct_listings_scored`
computes `low_confidence_flag` (city grain **and** fewer than
`min_comps_for_benchmark` comparables) and ships every row to gold. The app shows
flagged rows inline, in the same place as the score — grain and comparable count
next to the number, not in a footnote — and offers "hide low-confidence" as an
opt-in filter the visitor controls, defaulting to **off**. The freshness header
publishes the share of listings scored at neighbourhood grain versus city
fallback, so the aggregate weakness is visible before any listing is opened.

## Consequences
- Coverage claims stay honest and the app's own limitations are legible from the
  first screen.
- The visitor, not the pipeline, decides what confidence is good enough for their
  search.
- Some visible scores are genuinely weak. That is a **presentation**
  responsibility: any surface showing a score must also show its grain, or this
  decision silently reverts to the dishonest version.
- The share of neighbourhood-grain rows becomes a headline data-quality metric —
  it goes up with scraping volume, and the header will show it falling if the
  pipeline stalls.
- `low_confidence_flag` marks only the *thin* city grain. A city grain with ≥ 8
  comparables is not flagged by the model, so the app additionally discloses any
  fallback from neighbourhood grain as reduced confidence.

## Alternatives rejected
- **Filter low-confidence rows out of the app.** The version that looks
  finished. Rejected because the missing rows are invisible by construction: a
  visitor cannot audit an absence, so the app would be making a coverage claim it
  cannot support and the visitor cannot check. This is the specific failure the
  project is a rebuttal to.
- **Filter them out by default, with an opt-in to show them.** The same
  dishonesty with an escape hatch most people never open. Defaults are the
  product; a caveat reachable only by the already-suspicious is not disclosure.
  The filter exists, defaulted to off, which is the same mechanism pointed the
  other way.
- **Show every row but grey out or de-emphasise the weak ones.** Rejected
  because it communicates "less important" when the truth is "less certain" —
  a cheap flat scored on a thin benchmark may be the most interesting row on the
  page, and it is the *score* that deserves the caveat, not the listing. The
  grain and comparable count sit next to the number instead.
- **Suppress the score, keep the listing.** Honest, and briefly tempting. But
  a blank where a score should be tells the visitor nothing about how blank it
  is, and it discards a real if weak signal. A city-grain score answers a weaker
  question; the fix is to state the question, not to refuse to answer.
