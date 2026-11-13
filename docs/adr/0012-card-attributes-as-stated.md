# ADR 0012 — Keep the card's attributes, as the advertiser states them

**Status:** accepted · extends [ADR 0001](0001-search-card-scraping.md)

## Context
The opportunity score compares a listing's €/m² with its barrio's. It cannot
see the things that explain most of the price difference between two flats in
the same barrio: the floor, whether there is a lift, whether the flat faces the
street or an inner patio, whether a garage comes with it. The top "great deals"
sit 35–56% below their barrio, which is far more likely "a different kind of
flat" than "a cheap one". An attribute-adjusted benchmark needs those
attributes, with history behind them — and history only starts accumulating
from the first scrape that keeps them.

The search card already prints them and the scraper discarded them. In the
cached search page (`debug_output/`, 30 Madrid sale cards; both cached files
hold the same 30) the `.item-detail` spans and the rest of the card carry:

| What | Card text | Seen |
|---|---|---|
| Floor + orientation + lift, one span | `Planta 3ª exterior con ascensor` | 22 exterior, 3 interior (`Planta 6ª interior con ascensor`), all 25 `con ascensor` |
| No floor span | — | 5 (all houses / chalets) |
| Garage, included in the price | `Garaje incluido` | 11 |
| Garage, offered separately | `Garaje opc. 60.000 €` | 1 |
| The portal's price-drop marker | `<span class="pricedown_price">845.000 €</span>` + `<span class="pricedown_icon">3%</span>`, beside a current price of 820.000 € | 12 |
| Description snippet | `.item-description p`, already cut by Idealista at ~550 characters | 30 |
| Tags | `.listing-tags-container span`: `Lujo`, `Villa`, `Apartamento` | 15 cards, 1–2 tags |

Bathrooms are not on the card — `raw_bathrooms` is null in every row ever
loaded — and are not invented here. The cached page is one luxury Madrid
search, so `Bajo`, `Entreplanta`, `Sótano` / `Semi-sótano` and `sin ascensor` do
not occur in it; they are parsed from Idealista's known vocabulary and covered
by unit tests, not by observed pages.

## Decision
`IdealistaScraper` reads them into new optional `raw_*` columns:
`raw_floor`, `raw_floor_text`, `raw_is_exterior`, `raw_has_lift`, `raw_garage`
(`included` | `optional`), `raw_garage_price_eur`, `raw_garage_text`,
`raw_previous_price_eur`, `raw_price_drop_pct`, `raw_description`, `raw_tags`
(`|`-delimited). They flow to `rpt_opportunities` under the same names without
the prefix; the portal's marker becomes `portal_previous_price_eur` /
`portal_price_drop_pct`, to keep it apart from `price_change_pct`, which is
measured from our own snapshots.

**These are stated by the advertiser, and NULL means unstated.** Never `false`:
a card that does not mention a lift is not a flat without one, and a card that
does not mention a garage is not one without. Old rows are NULL because the
card was not read for these fields, which is the same statement.

**Floor encoding** — the storey as an integer, ground = 0:

| Card | `floor` |
|---|---|
| `Sótano`, `Semi-sótano` / `Semisótano` | −1 |
| `Bajo` | 0 |
| `Entreplanta` | 0 |
| `Planta Nª` (also `Planta -1`) | N |
| nothing stated (houses) | NULL |

Entreplanta is a mezzanine between bajo and 1ª; an integer cannot hold 0.5, and
it prices with the ground floor rather than the first. `floor_text` keeps the
span verbatim, so bajo, entreplanta, sótano and semi-sótano stay
distinguishable and a different encoding can be derived later without a
re-scrape.

**An optional garage is not in the asking price.** `garage = 'optional'` with
`garage_price_eur` says so; anything that compares prices should treat the two
cases differently.

**Migration.** The loader adds every new column with `ALTER TABLE … ADD COLUMN
IF NOT EXISTS` before each upsert, as `raw_title` was added, so the first
scheduled scrape migrates `raw.idealista_listings` itself and every existing
row keeps NULL. The bronze model reads the raw columns through
`column_or_null`, which emits a typed NULL while a column does not exist yet,
so `dbt build` compiles to the same columns before and after that migration
and no deploy ordering is needed. The incremental models carrying them
(`stg_idealista__listings`, `int_listings_unioned`, `int_listings_current`) use
`on_schema_change='append_new_columns'`: the columns are added in place, the
snapshot history is kept, and nothing needs a full refresh.

An implausible attribute (a floor of 250, a 0% cut) is set to NULL with a
warning rather than rejecting the listing: price, size and location are what
make a row usable, and an attribute garbled by a layout change should not cost
the listing.

**The score is unchanged.** Nothing here enters `fct_listings_scored`'s
arithmetic; the attributes ride alongside it until a benchmark is built that
uses them.

## Consequences
- History of these attributes begins at the first scrape after this change.
  Every snapshot before it is NULL for all of them, so any analysis must
  restrict to rows scraped after it, not treat NULL as a category.
- NULL mixes "the card did not say" with "not scraped yet"; `_loaded_at`
  separates the two.
- A column added to an incremental model is now a one-way door for the code
  that reads it: model code from before this change fails its incremental
  insert against a table that already has the columns (verified locally). A
  revert of this change therefore also has to drop the columns from the
  incremental tables, or keep `on_schema_change`; and an open PR branched
  before it fails its CI dbt build against the shared `ci_*` tables once this
  change's CI has run, until it is rebased.
- `portal_previous_price_eur` can predate our first observation of a listing,
  so it can show a cut our own history never saw. The two are kept apart on
  purpose.

## Alternatives rejected
- **Default unstated attributes to `false`.** Simpler to filter on, and wrong:
  it turns an advertiser's silence into a claim about the flat, and would
  teach an adjusted benchmark that houses have no lift.
- **Detail-page scraping for richer attributes** (bathrooms, year, energy
  rating). The card already carries the attributes that matter most, at no
  extra credits; a detail page costs a full request per listing (ADR 0001).
- **Fail the build until raw has the columns** — i.e. require the scrape to run
  before `dbt build` ever sees the new model. CI builds on every PR against the
  same raw tables, and scheduled runs skip the scrape when Scrapfly is off, so
  this would have made the merge order load-bearing for weeks.
- **A full refresh to add the columns.** `stg_idealista__listings` is the only
  snapshot history and is `full_refresh=false` precisely because rebuilding it
  from raw would lose it (ADR 0003).
