-- gold/rpt_market_context.sql
-- Official INE market context resolved to the municipalities the app serves, by
-- bridging municipality → autonomous community (ccaa_by_municipality seed) →
-- INE house-price index. One row per municipality; read directly by the app to
-- show "where the real market is heading" next to the asking-price benchmarks.
{{ config(materialized='view', schema='gold') }}

with muni as (
    select distinct municipality from {{ ref('int_listings_current') }}
),

city_to_region as (
    select * from {{ ref('ccaa_by_municipality') }}
),

context as (
    select * from {{ ref('int_market_context') }}
)

select
    m.municipality,
    r.ine_region                     as region,
    g.latest_period,
    g.hpi_index                      as hpi_index_general,
    g.hpi_yoy_pct                    as hpi_yoy_general,
    s.hpi_yoy_pct                    as hpi_yoy_second_hand
from muni m
left join city_to_region r on m.municipality = r.municipality
left join context g on r.ine_region = g.region and g.housing_type = 'general'
left join context s on r.ine_region = s.region and s.housing_type = 'second_hand'
