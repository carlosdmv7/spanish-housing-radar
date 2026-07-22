-- silver/int_market_context.sql
-- Collapses the INE house-price index into the LATEST available quarter per
-- region × housing_type, pivoting the metrics (index level, YoY %, QoQ %) into
-- columns. This is the official, transaction-based market reality the app shows
-- alongside the scraped ASKING-price benchmarks.
-- Grain: one row per (region, housing_type).
{{ config(materialized='table', schema='silver') }}

with hpi as (
    select * from {{ ref('stg_ine__hpi') }}
),

latest as (
    select region, housing_type, max(period_date) as latest_period
    from hpi
    group by 1, 2
)

select
    h.region,
    h.housing_type,
    h.period_date                                              as latest_period,
    max(case when h.metric = 'index' then h.value end)         as hpi_index,
    max(case when h.metric = 'yoy'   then h.value end)         as hpi_yoy_pct,
    max(case when h.metric = 'qoq'   then h.value end)         as hpi_qoq_pct
from hpi h
join latest l
    on  h.region      = l.region
    and h.housing_type = l.housing_type
    and h.period_date  = l.latest_period
group by 1, 2, 3
