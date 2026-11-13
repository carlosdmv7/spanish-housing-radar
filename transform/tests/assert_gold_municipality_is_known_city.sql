-- Fails if a municipality in gold is not a city the project knows about.
--
-- Regression test for "Piso En": a truncated Idealista title ("Piso en", nothing
-- after it) was parsed into the municipality `piso en`, and two rows carried it
-- all the way to fct_listings_scored and rpt_opportunities -- where the app
-- counted it as a city ("cities 2") and offered it in the Deals City picker.
-- No range, uniqueness or nullity test can see this; a wrong value that is
-- present, unique and not null satisfies all of them.
--
-- The reference list is the ccaa_by_municipality seed, which already has to name
-- every served city for the INE context to resolve. Adding a city to the scraper
-- therefore means adding it there -- and forgetting to is exactly what this
-- should fail on.
with known as (
    select municipality from {{ ref('ccaa_by_municipality') }}
),

used as (
    select 'fct_listings_scored' as model, municipality from {{ ref('fct_listings_scored') }}
    union
    select 'rpt_opportunities' as model, municipality from {{ ref('rpt_opportunities') }}
)

select u.model, u.municipality
from used u
left join known k on u.municipality = k.municipality
where k.municipality is null
