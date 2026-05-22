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
        source_id,
        source_name,
        raw_url,
        raw_price_eur,
        raw_operation_type,
        raw_size_sqm,
        raw_rooms,
        raw_bathrooms,
        raw_property_type,
        raw_lat,
        raw_lon,
        lower(trim(raw_municipality))  as raw_municipality,
        lower(trim(raw_district))      as raw_district,
        lower(trim(raw_neighborhood))  as raw_neighborhood,
        _loaded_at,
        _run_id
    from source
)

select * from renamed
