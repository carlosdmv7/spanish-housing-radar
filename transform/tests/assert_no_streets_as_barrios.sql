-- Fails if a street, a portal number or a property type is sitting in a
-- location column of the silver spine.
--
-- This is a regression test against a defect that reached production and stayed
-- there: the warehouse held barrios called "34", "7 -5", "chalet adosado en
-- russafa" and "piso en calle dels vivons", and `fct_listings_scored` grouped on
-- them as if they were places. Nothing failed, because nothing was looking --
-- the 89 existing tests checked ranges, uniqueness and nullity, all of which
-- garbage satisfies perfectly.
--
-- A benchmark built on a street name is not a wrong number, it is a wrong
-- *question*, and no range assertion can catch that. This is the assertion that
-- can.
-- Seed-confirmed names are exempt, for the same reason silver consults the seed
-- before the pattern: this test's first run failed on ten Málaga listings whose
-- district is "Carretera de Cádiz" — a genuine district of the city, rejected
-- for containing the word "carretera". A confirmed name is an area; the pattern
-- only has authority over names nothing vouches for.
with confirmed_areas as (
    select municipality, alias        as name from {{ ref('barrios_es') }}
    union
    select municipality, neighborhood as name from {{ ref('barrios_es') }}
    union
    select municipality, district     as name from {{ ref('barrios_es') }} where district is not null
)

select
    l.listing_pk,
    l.municipality,
    l.neighborhood,
    l.district
from {{ ref('int_listings_current') }} l
left join confirmed_areas cn
    on l.municipality = cn.municipality and l.neighborhood = cn.name
left join confirmed_areas cd
    on l.municipality = cd.municipality and l.district = cd.name
where (l.neighborhood is not null and cn.name is null and {{ is_not_an_area('l.neighborhood') }})
   or (l.district     is not null and cd.name is null and {{ is_not_an_area('l.district') }})
