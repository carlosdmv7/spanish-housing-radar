# Spanish Housing Radar — pipeline image.
# Runs the Prefect daily flow (extract → dbt build) in a reproducible environment.
#
#   docker build -t housing-radar .
#   docker run --rm --env-file .env housing-radar                                  # full pipeline
#   docker run --rm --env-file .env --entrypoint dbt housing-radar \
#       build --project-dir transform --target prod                               # dbt only
#
# Required env vars (pass via --env-file or -e): MOTHERDUCK_TOKEN,
# SCRAPFLY_API_KEY, SCRAPFLY_ENABLED, and optionally PREFECT_API_KEY/URL to
# report runs to Prefect Cloud.
FROM python:3.12-slim

# System deps: gcc for any wheel that needs compiling; git for dbt deps hub pulls.
RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc git \
    && rm -rf /var/lib/apt/lists/*

# uv: fast, lockfile-reproducible dependency installs.
RUN pip install --no-cache-dir uv==0.11.12

WORKDIR /pipeline

# Layer-cache dependencies separately from source: sync from the lockfile only
# (no dev group, no project install — package = false in pyproject).
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev

# Put the uv-managed venv on PATH so `python` / `dbt` resolve without `uv run`.
ENV PATH="/pipeline/.venv/bin:$PATH"

COPY extraction/ extraction/
COPY orchestration/ orchestration/
COPY transform/ transform/

# dbt packages are resolved at build time so runs are fully offline-reproducible.
RUN dbt deps --project-dir transform

# Non-root user — the pipeline needs no elevated permissions.
RUN useradd --create-home pipeline && chown -R pipeline:pipeline /pipeline
USER pipeline

ENV DBT_PROFILES_DIR=/pipeline/transform

ENTRYPOINT ["python", "-m", "orchestration.flows.daily_pipeline"]
