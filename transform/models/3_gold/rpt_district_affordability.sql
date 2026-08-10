-- gold/rpt_district_affordability.sql
-- Asking prices divided by what the people who live there actually earn.
--
-- Every other figure in this warehouse compares a flat to other flats. That
-- answers "is this cheap for the area?" and cannot answer "is this area cheap?"
-- — a barrio can be inexpensive because it is a bargain or because nobody there
-- can afford more, and €/m² alone does not distinguish those. Household income
-- from INE's ADRH is the missing denominator, and unlike a listing it does not
-- disappear when the advert comes down.
--
-- Grain: one row per municipality × district × operation × property type.
-- Districts, not barrios: ADRH's finer grain is the census section, which is
-- finer than anything this app can join to, so the district is the honest floor.
{{ config(materialized='table', schema='gold') }}

with listings as (
    select * from {{ ref('int_listings_current') }}
    where district is not null
),

income as (
    select * from {{ ref('int_district_income') }}
),

price_by_district as (
    select
        municipality,
        district,
        operation_type,
        property_type,
        count(*)                          as listings,
        median(price_eur)                 as median_price_eur,
        median(price_per_sqm)             as median_ppsqm,
        median(size_sqm)                  as median_size_sqm
    from listings
    group by 1, 2, 3, 4
)

select
    p.municipality,
    p.district,
    p.operation_type,
    p.property_type,
    p.listings,
    round(p.median_price_eur, 0)          as median_price_eur,
    round(p.median_ppsqm, 0)              as median_ppsqm,
    round(p.median_size_sqm, 0)           as median_size_sqm,

    i.reference_year                      as income_reference_year,
    i.net_income_per_person,
    i.net_income_per_household,

    -- The headline: gross years of household income to buy outright, ignoring
    -- financing entirely. Deliberately gross and deliberately simple — the
    -- moment a mortgage rate enters, the number stops being a property of the
    -- district and starts being a property of the borrower.
    case
        when p.operation_type = 'sale' and i.net_income_per_household > 0
        then round(p.median_price_eur / i.net_income_per_household, 1)
    end                                   as years_of_household_income,

    -- For rentals the same question is asked monthly: what share of a household's
    -- net income the median rent consumes. Above ~30% is the threshold most
    -- housing statistics treat as overburden.
    case
        when p.operation_type = 'rent' and i.net_income_per_household > 0
        then round(p.median_price_eur * 12 / i.net_income_per_household * 100, 1)
    end                                   as rent_pct_of_household_income

from price_by_district p
-- LEFT, not INNER: a district with no income figure still belongs in this table
-- with a null ratio. Dropping it would silently shrink the map to the districts
-- INE happens to cover, which is the same omission ADR-0005 argues against.
left join income i
  on p.municipality = i.municipality
 and p.district     = i.district
