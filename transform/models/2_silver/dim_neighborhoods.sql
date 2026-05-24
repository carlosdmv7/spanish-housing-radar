-- silver/dim_neighborhoods.sql
select
    municipality || '__' || neighborhood   as neighborhood_pk,  -- DT_NEIGHBORHOODS.neighborhood_pk
    municipality,
    district,
    neighborhood,
    -- enriquecimiento futuro:
    null::float as centroid_lat,
    null::float as centroid_lon,
    null::varchar as ine_code
from (
    select distinct municipality, district, neighborhood
    from {{ ref('int_listings_unioned') }}
)