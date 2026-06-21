-- silver/dim_neighborhoods.sql
-- Grain: one row per (municipality, neighborhood).
-- district is collapsed (max) so a neighbourhood that shows up under several
-- district spellings / null districts does not break neighborhood_pk uniqueness.
select
    municipality || '__' || coalesce(neighborhood, '(unknown)') as neighborhood_pk,
    municipality,
    district,
    neighborhood,
    -- enriquecimiento futuro:
    null::float as centroid_lat,
    null::float as centroid_lon,
    null::varchar as ine_code
from (
    select
        municipality,
        neighborhood,
        max(district) as district
    from {{ ref('int_listings_unioned') }}
    group by municipality, neighborhood
)