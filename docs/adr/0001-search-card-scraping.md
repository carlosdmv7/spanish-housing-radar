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

## Alternatives rejected
- **Detail pages for everything.** The complete record — coordinates, full
  description, floor, condition — at 25–29 credits a listing. At a fixed budget
  this buys roughly 1/750th the coverage, and coverage is what a benchmark is
  made of. A perfectly-described listing with four comparables behind its median
  is a worse product than a thinly-described one with forty.
- **A hybrid pass: cards for breadth, detail pages for the top-scoring few.**
  Genuinely attractive, and the likeliest future change. Rejected *for now*
  because it introduces a second extraction path, a second parser and a second
  failure mode to maintain, while the pipeline is still short of the comparable
  counts that make the score trustworthy in the first place. Worth revisiting
  once barrio-grain coverage is the norm rather than the exception.
- **Geocoding each listing from its card text.** The card gives a street name
  often enough to look plausible, and that is the problem: it fails silently and
  differently across municipalities, and a map of confidently-wrong pins is worse
  than an honest one of barrio centroids. Geocoding is done once per *barrio*,
  against a seed, where it can be checked.
- **A portal API or a licensed data feed.** No public Idealista API exists at
  this tier, and a commercial feed defeats the point of a project whose subject
  is what can be built end to end by one person on free infrastructure.
