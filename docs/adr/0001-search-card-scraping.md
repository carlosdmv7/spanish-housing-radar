# ADR 0001 — Scrape search cards, not detail pages

**Status:** accepted

## Context
Idealista exposes each listing twice: as a card in a paginated search result, and
as a full detail page. Detail pages carry more fields (notably per-listing
coordinates and the full description) but require JS rendering behind Scrapfly's
anti-bot proxy, at **25–29 credits per request**. A search card costs ~1 credit
and yields ~30 listings per fetch. The product is a *benchmark engine*: the score
is only as good as the number of comparables behind the median, so coverage is
the binding constraint, not per-listing depth.

## Decision
Extract every field from the `<article class="item">` search card only
(`extraction/scrapers/idealista.py`, `render_js=false`). Location is recovered by
parsing the card's `title` attribute with a `_parse_location()` heuristic
(municipality / district / neighbourhood), unit-tested against real cards. No
detail-page fetches anywhere in the default path.

## Consequences
- ~750× cheaper per listing, so a fixed credit budget buys breadth of
  comparables instead of depth on a handful of flats.
- **No per-listing coordinates.** The map plots barrio centroids from the
  `barrios_es` seed instead of exact addresses (see ADR 0004's grain logic and
  the README's known limitations).
- Location quality depends on a text heuristic, so it is a tested unit with a
  `neighborhood_is_canonical` flag rather than a trusted upstream field.
- Description-derived features (condition, "needs renovation", floor) are out of
  reach until a selective detail-page pass is worth the credits.
