-- transform/models/silver/int_listings_unioned.sql
{{ config(materialized='table', schema='silver') }}

-- DRY: the macro enforces the same price_per_sqm formula everywhere
{% set sources = ['stg_idealista__listings', 'stg_fotocasa__listings'] %}

with unioned as (
    {% for model in sources %}
    select
        source_id,
        source_name,
        raw_price_eur,
        raw_size_sqm,
        raw_rooms,
        raw_bathrooms,
        raw_property_type,
        raw_operation_type,
        raw_lat,
        raw_lon,
        raw_municipality,
        raw_district,
        raw_neighborhood,
        _loaded_at
    from {{ ref(model) }}
    where raw_price_eur > 0
      and raw_size_sqm  > 0
    {% if not loop.last %} union all {% endif %}
    {% endfor %}
),

deduped as (
    -- keep the most recently loaded record per portal + id combination
    select *,
        row_number() over (
            partition by source_name, source_id
            order by _loaded_at desc
        ) as _rn
    from unioned
),

enriched as (
    select
        {{ dbt_utils.generate_surrogate_key(['source_name', 'source_id']) }} as listing_id,
        source_id,
        source_name,
        raw_price_eur                                    as price_eur,
        raw_size_sqm                                     as size_sqm,
        {{ price_per_sqm('raw_price_eur', 'raw_size_sqm') }} as price_per_sqm,
        raw_rooms                                        as rooms,
        raw_bathrooms                                    as bathrooms,
        -- normalise property type across portals
        case raw_property_type
            when 'flat'        then 'apartment'
            when 'apartment'   then 'apartment'
            when 'penthouse'   then 'apartment'
            when 'house'       then 'house'
            when 'chalet'      then 'house'
            else 'other'
        end                                              as property_type,
        raw_operation_type                               as operation_type,
        raw_lat                                          as lat,
        raw_lon                                          as lon,
        raw_neighborhood                                 as neighborhood,
        raw_district                                     as district,
        raw_municipality                                 as municipality,
        _loaded_at
    from deduped
    where _rn = 1
)

select * from enriched