-- transform/models/gold/rpt_opportunities.sql
{{ config(materialized='view', schema='gold') }}

select
    listing_pk,
    source_name,
    url,
    municipality,
    district,
    neighborhood,
    neighborhood_is_canonical,
    operation_type,
    property_type,
    price_eur,
    size_sqm,
    rooms,
    price_per_sqm,
    neighborhood_median_ppsqm,
    ppsqm_vs_median,
    ppsqm_z_score,
    opportunity_score,
    deal_tier,
    benchmark_level,
    benchmark_comp_count,
    low_confidence_flag,
    lat,
    lon,
    _loaded_at
from {{ ref('fct_listings_scored') }}
-- low_confidence listings are surfaced (not hidden) so the app can flag them
-- instead of silently dropping rows when even the city grain is thin
