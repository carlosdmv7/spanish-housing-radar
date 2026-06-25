-- Gold layer: filtered opportunities for the search page
-- Placeholders: {operation_type}, {property_type}, {municipality}, {min_price}, {max_price}

SELECT
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
    _loaded_at::date AS scraped_date
FROM spanish_housing_radar.main_gold.rpt_opportunities
WHERE operation_type = $operation_type
  AND ($property_type = 'all' OR property_type = $property_type)
  AND ($municipality = 'all'  OR municipality  = $municipality)
  AND price_eur BETWEEN $min_price AND $max_price
ORDER BY opportunity_score DESC