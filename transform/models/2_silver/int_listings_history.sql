-- transform/models/silver/int_listings_history.sql
-- Todos los snapshots válidos → para series temporales de precio
{{ config(materialized='incremental', unique_key='snapshot_pk', schema='silver') }}

select
    snapshot_pk,
    listing_pk,
    source_id,
    source_name,
    price_eur,
    round(price_eur / size_sqm, 2)  as price_per_sqm,
    size_sqm,
    case property_type
        when 'flat'      then 'apartment'
        when 'apartment' then 'apartment'
        when 'penthouse' then 'apartment'
        when 'house'     then 'house'
        when 'chalet'    then 'house'
        else 'other'
    end                              as property_type,
    operation_type,
    municipality,
    district,
    neighborhood,
    scraped_date,
    _loaded_at,
    _run_id
from {{ ref('stg_idealista__listings') }}
where not dq_bad_price
  and not dq_bad_size
  {% if is_incremental() %}
      and _loaded_at > (select max(_loaded_at) from {{ this }})
  {% endif %}