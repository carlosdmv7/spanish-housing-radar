# ADR 0003 — Idempotent upserts keyed on `(source_name, source_id)`

**Status:** accepted

## Context
A scheduled pipeline retries. Scrapfly times out mid-run, a GitHub Actions job is
re-dispatched, a developer re-runs an extraction to debug a selector — and the
same listings are fetched again. With plain `INSERT`, every retry inflates the
row count and silently corrupts every median the Opportunity Score depends on.
Retry-safety is therefore a prerequisite for orchestrating the pipeline at all,
not a nice-to-have.

## Decision
Raw tables declare `PRIMARY KEY (source_name, source_id)` and the loader writes
with `INSERT OR REPLACE` (`extraction/loaders/motherduck_loader.py`). The key is
the portal's own listing ID scoped by portal, so the same flat cross-listed on
Idealista and Fotocasa stays two rows (deduplicated later, in
`int_listings_unioned`) while a re-scrape of one portal overwrites in place.
`raw.ine_hpi` follows the same pattern on `(series_cod, period_date)`. Every raw
row carries `_run_id` and `_loaded_at` for provenance.

## Consequences
- Any run is safe to repeat: the pipeline is orchestratable with task-level
  retries (Prefect) and a daily cron with no dedup step in between.
- **A re-scrape overwrites the previous observation for that listing.** Snapshot
  history therefore cannot live in raw — `int_listings_history` accumulates it in
  silver, keyed by load date, and is what makes days-on-market and price-cut
  signals real rather than reconstructed.
- The upsert is only as stable as the portal's ID. If Idealista ever recycles a
  `source_id`, two different flats collapse into one row; no test currently
  guards that, and it would show up as a price discontinuity in the history.
- `_run_id` makes it possible to attribute a bad batch to a specific run.
