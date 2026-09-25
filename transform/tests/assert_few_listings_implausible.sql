-- Warns when more than 3% of a city's listings for one operation are set aside
-- as implausible (int_listings_screened), counted only where there are 30+.
--
-- One typo in a few hundred listings is the portal's data; one in twenty is our
-- parser. A change in Idealista's card markup that shifts the size into the
-- price, or drops a digit, would not fail a single range test — every value
-- would still be a positive number — but it would flood the screen, and the
-- app would quietly lose listings without anyone being told. This is the alarm.
{{ config(severity='warn') }}

select
    municipality,
    operation_type,
    count(*)                                                        as listings,
    count(*) filter (where dq_issue = 'implausible_price_per_sqm')  as implausible
from {{ ref('int_listings_screened') }}
group by 1, 2
having count(*) >= 30
   and count(*) filter (where dq_issue = 'implausible_price_per_sqm') > 0.03 * count(*)
