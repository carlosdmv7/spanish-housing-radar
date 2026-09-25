-- transform/models/bronze/stg_idealista__listings.sql
-- unique_key ahora incluye _run_id → guardamos CADA snapshot, no solo el último
-- full_refresh=false: this table is the only complete snapshot history in the
-- warehouse. raw.idealista_listings upserts on (source_name, source_id), so a
-- re-scrape overwrites the previous observation (ADR-0003); rebuilt from raw,
-- this model would keep one snapshot per listing and every days-on-market and
-- price-cut signal downstream would silently reset. A full refresh of the
-- project therefore skips this model — which is what makes rebuilding silver
-- and gold safe. Verified 2026-09-25: a --full-refresh into ci_* left 1,426
-- snapshots for 1,426 listings, against 1,618 kept in prod.
{{ config(
    materialized='incremental',
    unique_key=['source_id', '_run_id'],
    schema='bronze',
    full_refresh=false
) }}

with source as (
    select * from {{ source('raw', 'idealista_listings') }}
    {% if is_incremental() %}
        where _loaded_at > (select max(_loaded_at) from {{ this }})
    {% endif %}
),

cleaned as (
    select
        -- PK legible: fuente__id__run  →  idealista__109947740__20260524T113320Z
        source_name || '__' || source_id || '__' || _run_id  as snapshot_pk,

        -- PK estable del listing (sin run): para joins y dedup en silver
        source_name || '__' || source_id                     as listing_pk,

        source_id,
        source_name,
        raw_url                                              as url,
        raw_price_eur                                        as price_eur,
        raw_operation_type                                   as operation_type,
        raw_size_sqm                                         as size_sqm,
        raw_rooms                                            as rooms,
        raw_bathrooms                                        as bathrooms,
        raw_property_type                                    as property_type,
        raw_lat                                              as lat,
        raw_lon                                              as lon,
        lower(trim(raw_municipality))                        as municipality,
        lower(trim(raw_district))                            as district,
        lower(trim(raw_neighborhood))                        as neighborhood,
        -- Carried through untouched so silver can re-derive location from the
        -- source text rather than trusting the extraction-time parse.
        raw_title                                            as listing_title,

        -- Data quality flags (detectar basura antes de silver)
        raw_price_eur is null or raw_price_eur <= 0          as dq_bad_price,
        raw_size_sqm  is null or raw_size_sqm  <= 0          as dq_bad_size,
        raw_price_eur > 0 and raw_size_sqm > 0
            and (raw_price_eur / raw_size_sqm) > 50000       as dq_extreme_ppsqm,

        _loaded_at,
        _run_id,
        cast(_loaded_at as date)                             as scraped_date
    from source
)

select * from cleaned