-- silver/int_listings_unioned.sql
-- The multi-source spine. Today only Idealista is ingested; Fotocasa staging is
-- a zero-row placeholder (raw.fotocasa_listings not populated yet). The UNION +
-- cross-source dedup below is written so that the moment Fotocasa data lands, the
-- same listing scraped from both portals collapses to one row (lowest price wins).
{{ config(materialized='incremental', unique_key='snapshot_pk', schema='silver') }}

with idealista as (
    select * from {{ ref('stg_idealista__listings') }}
),

-- Placeholder until raw.fotocasa_listings exists; returns zero rows today.
-- fotocasa as (
--     select * from {{ ref('stg_fotocasa__listings') }}
-- ),

all_sources as (
    select * from idealista
    -- union all
    -- select * from fotocasa
),

-- Canonical Valencia barrio names + approximate centroids. Used to (a) collapse
-- spelling variants (russafa/ruzafa) so a real barrio reaches the comparable
-- threshold, and (b) geocode listings whose scraped lat/lon are null.
barrios as (
    select * from {{ ref('valencia_barrios') }}
),

normalised as (
    select
        s.snapshot_pk,
        s.listing_pk,
        s.source_id,
        s.source_name,
        s.url,
        s.price_eur,
        s.size_sqm,
        {{ price_per_sqm('s.price_eur', 's.size_sqm') }} as price_per_sqm,
        s.rooms,
        case s.property_type
            when 'flat'      then 'apartment'
            when 'apartment' then 'apartment'
            when 'penthouse' then 'apartment'
            when 'house'     then 'house'
            when 'chalet'    then 'house'
            else 'other'
        end                                              as property_type,
        s.operation_type,
        -- geocode from the barrio seed when the scraper returned no coordinates
        coalesce(s.lat, b.lat)                           as lat,
        coalesce(s.lon, b.lon)                           as lon,
        s.municipality,
        coalesce(b.district, s.district)                 as district,
        coalesce(b.neighborhood, s.neighborhood)         as neighborhood,
        (b.neighborhood is not null)                     as neighborhood_is_canonical,
        s.scraped_date,
        s._loaded_at,
        s._run_id,
        s.dq_bad_price,
        s.dq_bad_size,
        s.dq_extreme_ppsqm
    from all_sources s
    left join barrios b
        on  s.municipality = b.municipality
        and lower(trim(s.neighborhood)) = b.alias
    {% if is_incremental() %}
        where s._loaded_at > (select max(_loaded_at) from {{ this }})
    {% endif %}
),

-- Cross-source dedup: if the same physical listing is scraped from >1 portal in
-- the same run, keep the cheapest. No-op while Idealista is the only source.
deduped as (
    select *,
        row_number() over (
            partition by municipality, neighborhood, size_sqm, rooms, price_eur, _run_id
            order by price_eur asc, source_name asc
        ) as _dedup_rn
    from normalised
)

select * exclude (_dedup_rn)
from deduped
where _dedup_rn = 1
  and not dq_bad_price
  and not dq_bad_size
  and not dq_extreme_ppsqm
