-- transform/models/silver/int_listings_current.sql
-- Current state of each listing: the latest valid snapshot per listing_pk.
-- Reads from the multi-source spine (int_listings_unioned), which already
-- applies dq filtering, property-type normalisation, barrio cleaning and
-- geocoding — so this model only has to pick the most recent snapshot.
{{ config(materialized='incremental', unique_key='listing_pk', schema='silver') }}

with unioned as (
    select * from {{ ref('int_listings_unioned') }}
),

latest as (
    select *,
        row_number() over (
            partition by listing_pk
            order by _loaded_at desc
        ) as _rn
    from unioned
)

select
    listing_pk,
    snapshot_pk,
    source_id,
    source_name,
    url,
    price_eur,
    size_sqm,
    price_per_sqm,
    rooms,
    property_type,
    operation_type,
    lat,
    lon,
    municipality,
    district,
    neighborhood,
    neighborhood_is_canonical,
    neighborhood_is_benchmarkable,
    scraped_date,
    _loaded_at,
    _run_id
from latest
where _rn = 1
