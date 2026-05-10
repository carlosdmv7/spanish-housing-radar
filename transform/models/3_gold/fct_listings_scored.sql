-- transform/models/gold/fct_listings_scored.sql
{{ config(materialized='table', schema='gold') }}

with listings as (
    select * from {{ ref('int_listings_unioned') }}
),

neighborhood_stats as (
    select * from {{ ref('rpt_neighborhood_stats') }}
),

joined as (
    select
        l.*,
        n.median_ppsqm            as neighborhood_median_ppsqm,
        n.stddev_ppsqm            as neighborhood_stddev_ppsqm,
        n.p25_ppsqm               as neighborhood_p25_ppsqm,
        n.p75_ppsqm               as neighborhood_p75_ppsqm,
        n.total_listings          as neighborhood_listing_count
    from listings l
    left join neighborhood_stats n
        on  l.neighborhood    = n.neighborhood
        and l.municipality    = n.municipality
        and l.operation_type  = n.operation_type
        and l.property_type   = n.property_type
),

scored as (
    select
        *,

        -- Raw deviation: negative = cheaper than median (good for buyer)
        round(price_per_sqm - neighborhood_median_ppsqm, 2)
            as ppsqm_vs_median,

        -- Z-score: how many std deviations from the neighborhood mean?
        -- Negative z = undervalued. Clamp to [-3, 3] to avoid outlier distortion.
        round(
            greatest(-3.0, least(3.0,
                (price_per_sqm - neighborhood_median_ppsqm)
                / nullif(neighborhood_stddev_ppsqm, 0)
            )), 3
        ) as ppsqm_z_score,

        -- Opportunity Score: invert z, scale 0-100, clamp.
        -- Score 100 = 3+ std below median (very undervalued)
        -- Score 50  = at median
        -- Score 0   = 3+ std above median (very overvalued)
        round(
            greatest(0, least(100,
                50 - (
                    greatest(-3.0, least(3.0,
                        (price_per_sqm - neighborhood_median_ppsqm)
                        / nullif(neighborhood_stddev_ppsqm, 0)
                    ))
                ) * (50.0 / 3.0)
            )), 1
        ) as opportunity_score,

        -- Human-readable tier (useful for Streamlit badge colour)
        case
            when opportunity_score >= 75 then 'great_deal'
            when opportunity_score >= 55 then 'good_deal'
            when opportunity_score >= 45 then 'fair'
            when opportunity_score >= 25 then 'overpriced'
            else 'very_overpriced'
        end as deal_tier,

        -- Flag listings with too few neighborhood comps (score unreliable)
        neighborhood_listing_count < 10 as low_confidence_flag

    from joined
)

select * from scored