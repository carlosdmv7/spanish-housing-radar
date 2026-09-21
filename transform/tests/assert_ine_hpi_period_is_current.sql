-- Warns when the INE house-price index has stopped advancing.
--
-- This exists because the source freshness gate on `raw.ine_hpi` cannot catch
-- it. That gate measures `_loaded_at`, and the loader rewrites every row's
-- `_loaded_at` on every weekly run, so the table is *always* freshly loaded no
-- matter how old the data inside it is. `dbt source freshness` therefore passes
-- with a green PASS while the newest quarter in the table is a year behind —
-- which is exactly the state this test was written in.
--
-- Two different failure modes, two different checks:
--   * the loader stopped running      → source freshness on `_loaded_at`
--   * the loader runs, data is stale  → this test on `period_date`
-- Neither substitutes for the other, and only the first one existed.
--
-- WARN, not ERROR, and deliberately: the IPV advancing is INE's business, not
-- this pipeline's. A red build would assert a fault in code that is working
-- correctly, which is the same lie in the opposite direction. The app states
-- the reference quarter and its age on the Market page, so a visitor sees the
-- lag rather than inferring currency from a green badge.
{{ config(severity='warn') }}

with newest as (
    select max(period_date) as latest_period
    from {{ ref('stg_ine__hpi') }}
)

select
    latest_period,
    current_date - latest_period as days_behind
from newest
-- The IPV is quarterly and published roughly a quarter in arrears, so in normal
-- operation the newest period sits up to ~160 days back just before a release.
-- The threshold clears that gap without clearing a genuinely stalled feed.
where latest_period is null
   or current_date - latest_period > {{ var('max_ine_period_lag_days') }}
