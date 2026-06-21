-- Silver layer: price evolution over time
-- Placeholder: {operation_type}, {municipality}

SELECT
    scraped_date,
    municipality,
    neighborhood,
    operation_type,
    property_type,
    COUNT(*)              AS total_listings,
    ROUND(MEDIAN(price_per_sqm), 2) AS median_ppsqm,
    ROUND(AVG(price_per_sqm), 2)    AS avg_ppsqm,
    ROUND(MEDIAN(price_eur), 0)     AS median_price
FROM spanish_housing_radar.main_silver.int_listings_history
WHERE operation_type = '{operation_type}'
  AND ('{municipality}' = 'all' OR municipality = '{municipality}')
GROUP BY 1, 2, 3, 4, 5
ORDER BY scraped_date ASC