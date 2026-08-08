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

-- Canonical barrio names + approximate centroids (Valencia, Madrid, Barcelona,
-- Sevilla, Málaga). Used to (a) collapse spelling variants (russafa/ruzafa) so a
-- real barrio reaches the comparable threshold, and (b) geocode listings whose
-- scraped lat/lon are null.
barrios as (
    select * from {{ ref('barrios_es') }}
),

-- Which municipalities the seed actually knows about. This matters because the
-- seed is complete for the cities it covers and absent for the rest: it holds
-- Madrid, València, Barcelona, Málaga and Sevilla, and not one row for Bilbao,
-- Valladolid or Zaragoza. Without this distinction, "the seed has never heard of
-- this city" is indistinguishable from "this is not a real barrio", and real
-- barrios -- Valladolid's Centro with 12 listings, Bilbao's Ensanche-Moyua --
-- get silently disqualified for the sin of being somewhere the seed does not go.
seed_coverage as (
    select distinct municipality, true as seed_covers_city from barrios
),

-- ── Location repair ───────────────────────────────────────────────────────────
-- The extraction heuristic mislabels two ways, and both are repaired here rather
-- than at the scraper, because silver rebuilds from raw and therefore fixes
-- history; the scraper only ever fixes the future.
--
--   1. Non-areas leak into either column -- street names, portal numbers,
--      property types -- and then serve as benchmark grouping keys.
--   2. When a street name lands in `neighborhood`, the *real* barrio is pushed
--      one slot along into `district`. "Piso en calle dels Vivons, Russafa,
--      Valencia" stored the street as the barrio and Russafa as the district,
--      which is why the seed is probed against both columns below -- and why
--      that probe recovers those listings without re-scraping one of them.
--
-- Order matters, and it is the opposite of the obvious one. The seed is
-- consulted FIRST and the pattern only judges what the seed could not confirm,
-- because a name a source vouches for is an area no matter what it looks like:
-- "Carretera de Cádiz" is one of Málaga's eleven official districts, and a
-- pattern that rejects anything containing "carretera" throws it away along with
-- the ten listings behind it.
known_districts as (
    select distinct municipality, district as name from barrios where district is not null
),

seeded as (
    select
        s.*,
        -- Prefer a hit on the neighbourhood slot; fall back to the district slot,
        -- which is where a mis-parsed title hides the real barrio.
        coalesce(bn.neighborhood, bd.neighborhood) as seed_neighborhood,
        coalesce(bn.district,     bd.district)     as seed_district,
        coalesce(bn.lat,          bd.lat)          as seed_lat,
        coalesce(bn.lon,          bd.lon)          as seed_lon,
        coalesce(sc.seed_covers_city, false)       as seed_covers_city,
        (kd.name is not null)                      as district_confirmed
    from all_sources s
    left join barrios bn
        on  s.municipality = bn.municipality and lower(trim(s.neighborhood)) = bn.alias
    left join barrios bd
        on  s.municipality = bd.municipality and lower(trim(s.district))     = bd.alias
    left join seed_coverage sc
        on  s.municipality = sc.municipality
    left join known_districts kd
        on  s.municipality = kd.municipality and lower(trim(s.district))     = kd.name
),

located as (
    select
        c.*,
        -- Scrub only the unconfirmed. A seed hit is positive evidence and
        -- overrides the pattern in both directions.
        case
            when c.seed_neighborhood is not null then c.neighborhood
            when {{ is_not_an_area('c.neighborhood') }} then null
            else c.neighborhood
        end as nbhd_scrubbed,
        case
            when c.district_confirmed or c.seed_district is not null then c.district
            when {{ is_not_an_area('c.district') }} then null
            else c.district
        end as district_scrubbed
    from seeded c
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
        coalesce(s.lat, s.seed_lat)                      as lat,
        coalesce(s.lon, s.seed_lon)                      as lon,
        s.municipality,
        coalesce(s.seed_district, s.district_scrubbed)   as district,
        -- A scrubbed-but-unrecognised name is kept, not discarded: it may well be
        -- a real barrio missing from the seed, and ADR-0005's rule is to show
        -- weak evidence flagged rather than hide it. What it does not get is the
        -- canonical flag -- and the scoring model benchmarks on canonical names
        -- only, so an unverified name can no longer manufacture a barrio grain.
        coalesce(s.seed_neighborhood, s.nbhd_scrubbed)   as neighborhood,

        -- Two different questions, deliberately kept apart.
        --
        -- `_is_canonical` — did a source confirm this name is a real barrio?
        -- Only the seed can answer yes. The app shows this as confidence.
        (s.seed_neighborhood is not null)                as neighborhood_is_canonical,

        -- `_is_benchmarkable` — may this name form a barrio-grain benchmark?
        -- Confirmed names always may. In a city the seed does not cover, a name
        -- that survived scrubbing also may: there is no evidence against it, and
        -- refusing it would disqualify every barrio in Bilbao, Valladolid and
        -- Zaragoza for a gap in our reference data rather than a defect in
        -- theirs. The `min_comps_for_benchmark` threshold is the backstop that
        -- makes this safe -- an unmarked street name is one street, and one
        -- street does not gather eight comparables.
        (
            s.seed_neighborhood is not null
            or (not s.seed_covers_city and s.nbhd_scrubbed is not null)
        )                                                as neighborhood_is_benchmarkable,
        s.scraped_date,
        s._loaded_at,
        s._run_id,
        s.dq_bad_price,
        s.dq_bad_size,
        s.dq_extreme_ppsqm
    from located s
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
