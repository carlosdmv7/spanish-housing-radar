-- silver/dim_neighborhoods.sql
-- Grain: one row per (municipality, neighborhood).
-- district is collapsed (max) so a neighbourhood that shows up under several
-- district spellings / null districts does not break neighborhood_pk uniqueness.
-- Centroids come from whatever coordinates the listings carry (scraped or filled
-- from the Valencia barrio seed in int_listings_unioned).
select
    municipality || '__' || coalesce(neighborhood, '(unknown)') as neighborhood_pk,
    municipality,
    district,
    neighborhood,
    centroid_lat,
    centroid_lon,
    null::varchar as ine_code
from (
    select
        municipality,
        neighborhood,
        max(district)       as district,
        round(avg(lat), 6)  as centroid_lat,
        round(avg(lon), 6)  as centroid_lon
    from {{ ref('int_listings_unioned') }}
    group by municipality, neighborhood
)
