-- silver/int_listings_valid.sql
-- The current listings that passed the screen in int_listings_screened. Every
-- benchmark, score and area statistic reads from here, so a listing set aside
-- there is set aside everywhere at once — no consumer has to remember a filter.
{{ config(materialized='view', schema='silver') }}

select * exclude (city_median_ppsqm, ppsqm_to_city_ratio, reference_scraped_date, dq_issue)
from {{ ref('int_listings_screened') }}
where dq_issue is null
