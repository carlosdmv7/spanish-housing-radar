-- transform/models/silver/int_listings_current.sql
-- Estado actual de cada listing (último snapshot válido)
{{ config(materialized='incremental', unique_key='listing_pk', schema='silver') }}

with bronze as (
    select * from {{ ref('stg_idealista__listings') }}
    where not dq_bad_price
      and not dq_bad_size
      and not dq_extreme_ppsqm
),

latest as (
    select *,
        row_number() over (
            partition by listing_pk
            order by _loaded_at desc
        ) as _rn
    from bronze
),

enriched as (
    select
        listing_pk,
        snapshot_pk,
        source_id,
        source_name,
        url,
        price_eur,
        size_sqm,
        round(price_eur / size_sqm, 2)      as price_per_sqm,
        rooms,
        bathrooms,
        case property_type
            when 'apartment'  then 'apartment'
            when 'penthouse'  then 'apartment'
            when 'flat'       then 'apartment'
            when 'house'      then 'house'
            when 'chalet'     then 'house'
            else 'other'
        end                                  as property_type,
        operation_type,
        lat,
        lon,
        municipality,
        district,
        neighborhood,
        scraped_date,
        _loaded_at,
        _run_id
    from latest
    where _rn = 1
)

select * from enriched