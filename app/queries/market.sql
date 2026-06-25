-- Silver layer: neighborhood stats for the market overview page
-- Placeholder: {operation_type}, {municipality}

SELECT
    municipality,
    district,
    neighborhood,
    operation_type,
    property_type,
    total_listings,
    median_ppsqm,
    avg_ppsqm,
    stddev_ppsqm,
    p25_ppsqm,
    p75_ppsqm,
    median_size_sqm
FROM spanish_housing_radar.main_silver.int_neighborhood_stats
WHERE operation_type = $operation_type
  AND ($municipality = 'all' OR municipality = $municipality)
ORDER BY median_ppsqm DESC