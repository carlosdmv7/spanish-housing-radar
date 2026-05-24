-- silver/int_listings_unioned.sql
{{ config(materialized='incremental', unique_key='snapshot_pk', schema='silver') }}

with idealista as (
    select * from {{ ref('stg_idealista__listings') }}
),

-- fotocasa as (
--     select * from {{ ref('stg_fotocasa__listings') }}
-- ),

all_sources as (
    select * from idealista
    -- union all
    -- select * from fotocasa
),

cleaned as (
    select
        snapshot_pk,
        listing_pk,
        source_id,
        source_name,
        url,
        price_eur,
        size_sqm,
        round(price_eur / size_sqm, 2)   as price_per_sqm,
        rooms,
        bathrooms,
        -- normalización cross-source aquí, no en cada stg_
        case property_type
            when 'flat'      then 'apartment'
            when 'apartment' then 'apartment'
            when 'penthouse' then 'apartment'
            when 'house'     then 'house'
            when 'chalet'    then 'house'
            else 'other'
        end                              as property_type,
        operation_type,
        lat, lon,
        municipality, district, neighborhood,
        scraped_date, _loaded_at, _run_id,
        dq_bad_price, dq_bad_size, dq_extreme_ppsqm
    from all_sources
    {% if is_incremental() %}
        where _loaded_at > (select max(_loaded_at) from {{ this }})
    {% endif %}
)

select * from cleaned
where not dq_bad_price and not dq_bad_size and not dq_extreme_ppsqm