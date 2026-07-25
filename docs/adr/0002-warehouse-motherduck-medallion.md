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
