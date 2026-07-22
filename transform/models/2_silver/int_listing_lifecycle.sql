-- silver/int_listing_lifecycle.sql
-- Behavioural signals per listing, derived from the accumulated snapshot history.
--
-- €/m² cheapness is a STATIC signal. How long a flat has sat on the market and
-- whether the seller has already cut the price are BEHAVIOURAL signals — usually a
-- stronger indication of a *negotiable* deal than price alone (a listing sitting
-- 90 days with two price cuts = motivated seller). This model collapses the raw
-- snapshot stream (int_listings_history: one row per observation) into ONE row per
-- listing_pk with days-on-market and price-trajectory metrics.
--
-- Correct from day one; it simply lights up as the daily pipeline accumulates more
-- than one snapshot per listing. With a single snapshot, days_on_market = 0 and
-- n_price_changes = 0 (honest "no behavioural signal yet"), not a fabricated one.
{{ config(materialized='table', schema='silver') }}

with history as (
    select
        listing_pk,
        price_eur,
        scraped_date,
        _loaded_at
    from {{ ref('int_listings_history') }}
),

-- Detect price movements between consecutive observations of the same listing.
sequenced as (
    select
        listing_pk,
        price_eur,
        lag(price_eur) over (partition by listing_pk order by _loaded_at) as _prev_price
    from history
),

price_changes as (
    select
        listing_pk,
        count(*) filter (
            where _prev_price is not null and price_eur <> _prev_price
        ) as n_price_changes
    from sequenced
    group by 1
),

bounds as (
    select
        listing_pk,
        min(scraped_date)                as first_seen_date,
        max(scraped_date)                as last_seen_date,
        count(*)                         as n_snapshots,
        -- first/last observed price, ordered by ingestion time
        arg_min(price_eur, _loaded_at)   as first_price_eur,
        arg_max(price_eur, _loaded_at)   as last_price_eur
    from history
    group by 1
)

select
    b.listing_pk,
    b.first_seen_date,
    b.last_seen_date,
    b.n_snapshots,
    date_diff('day', b.first_seen_date, b.last_seen_date)  as days_on_market,
    b.first_price_eur,
    b.last_price_eur,
    coalesce(pc.n_price_changes, 0)                        as n_price_changes,
    round(
        case
            when b.first_price_eur > 0
                then (b.last_price_eur - b.first_price_eur) / b.first_price_eur * 100.0
            else 0
        end, 2
    )                                                      as price_change_pct,
    (b.last_price_eur < b.first_price_eur)                 as price_dropped
from bounds b
left join price_changes pc using (listing_pk)
