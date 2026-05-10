-- transform/models/bronze/stg_idealista__listings.sql
{{ config(materialized='incremental', unique_key='source_id', schema='bronze') }}

with source as (
    select * from {{ source('raw', 'idealista_listings') }}
    {% if is_incremental() %}
        where _loaded_at > (select max(_loaded_at) from {{ this }})
    {% endif %}
),

renamed as (
    select
        -- natural key from the portal
        cast(id            as varchar)   as source_id,
        'idealista'                      as source_name,
        cast(price         as double)    as raw_price_eur,
        cast(size          as double)    as raw_size_sqm,
        cast(rooms         as integer)   as raw_rooms,
        cast(bathrooms     as integer)   as raw_bathrooms,
        lower(trim(propertyType))        as raw_property_type,
        lower(trim(operation))           as raw_operation_type,  -- 'sale' | 'rent'
        cast(latitude      as double)    as raw_lat,
        cast(longitude     as double)    as raw_lon,
        -- location hierarchy (denormalised for Bronze)
        lower(trim(municipality))        as raw_municipality,
        lower(trim(district))            as raw_district,
        lower(trim(neighborhood))        as raw_neighborhood,
        -- raw JSON blob kept for future field extraction
        to_json(address)                 as raw_address_json,
        -- pipeline metadata
        current_timestamp                as _loaded_at,
        '{{ var("run_id", "manual") }}'  as _run_id
    from source
)

select * from renamed