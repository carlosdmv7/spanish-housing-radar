-- Gold: current listings enriched for affordability analysis
-- Placeholder: {operation_type}, {municipality}

SELECT
    listing_pk,
    municipality,
    district,
    neighborhood,
    operation_type,
    property_type,
    price_eur,
    size_sqm,
    rooms,
    price_per_sqm,
    opportunity_score,
    deal_tier
FROM spanish_housing_radar.main_gold.rpt_opportunities
WHERE operation_type = '{operation_type}'
  AND ('{municipality}' = 'all' OR municipality = '{municipality}')