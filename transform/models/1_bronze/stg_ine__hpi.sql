-- bronze/stg_ine__hpi.sql
-- Light typing over the raw INE house-price index feed. Keeps every series ×
-- quarter observation; downstream silver picks the metrics/grains it needs.
{{ config(materialized='view', schema='bronze') }}

select
    series_cod,
    lower(trim(region))                       as region,
    housing_type,                              -- general | new | second_hand
    metric,                                    -- index | qoq | yoy | ytd
    cast(period_date as date)                  as period_date,
    year,
    value,
    _loaded_at,
    _run_id
from {{ source('raw', 'ine_hpi') }}
