-- silver/int_district_income.sql
-- Latest published income per district, joined to the district names this app
-- actually uses.
--
-- The join is the whole point and the fragile part. INE identifies districts by
-- number ("València distrito 01"); listings identify them by name ("ciutat
-- vella"). The `ine_districts` seed carries that mapping, sourced from the
-- Ajuntament's own published list rather than inferred from the data — inferring
-- it would mean deciding which barrio belongs to which district using the very
-- prices we are about to divide by income.
--
-- Only the most recent year is kept. ADRH publishes with a ~2-year lag and
-- revises prior years, so carrying every year forward would invite a stale one
-- to be picked up by mistake; the year is exposed as a column so the app can say
-- which one it is instead of implying the figure is current.
{{ config(materialized='table', schema='silver') }}

with income as (
    select * from {{ ref('stg_ine__income') }}
),

districts as (
    select * from {{ ref('ine_districts') }}
),

latest_year as (
    select district_code, max(year) as year
    from income
    group by 1
),

pivoted as (
    select
        i.district_code,
        i.year,
        max(case when i.metric = 'net_income_per_person'    then i.value end)
            as net_income_per_person,
        max(case when i.metric = 'net_income_per_household' then i.value end)
            as net_income_per_household,
        max(case when i.metric = 'median_income_per_consumption_unit' then i.value end)
            as median_income_per_consumption_unit
    from income i
    join latest_year ly
      on i.district_code = ly.district_code and i.year = ly.year
    group by 1, 2
)

select
    d.municipality,
    d.district,
    d.district_number,
    p.district_code,
    p.year                                  as reference_year,
    p.net_income_per_person,
    p.net_income_per_household,
    p.median_income_per_consumption_unit
from pivoted p
join districts d
  on p.district_code = d.ine_district_code
