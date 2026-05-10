# app/queries/listings.sql
select
    listing_id,
    municipality,
    neighborhood,
    operation_type,
    property_type,
    price_eur,
    size_sqm,
    rooms,
    price_per_sqm,
    opportunity_score,
    deal_tier,
    lat,
    lon
from gold.rpt_opportunities
where operation_type  = $1
  and municipality    = any($2::varchar[])
  and property_type   = any($3::varchar[])
  and price_eur between $4 and $5
  and opportunity_score >= $6
order by opportunity_score desc
limit 500