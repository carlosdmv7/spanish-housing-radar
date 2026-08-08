# ADR 0002 — MotherDuck (DuckDB) warehouse with a dbt medallion

**Status:** accepted

## Context
The project needs a warehouse a single developer can run end to end, that is free
at this scale (thousands of rows, not billions), SQL-first, and that dbt and
Streamlit can both read without an access layer in between. Snowflake, BigQuery
and Redshift all clear the technical bar but add cost and operational overhead
for no analytical benefit at this volume.

## Decision
MotherDuck (managed DuckDB) on the free tier, via `dbt-duckdb`. Schemas are
`raw` (written by the extraction pipeline) then `main_bronze` / `main_silver` /
`main_gold`, owned by dbt — a `generate_schema_name` override
(`transform/macros/generate_schema_name.sql`) makes models land in exactly those
names rather than `<target>_<schema>`. The Streamlit app connects with the same
`md:` DSN and reads only the gold layer. CI targets an isolated `ci_*` schema so
a broken PR can never overwrite what the live app reads.

## Consequences
- Free and zero-ops at this scale; the app queries the warehouse directly with no
  API tier to build or host.
- The dbt project stays **warehouse-agnostic** — the same `ref()`/`source()` SQL
  runs on Snowflake with a profile swap, so the modelling work transfers 1:1.
- DuckDB connections are **not thread-safe**: the app shares one cached
  connection across Streamlit sessions and must issue a per-call `cursor()`
  (`app/connection.py`) or two concurrent visitors crash the server.
- DuckDB's nullable-integer columns arrive as pandas extension dtypes whose
  `pd.NA` breaks chart serialisation, so the app downcasts centrally on read.
- Free-tier limits are a real ceiling; sustained daily scraping would eventually
  force a paid tier or a warehouse move.

## Alternatives rejected
- **Snowflake / BigQuery / Redshift.** All three clear the bar technically and
  all three are what the job market asks for, which was a real argument for
  choosing one. Rejected because at thousands of rows they add cost, credentials
  and cold-start latency for no analytical benefit — and because the dbt project
  is warehouse-agnostic, so the modelling work that *is* the transferable skill
  transfers with a profile swap. Nothing is being avoided here except a bill.
- **Local DuckDB file committed to the repo.** Free, simple, no network. Rejected
  because the deployed Streamlit app and the CI job would each read a different
  frozen copy, and the file would either be stale or turn every pipeline run into
  a binary diff in git history.
- **Postgres (Supabase/Neon free tier).** A real shared database, and a defensible
  choice. Rejected because dbt-postgres at this volume gains nothing over DuckDB
  while giving up DuckDB's columnar scan speed on the wide aggregations the app
  runs on every page load, and because it adds a connection-pool problem to a
  single-process Streamlit app.
- **An API tier between the app and the warehouse.** Correct for a multi-tenant
  product, premature here. It would exist only to hide a `SELECT` behind HTTP,
  and the app's queries are already confined to the gold contract.
