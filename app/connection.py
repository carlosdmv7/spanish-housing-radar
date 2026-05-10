# app/connection.py
import os
import duckdb
import streamlit as st

@st.cache_resource
def get_connection() -> duckdb.DuckDBPyConnection:
    """
    Opens a single MotherDuck connection per Streamlit worker.
    Token is read from environment; never hardcode it.
    """
    token = os.environ["MOTHERDUCK_TOKEN"]
    conn = duckdb.connect(f"md:spanish_housing_radar?motherduck_token={token}")
    return conn