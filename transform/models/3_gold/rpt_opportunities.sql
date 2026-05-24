-- transform/models/gold/rpt_opportunities.sql
{{ config(materialized='view', schema='gold') }}

select
    listing_pk,
    source_name,
    municipality,
    district,
    neighborhood,
    operation_type,
    property_type,
    price_eur,
    size_sqm,
    rooms,
    bathrooms,
    price_per_sqm,
    neighborhood_median_ppsqm,
    ppsqm_vs_median,
    opportunity_score,
    deal_tier,
    low_confidence_flag,
    lat,
    lon,
    _loaded_at
from {{ ref('fct_listings_scored') }}
-- Only expose listings with enough neighborhood data to be meaningful
where low_confidence_flag = false