-- transform/models/gold/rpt_opportunities.sql
{{ config(materialized='view', schema='gold') }}

with scored as (
    select * from {{ ref('fct_listings_scored') }}
),

lifecycle as (
    select * from {{ ref('int_listing_lifecycle') }}
)

select
    s.listing_pk,
    s.source_name,
    s.url,
    s.municipality,
    s.district,
    s.neighborhood,
    s.neighborhood_is_canonical,
    s.operation_type,
    s.property_type,
    s.price_eur,
    s.size_sqm,
    s.rooms,
    s.price_per_sqm,
    s.neighborhood_median_ppsqm,
    s.ppsqm_vs_median,
    s.ppsqm_z_score,
    s.opportunity_score,
    s.deal_tier,
    s.benchmark_level,
    s.benchmark_comp_count,
    s.low_confidence_flag,

    -- ── Behavioural signals (int_listing_lifecycle) ──────────────────────────
    -- Coalesced so a listing seen only once reads as "no signal yet" (0 / false)
    -- rather than null. Lights up as the daily pipeline accumulates snapshots.
    l.first_seen_date,
    coalesce(l.days_on_market, 0)   as days_on_market,
    coalesce(l.n_price_changes, 0)  as n_price_changes,
    coalesce(l.price_change_pct, 0) as price_change_pct,
    coalesce(l.price_dropped, false) as price_dropped,

    -- Composite "how motivated is the seller" label. Deliberately conservative:
    -- a listing only reaches 'high' on a real behavioural trigger (long on market,
    -- OR multiple cuts, OR a ≥5% drop), so it never over-promises on thin history.
    case
        when coalesce(l.days_on_market, 0) >= 60
             or coalesce(l.n_price_changes, 0) >= 2
             or coalesce(l.price_change_pct, 0) <= -5 then 'high'
        when coalesce(l.days_on_market, 0) >= 21
             or coalesce(l.n_price_changes, 0) >= 1 then 'medium'
        else 'low'
    end as seller_motivation,

    s.lat,
    s.lon,
    s._loaded_at
from scored s
left join lifecycle l using (listing_pk)
-- low_confidence listings are surfaced (not hidden) so the app can flag them
-- instead of silently dropping rows when even the city grain is thin
