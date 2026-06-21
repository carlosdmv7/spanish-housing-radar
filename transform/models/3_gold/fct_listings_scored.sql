-- transform/models/gold/fct_listings_scored.sql
{{ config(materialized='table', schema='gold') }}

with listings as (
    select * from {{ ref('int_listings_current') }}
),

stats as (
    select * from {{ ref('int_neighborhood_stats') }}
),

joined as (
    select
        l.*,
        s.median_ppsqm      as neighborhood_median_ppsqm,
        s.stddev_ppsqm      as neighborhood_stddev_ppsqm,
        s.p25_ppsqm         as neighborhood_p25_ppsqm,
        s.p75_ppsqm         as neighborhood_p75_ppsqm,
        s.total_listings    as neighborhood_listing_count
    from listings l
    left join stats s
        on  l.neighborhood   = s.neighborhood
        and l.municipality   = s.municipality
        and l.operation_type = s.operation_type
        and l.property_type  = s.property_type
),

-- Separar el cálculo del z-score para poder reusarlo sin repetir la fórmula
with_zscore as (
    select
        *,
        round(price_per_sqm - neighborhood_median_ppsqm, 2) as ppsqm_vs_median,
        round(
            greatest(-3.0, least(3.0,
                -- coalesce to 0 (neutral) when the neighbourhood has no price
                -- dispersion (single comparable → stddev 0/NULL). Without this,
                -- DuckDB's greatest/least ignore the NULL and snap the z-score to
                -- the +3 bound, mislabelling every single-comp listing as
                -- very_overpriced (score 0). These rows are already low_confidence.
                coalesce(
                    (price_per_sqm - neighborhood_median_ppsqm)
                    / nullif(neighborhood_stddev_ppsqm, 0),
                    0
                )
            )), 3
        ) as ppsqm_z_score
    from joined
),

-- Ahora sí podemos referenciar ppsqm_z_score en el CASE
scored as (
    select
        *,
        round(greatest(0, least(100,
            50 - ppsqm_z_score * (50.0 / 3.0)
        )), 1)                              as opportunity_score,
        neighborhood_listing_count < 10    as low_confidence_flag
    from with_zscore
),

-- Y ahora el deal_tier puede referenciar opportunity_score sin problema
final as (
    select
        *,
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