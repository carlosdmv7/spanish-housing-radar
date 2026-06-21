-- Fotocasa staging — PLACEHOLDER until the Fotocasa source is wired in.
-- The scraper exists (extraction/scrapers/fotocasa.py) but raw.fotocasa_listings
-- is not populated yet, so this model intentionally returns zero rows. Keeping it
-- in the graph (rather than disabling it) means int_listings_unioned's reference
-- still resolves and its tests pass trivially. Replace the body with real staging
-- logic once Fotocasa data is being ingested.
{{ config(materialized='view') }}

select
    null::varchar as snapshot_pk,
    null::varchar as listing_pk,
    null::varchar as operation_type
where 1 = 0
