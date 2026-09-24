-- gold/rpt_market_trend.sql
-- The INE house-price index as a quarterly series per served municipality: the
-- history that rpt_market_context collapses to its latest quarter. The app draws
-- it as the official trend next to the scraped asking prices, which only have
-- weeks of history of their own — the per-barrio line the Market page used to
-- draw from those snapshots was mostly noise from a changing sample.
-- Grain: one row per (municipality, housing_type, period_date).
{{ config(materialized='view', schema='gold') }}

with muni as (
    select distinct municipality from {{ ref('int_listings_current') }}
),

city_to_region as (
    select * from {{ ref('ccaa_by_municipality') }}
),

hpi as (
    select * from {{ ref('stg_ine__hpi') }}
)

select
    m.municipality,
    r.ine_region                                           as region,
    h.housing_type,
    h.period_date,
    max(case when h.metric = 'index' then h.value end)     as hpi_index,
    max(case when h.metric = 'yoy'   then h.value end)     as hpi_yoy_pct
from muni m
join city_to_region r on m.municipality = r.municipality
join hpi h on r.ine_region = h.region
group by 1, 2, 3, 4
