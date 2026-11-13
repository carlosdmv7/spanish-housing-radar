-- transform/models/silver/int_listings_current.sql
-- Current state of each listing: the latest valid snapshot per listing_pk.
-- Reads from the multi-source spine (int_listings_unioned), which already
-- applies dq filtering, property-type normalisation, barrio cleaning and
-- geocoding — so this model only has to pick the most recent snapshot.
-- append_new_columns: see stg_idealista__listings.
{{ config(
    materialized='incremental',
    unique_key='listing_pk',
    schema='silver',
    on_schema_change='append_new_columns'
) }}

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
    -- Card attributes of the latest snapshot (ADR-0012); NULL = unstated.
    floor,
    floor_text,
    is_exterior,
    has_lift,
    garage,
    garage_price_eur,
    garage_text,
    portal_previous_price_eur,
    portal_price_drop_pct,
    description,
    tags,
    scraped_date,
    _loaded_at,
    _run_id
from latest
where _rn = 1
