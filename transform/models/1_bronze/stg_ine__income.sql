-- bronze/stg_ine__income.sql
-- Light typing over the ADRH district-income feed. Keeps every district × metric
-- × year; silver picks the metric and the reference year it needs.
{{ config(materialized='view', schema='bronze') }}

select
    district_code,
    municipality_code,
    lower(trim(municipality_name))            as municipality_name,
    lower(trim(district_name))                as district_name_ine,
    metric,
    year,
    value,
    _loaded_at,
    _run_id
from {{ source('raw', 'ine_income') }}
