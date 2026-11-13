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
--
-- on_schema_change='append_new_columns': the card-attribute columns (ADR-0012)
-- were added to an incremental table that already holds the only snapshot
-- history. Under dbt's default ('ignore') they would be dropped silently from
-- every future insert; 'sync_all_columns' could drop columns. Appending adds
-- them in place, leaves every existing snapshot NULL in them — correct: those
-- cards were never read for these fields — and needs no full refresh.
{{ config(
    materialized='incremental',
    unique_key=['source_id', '_run_id'],
    schema='bronze',
    full_refresh=false,
    on_schema_change='append_new_columns'
) }}

{#- The loader adds these raw columns on the first scrape that carries them;
    until then `dbt build` (CI, and scheduled runs that skip the scrape) still
    reads the old table. column_or_null makes both shapes compile to the same
    typed columns. -#}
{%- set raw_cols = relation_column_names(source('raw', 'idealista_listings')) %}

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

        -- Card attributes as the advertiser states them (ADR-0012). NULL means
        -- the card did not say — and for every snapshot loaded before these
        -- were scraped, that the card was not read for them. Never "no".
        -- floor: sótano/semi-sótano -1, bajo/entreplanta 0, "Planta Nª" N.
        {{ column_or_null(raw_cols, 'raw_floor', 'integer') }}                as floor,
        {{ column_or_null(raw_cols, 'raw_floor_text', 'varchar') }}           as floor_text,
        {{ column_or_null(raw_cols, 'raw_is_exterior', 'boolean') }}          as is_exterior,
        {{ column_or_null(raw_cols, 'raw_has_lift', 'boolean') }}             as has_lift,
        -- 'included' (in the asking price) | 'optional' (sold separately)
        {{ column_or_null(raw_cols, 'raw_garage', 'varchar') }}               as garage,
        {{ column_or_null(raw_cols, 'raw_garage_price_eur', 'double') }}      as garage_price_eur,
        {{ column_or_null(raw_cols, 'raw_garage_text', 'varchar') }}          as garage_text,
        -- The portal's own price-drop marker, not one derived from our history.
        {{ column_or_null(raw_cols, 'raw_previous_price_eur', 'double') }}    as portal_previous_price_eur,
        {{ column_or_null(raw_cols, 'raw_price_drop_pct', 'double') }}        as portal_price_drop_pct,
        {{ column_or_null(raw_cols, 'raw_description', 'varchar') }}          as description,
        -- '|'-delimited, e.g. 'Lujo|Villa'
        {{ column_or_null(raw_cols, 'raw_tags', 'varchar') }}                 as tags,

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