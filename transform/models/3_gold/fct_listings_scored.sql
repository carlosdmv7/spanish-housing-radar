-- transform/models/gold/fct_listings_scored.sql
-- Opportunity score with a HIERARCHICAL benchmark.
--
-- Each listing is compared against the median €/sqm of its own area. But a
-- neighbourhood with only one or two listings can't benchmark anything (you'd be
-- comparing a flat to itself → z-score 0 → a meaningless "fair" 50). So we build
-- three benchmark grains and, per listing, pick the FINEST one that has at least
-- `min_comps_for_benchmark` comparables:
--     neighbourhood  →  district  →  city (municipality)
-- always within the same operation_type + property_type. `benchmark_level` records
-- which grain actually scored each listing, so the app can be honest about it.
{{ config(materialized='table', schema='gold') }}

{% set min_comps = var('min_comps_for_benchmark', 8) %}

with listings as (
    select * from {{ ref('int_listings_current') }}
),

-- ── Benchmark grains ──────────────────────────────────────────────────────────
-- `neighborhood_is_benchmarkable` gates this grain, and only this grain. Until
-- now any string sitting in `neighborhood` was a valid grouping key -- including
-- the street names and portal numbers the extraction heuristic produced, so the
-- warehouse could and did build "benchmarks" for places called "34". A benchmark
-- is a claim about a place, and a name that is demonstrably not a place is not
-- evidence for anything.
--
-- The flag is deliberately weaker than `neighborhood_is_canonical`: see
-- int_listings_unioned for why seed-confirmed and seed-unknown are not the same
-- thing. Unverified names still reach the app (ADR-0005) -- they simply cannot
-- become the denominator of anyone's score.
nbhd_stats as (
    select
        municipality, operation_type, property_type, neighborhood,
        count(*)                          as n,
        median(price_per_sqm)             as median_ppsqm,
        stddev_pop(price_per_sqm)         as stddev_ppsqm
    from listings
    where neighborhood is not null
      and neighborhood_is_benchmarkable
    group by 1, 2, 3, 4
),

district_stats as (
    select
        municipality, operation_type, property_type, district,
        count(*)                          as n,
        median(price_per_sqm)             as median_ppsqm,
        stddev_pop(price_per_sqm)         as stddev_ppsqm
    from listings
    where district is not null
    group by 1, 2, 3, 4
),

city_stats as (
    select
        municipality, operation_type, property_type,
        count(*)                          as n,
        median(price_per_sqm)             as median_ppsqm,
        stddev_pop(price_per_sqm)         as stddev_ppsqm
    from listings
    group by 1, 2, 3
),

-- ── Pick the finest grain with enough comparables ─────────────────────────────
benched as (
    select
        l.*,
        case
            when nb.n >= {{ min_comps }} then 'neighbourhood'
            when di.n >= {{ min_comps }} then 'district'
            else 'city'
        end as benchmark_level,
        case
            when nb.n >= {{ min_comps }} then nb.median_ppsqm
            when di.n >= {{ min_comps }} then di.median_ppsqm
            else ci.median_ppsqm
        end as benchmark_median_ppsqm,
        case
            when nb.n >= {{ min_comps }} then nb.stddev_ppsqm
            when di.n >= {{ min_comps }} then di.stddev_ppsqm
            else ci.stddev_ppsqm
        end as benchmark_stddev_ppsqm,
        case
            when nb.n >= {{ min_comps }} then nb.n
            when di.n >= {{ min_comps }} then di.n
            else ci.n
        end as benchmark_comp_count
    from listings l
    left join nbhd_stats nb
        on l.municipality = nb.municipality and l.operation_type = nb.operation_type
       and l.property_type = nb.property_type and l.neighborhood = nb.neighborhood
       -- Belt and braces: nbhd_stats is already filtered, so this cannot change
       -- the result today. It states the invariant at the join, where a future
       -- edit to either side would otherwise break it silently.
       and l.neighborhood_is_benchmarkable
    left join district_stats di
        on l.municipality = di.municipality and l.operation_type = di.operation_type
       and l.property_type = di.property_type and l.district = di.district
    left join city_stats ci
        on l.municipality = ci.municipality and l.operation_type = ci.operation_type
       and l.property_type = ci.property_type
),

with_zscore as (
    select
        *,
        round(price_per_sqm - benchmark_median_ppsqm, 2) as ppsqm_vs_median,
        round(
            greatest(-3.0, least(3.0,
                -- neutral (0) when the benchmark has no price dispersion
                -- (single comparable → stddev 0/NULL), avoiding a false -/+3 snap.
                coalesce(
                    (price_per_sqm - benchmark_median_ppsqm)
                    / nullif(benchmark_stddev_ppsqm, 0),
                    0
                )
            )), 3
        ) as ppsqm_z_score
    from benched
),

scored as (
    select
        *,
        round(greatest(0, least(100, 50 - ppsqm_z_score * (50.0 / 3.0))), 1) as opportunity_score,
        -- only the very coarse, thin city grain is flagged unreliable now
        (benchmark_level = 'city' and benchmark_comp_count < {{ min_comps }})  as low_confidence_flag
    from with_zscore
),

final as (
    select
        *,
        -- keep the neighbourhood-median column name the app already consumes
        benchmark_median_ppsqm as neighborhood_median_ppsqm,
        case
            when opportunity_score >= 75 then 'great_deal'
            when opportunity_score >= 55 then 'good_deal'
            when opportunity_score >= 45 then 'fair'
            when opportunity_score >= 25 then 'overpriced'
            else 'very_overpriced'
        end as deal_tier
    from scored
)

select * from final
