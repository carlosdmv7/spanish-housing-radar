"""
MotherDuck connection — cached singleton for the entire Streamlit session.
One connection shared across all pages; never re-opened on re-runs.
"""
from __future__ import annotations

import os

from dotenv import load_dotenv
import duckdb
import pandas as pd
import streamlit as st

load_dotenv()


def _get_secret(key: str, default: str | None = None) -> str | None:
    """
    Read config from either Streamlit Cloud secrets (st.secrets) or the
    local environment (.env / os.environ), in that order.

    This lets the same code run unchanged locally and on Streamlit Community
    Cloud, where there is no .env file and secrets arrive via st.secrets.
    """
    try:
        if key in st.secrets:
            return st.secrets[key]
    except Exception:
        # st.secrets raises if no secrets.toml exists — fall back to env.
        pass
    return os.environ.get(key, default)


@st.cache_resource
def get_connection() -> duckdb.DuckDBPyConnection:
    token = _get_secret("MOTHERDUCK_TOKEN")
    if not token:
        raise RuntimeError(
            "MOTHERDUCK_TOKEN is not set. Add it to .env locally, or to the "
            "app's Secrets in Streamlit Community Cloud."
        )
    db   = _get_secret("MOTHERDUCK_DATABASE", "spanish_housing_radar")
    conn = duckdb.connect(f"md:{db}?motherduck_token={token}")
    return conn


def query(sql: str, **params) -> pd.DataFrame:
    """Execute a SQL string and return a DataFrame. Supports {param} placeholders."""
    conn = get_connection()
    if params:
        sql = sql.format(**params)
    return conn.execute(sql).df()
