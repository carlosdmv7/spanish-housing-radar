-- transform/models/gold/rpt_neighborhood_stats.sql
{{ config(materialized='table', schema='gold') }}

-- Pre-aggregate neighborhood benchmarks to avoid expensive per-query groupBys in Streamlit
with base as (
    select * from {{ ref('int_listings_unioned') }}
    where operation_type in ('sale', 'rent')
),

stats as (
    select
        municipality,
        district,
        neighborhood,
        operation_type,
        property_type,
        count(*)                                            as total_listings,
        median(price_per_sqm)                               as median_ppsqm,
        percentile_cont(0.25) within group
            (order by price_per_sqm)                        as p25_ppsqm,
        percentile_cont(0.75) within group
            (order by price_per_sqm)                        as p75_ppsqm,
        avg(price_per_sqm)                                  as avg_ppsqm,
        stddev_pop(price_per_sqm)                           as stddev_ppsqm,
        median(size_sqm)                                    as median_size_sqm,
        current_timestamp                                   as _refreshed_at
    from base
    group by 1,2,3,4,5
)

select * from stats