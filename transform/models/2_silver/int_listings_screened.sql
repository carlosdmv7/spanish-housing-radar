-- silver/int_listings_screened.sql
-- Every current listing with a verdict on whether it may be used: `dq_issue` is
-- null when it may, otherwise the reason it may not. Grain: one row per
-- listing_pk. Everything downstream reads `int_listings_valid`, the passing rows;
-- this model keeps the rest so the app can show what was set aside and why
-- (ADR-0009).
--
-- Bronze already drops what is impossible row by row: no price, no size, or more
-- than €50,000/m². What it cannot see is a listing that is wrong only next to
-- the others. A rent in Russafa of €1,300 a month for 707 m² — one bedroom —
-- passed every rule, came out at €1.84/m² against a city median near €17, and
-- was the highest-scoring "great deal" in València: a typo for 70 m². It also
-- widened the spread of its barrio's benchmark, which quietly flattened the
-- score of every other rent there.
--
-- Size on its own cannot catch that — Aravaca has a real 775 m² house. Price per
-- m² against the city can: a typo in either the price or the size moves it by an
-- order of magnitude, and no real flat in one city asks a quarter, or four
-- times, what the city's typical flat asks per m².
{{ config(materialized='table', schema='silver') }}

{% set ratio = var('max_ppsqm_ratio_to_city', 4) %}
{% set max_age = var('max_listing_age_days', 60) %}

with listings as (
    select * from {{ ref('int_listings_current') }}
),

-- Per city and operation, not per property type: a house and a flat ask within
-- a third of each other per m², far inside the factor of four, and a city with
-- nine houses for rent still has a few hundred rentals to take a median from.
city as (
    select
        municipality,
        operation_type,
        median(price_per_sqm) as city_median_ppsqm,
        -- A city's clock is its own last scrape, not today: a paused pipeline
        -- must not empty the app, and the cities held as one older snapshot are
        -- as current as they are ever going to be.
        max(scraped_date)     as city_last_scraped_date
    from listings
    group by 1, 2
)

select
    l.*,
    c.city_median_ppsqm,
    round(l.price_per_sqm / nullif(c.city_median_ppsqm, 0), 3) as ppsqm_to_city_ratio,
    c.city_last_scraped_date,
    case
        when l.price_per_sqm < c.city_median_ppsqm / {{ ratio }}
          or l.price_per_sqm > c.city_median_ppsqm * {{ ratio }}
            then 'implausible_price_per_sqm'
        -- Not seen for two months while the scraper kept visiting the city: most
        -- likely sold or withdrawn. Last seen is not proof of anything, but a
        -- page that says "right now" must not lead with a flat that left in July.
        when l.scraped_date < c.city_last_scraped_date - interval {{ max_age }} day
            then 'not_seen_recently'
    end as dq_issue
from listings l
join city c using (municipality, operation_type)
