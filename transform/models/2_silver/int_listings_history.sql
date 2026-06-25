-- transform/models/silver/int_listings_history.sql
-- All valid snapshots → time series of price. Reads from the unified spine so
-- the history shares the same cleaned barrios, geocoding and dq filtering as the
-- rest of silver (int_listings_unioned keeps every snapshot, so trends survive).
{{ config(materialized='incremental', unique_key='snapshot_pk', schema='silver') }}

select
    snapshot_pk,
    listing_pk,
    source_id,
    source_name,
    price_eur,
    price_per_sqm,
    size_sqm,
    property_type,
    operation_type,
    municipality,
    district,
    neighborhood,
    scraped_date,
    _loaded_at,
    _run_id
from {{ ref('int_listings_unioned') }}
{% if is_incremental() %}
    where _loaded_at > (select max(_loaded_at) from {{ this }})
{% endif %}
