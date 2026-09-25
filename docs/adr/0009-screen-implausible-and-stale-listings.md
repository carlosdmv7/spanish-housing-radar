# ADR 0009 — Set aside implausible and stale listings, and show them

**Status:** accepted · amended 2026-09-25 (see the end)

## Context
Bronze drops what is impossible row by row: no price, no size, more than
€50,000/m². Two kinds of bad row got through anyway.

- **Typos.** A one-bedroom rent in Russafa at €1,300 a month for 707 m² —
  €1.84/m² against a city median near €17 — was València's top-scoring "great
  deal". It was a typo for 70 m². It also widened its barrio's spread, which
  flattened every other rent score there. No row-level rule catches it: Aravaca
  has a real 775 m² house, and €1,300 is a normal rent.
- **Stale listings.** `int_listings_current` holds the latest snapshot of every
  listing ever seen. With a pipeline paused over the summer, 83 València
  listings last seen in May and June were still served as "right now".

ADR 0005 says never filter on *confidence*. Neither of these is a confidence
problem: a thin benchmark is a weak answer to a real question, a typo is not a
flat at all, and a withdrawn listing is not on the market.

## Decision
`int_listings_screened` gives every current listing a `dq_issue`:

- `implausible_price_per_sqm` — under a quarter of, or over four times, the
  median €/m² of its city and operation (`max_ppsqm_ratio_to_city`). A typo in
  either the price or the size moves €/m² by an order of magnitude; no real flat
  in one city is that far from its typical flat.
- `not_seen_recently` — unseen for `max_listing_age_days` (60) before the
  city's own latest scrape. Measured from the last scrape, not from today, so a
  paused pipeline does not empty the app.

Everything downstream reads `int_listings_valid`, the rows with no issue — one
place, so no consumer can forget the filter. The set-aside rows stay in
`int_listings_screened`, and How it works lists them with the reason: a visitor
can audit what was removed, which is the part of ADR 0005 that matters.

A warn-level test fires when more than 3% of a city's listings for one
operation are implausible: a few typos are the portal's, a flood is our parser.

## Consequences
- The typo stops being the top deal and stops distorting its neighbours.
- "Right now" means seen within two months of the latest scrape, and each deal
  shows the date it was last seen.
- A real outlier beyond a factor of four — a castle, a garage sold as a flat —
  is set aside too. At a few hundred listings per city this is rare, and it is
  shown, not lost.

## Alternatives rejected
- **Absolute bounds on size or €/m².** Either loose enough for Madrid's houses
  and too loose for València's flats, or the reverse.
- **Flag, keep in the benchmark.** The damage is to the benchmark itself.
- **Tighter bounds (a factor of three).** Would catch a real €10,000/month
  penthouse in Málaga's Pacífico at 3.0× the city. The rule is for errors,
  not for the expensive end of the market.

## Amendment (2026-09-25)
`not_seen_recently` was first measured from each city's own latest scrape.
That kept a one-off June 2026 snapshot of seven other cities "current" three
months later, and the app served its flats as today's deals. It is now measured
from the warehouse's latest scrape of any city. A paused pipeline still does not
empty the app, and a city the pipeline no longer visits ages out like any
listing that stopped being seen, staying in the history.
