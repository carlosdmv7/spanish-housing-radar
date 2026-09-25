-- transform/models/gold/fct_listings_scored.sql
-- Opportunity score against a benchmark that trusts a barrio as far as its
-- data earns, and no further.
--
-- Each listing is compared with the median €/m² around it, always within the
-- same operation_type + property_type. The *parent* area is the district when
-- it has `min_comps_for_benchmark` comparables, else the whole city (ADR-0004).
-- The barrio then moves the benchmark away from its parent by an
-- empirical-Bayes weight (ADR-0011):
--
--     benchmark = w · barrio median + (1 − w) · parent median,  w = n / (n + k)
--
-- n is the barrio's listing count; k is estimated from the data on every build,
-- per city × operation × property type, as the within-barrio variance over the
-- between-barrio variance within districts. A large k means barrios barely
-- differ from their district beyond noise, so it takes many listings before a
-- barrio's own median is believed.
--
-- This replaced a hard switch — 8 listings and the barrio median counted in
-- full, 7 and it counted not at all. Measured on València (2026-09-25), k was
-- about 6 for sales: a barrio of 8 deserves ~57% weight, not 100%, and one of 5
-- deserves ~45%, not 0. For rents the barrio effect within a district was not
-- distinguishable from noise at all, so rents are scored against their district.
--
-- `benchmark_level` names the area that carries most of the weight, and
-- `barrio_weight` records the exact blend, so the app can say what a score was
-- measured against.
{{ config(materialized='table', schema='gold') }}

{% set min_comps = var('min_comps_for_benchmark', 8) %}
{% set min_barrio = var('min_listings_for_barrio_weight', 3) %}
{% set min_barrios = var('min_barrios_for_shrinkage', 5) %}

with listings as (
    select * from {{ ref('int_listings_valid') }}
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

-- ── How far to trust a barrio: the shrinkage constant k ─────────────────────
-- Method of moments over barrios with at least `min_barrio` listings:
--   within  = pooled variance of listings around their barrio's mean
--   between = variance of barrio means around their district's mean, minus the
--             part of it that sampling noise alone would produce
-- k = within / between. No k (so no barrio weight) when fewer than
-- `min_barrios` barrios inform it or when `between` is not positive — the data
-- cannot tell barrios in a district apart.
barrio_moments as (
    select
        municipality, operation_type, property_type, district, neighborhood,
        count(*)                          as n,
        avg(price_per_sqm)                as mean_ppsqm,
        var_samp(price_per_sqm)           as var_ppsqm
    from listings
    where neighborhood is not null
      and neighborhood_is_benchmarkable
      and district is not null
    group by 1, 2, 3, 4, 5
    having count(*) >= {{ min_barrio }}
),

district_means as (
    select municipality, operation_type, property_type, district,
           avg(price_per_sqm) as mean_ppsqm
    from listings
    where district is not null
    group by 1, 2, 3, 4
),

shrinkage as (
    select
        b.municipality, b.operation_type, b.property_type,
        count(*)                                                    as n_barrios,
        sum((b.n - 1) * b.var_ppsqm) / nullif(sum(b.n - 1), 0)      as within_var,
        avg(power(b.mean_ppsqm - d.mean_ppsqm, 2))
            - avg(b.var_ppsqm / b.n)                                as between_var
    from barrio_moments b
    join district_means d
      on b.municipality = d.municipality and b.operation_type = d.operation_type
     and b.property_type = d.property_type and b.district = d.district
    group by 1, 2, 3
),

shrinkage_k as (
    select
        municipality, operation_type, property_type,
        case when n_barrios >= {{ min_barrios }} and between_var > 0
             then within_var / between_var end                      as shrinkage_k
    from shrinkage
),

-- ── Parent area, then the barrio's pull on it ────────────────────────────────
parented as (
    select
        l.*,
        case when di.n >= {{ min_comps }} then 'district' else 'city' end  as parent_level,
        case when di.n >= {{ min_comps }} then di.median_ppsqm else ci.median_ppsqm end
                                                                            as parent_median_ppsqm,
        case when di.n >= {{ min_comps }} then di.stddev_ppsqm else ci.stddev_ppsqm end
                                                                            as parent_stddev_ppsqm,
        case when di.n >= {{ min_comps }} then di.n else ci.n end          as parent_n,
        nb.n                                                                as barrio_n,
        nb.median_ppsqm                                                     as barrio_median_ppsqm,
        nb.stddev_ppsqm                                                     as barrio_stddev_ppsqm,
        k.shrinkage_k,
        case
            when nb.n >= {{ min_barrio }} and k.shrinkage_k is not null
                then nb.n / (nb.n + k.shrinkage_k)
            else 0
        end                                                                 as barrio_weight
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
    left join shrinkage_k k
        on l.municipality = k.municipality and l.operation_type = k.operation_type
       and l.property_type = k.property_type
),

benched as (
    select
        * exclude (barrio_weight),
        round(barrio_weight, 3)                                             as barrio_weight,
        -- Named after the area carrying most of the weight.
        case when barrio_weight >= 0.5 then 'neighbourhood' else parent_level end
                                                                            as benchmark_level,
        barrio_weight * coalesce(barrio_median_ppsqm, 0)
            + (1 - barrio_weight) * parent_median_ppsqm                     as benchmark_median_ppsqm,
        -- The spread blends the same way, as variances.
        sqrt(barrio_weight * power(coalesce(barrio_stddev_ppsqm, 0), 2)
             + (1 - barrio_weight) * power(parent_stddev_ppsqm, 2))         as benchmark_stddev_ppsqm,
        case when barrio_weight >= 0.5 then barrio_n else parent_n end     as benchmark_comp_count
    from parented
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
