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


def _sanitize_dtypes(df: pd.DataFrame) -> pd.DataFrame:
    """
    DuckDB maps nullable INTEGER columns to pandas' extension dtypes (Int32/
    Int64/boolean), whose missing value is `pd.NA`. Plotly serialises figures
    with orjson, which cannot encode `pd.NA` and raises
    "Type is not JSON serializable: NAType" the moment such a column reaches a
    chart's hover_data/customdata (e.g. `rooms`, `bathrooms`).

    Downcast those extension columns to plain numpy dtypes (float64 with NaN,
    or object) here — once, centrally — so every page and chart is safe.
    """
    for col in df.columns:
        dtype = df[col].dtype
        if pd.api.types.is_extension_array_dtype(dtype):
            if pd.api.types.is_integer_dtype(dtype) or pd.api.types.is_float_dtype(dtype):
                df[col] = df[col].astype("float64")
            elif pd.api.types.is_bool_dtype(dtype):
                df[col] = df[col].astype("object").where(df[col].notna(), None)
    return df


def query(sql: str, **params) -> pd.DataFrame:
    """
    Execute a SQL string and return a DataFrame.

    Values are bound as DuckDB named parameters ($name) — never string-formatted
    into the SQL — so user-driven filters can't break or inject into the query.
    """
    conn = get_connection()
    result = conn.execute(sql, params) if params else conn.execute(sql)
    return _sanitize_dtypes(result.df())
