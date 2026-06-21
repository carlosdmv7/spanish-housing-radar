-- transform/models/silver/int_neighborhood_stats.sql
{{ config(materialized='table', schema='silver') }}

-- Grain: one row per (municipality, neighborhood, operation_type, property_type).
-- district is NOT part of the grain (it is collapsed with max) — benchmarks are
-- neighbourhood-level. Keeping district in the GROUP BY would fan out the join in
-- fct_listings_scored and duplicate listings.
select
    municipality,
    max(district)                                               as district,
    neighborhood,
    operation_type,
    property_type,
    count(*)                                                    as total_listings,
    round(median(price_per_sqm), 2)                             as median_ppsqm,
    round(avg(price_per_sqm), 2)                                as avg_ppsqm,
    round(stddev_pop(price_per_sqm), 2)                         as stddev_ppsqm,
    round(percentile_cont(0.25) within group
        (order by price_per_sqm), 2)                            as p25_ppsqm,
    round(percentile_cont(0.75) within group
        (order by price_per_sqm), 2)                            as p75_ppsqm,
    round(median(size_sqm), 1)                                  as median_size_sqm,
    current_timestamp                                           as _refreshed_at
from {{ ref('int_listings_current') }}
group by municipality, neighborhood, operation_type, property_type