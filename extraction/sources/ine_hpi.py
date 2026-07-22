"""
INE Índice de Precios de Vivienda (IPV) fetcher.

Pulls the official, transaction-based Spanish house-price index from the INE
Tempus3 JSON API (public, no key, no proxy) and returns validated records.

The API returns a list of series objects; each series `Nombre` encodes
"{Region}. {HousingType}. {Metric}." and carries a `Data` array of quarterly
observations. We parse the name into canonical slugs and flatten Data into one
IneHpiRecord per observation.

Reference: https://servicios.ine.es/wstempus/js/ES/DATOS_TABLA/{table}?nult={n}
"""
from __future__ import annotations

from datetime import UTC, datetime
import logging

import requests

from extraction.config import (
    INE_BASE_URL,
    INE_HPI_N_PERIODS,
    INE_HPI_TABLE_ID,
    INE_TIMEOUT_SECONDS,
)
from extraction.schemas.ine_records import (
    HOUSING_TYPE_SLUGS,
    METRIC_SLUGS,
    IneHpiRecord,
)

logger = logging.getLogger(__name__)


def _parse_series_name(nombre: str) -> tuple[str, str, str] | None:
    """
    "Comunitat Valenciana. Vivienda segunda mano. Índice." →
        ("Comunitat Valenciana", "second_hand", "index")

    Region names may contain commas ("Madrid, Comunidad de") but never ". ",
    so splitting on ". " cleanly yields [region, housing_type, metric].
    Returns None for any label we don't recognise (defensive against INE adding
    new breakdowns).
    """
    # INE names end with ". " (period + trailing space), e.g. "Nacional. General. Índice. "
    # — strip trailing periods/spaces first so the split yields exactly 3 segments.
    parts = [p.strip() for p in nombre.strip().rstrip(". ").split(". ")]
    if len(parts) != 3:
        return None
    region, raw_type, raw_metric = parts
    housing_type = HOUSING_TYPE_SLUGS.get(raw_type)
    metric = METRIC_SLUGS.get(raw_metric)
    if not housing_type or not metric:
        return None
    return region, housing_type, metric


def fetch_ine_hpi(
    table_id: str = INE_HPI_TABLE_ID,
    n_periods: int = INE_HPI_N_PERIODS,
) -> list[IneHpiRecord]:
    """Fetch + parse + validate the last `n_periods` quarters of the IPV table."""
    url = f"{INE_BASE_URL}/DATOS_TABLA/{table_id}"
    logger.info("[ine] Fetching IPV table %s (nult=%d) → %s", table_id, n_periods, url)

    resp = requests.get(url, params={"nult": n_periods}, timeout=INE_TIMEOUT_SECONDS)
    resp.raise_for_status()
    series_list = resp.json()

    records: list[IneHpiRecord] = []
    skipped_series = 0
    for series in series_list:
        parsed = _parse_series_name(series.get("Nombre", ""))
        if parsed is None:
            skipped_series += 1
            continue
        region, housing_type, metric = parsed
        cod = series.get("COD", "")

        for obs in series.get("Data", []):
            valor = obs.get("Valor")
            fecha_ms = obs.get("Fecha")
            if valor is None or fecha_ms is None:
                continue  # suppressed / secret value
            period_date = datetime.fromtimestamp(fecha_ms / 1000, tz=UTC).date()
            try:
                records.append(
                    IneHpiRecord(
                        series_cod=cod,
                        region=region,
                        housing_type=housing_type,
                        metric=metric,
                        period_date=period_date,
                        year=period_date.year,
                        value=float(valor),
                    )
                )
            except Exception as exc:  # pydantic validation — log and skip
                logger.debug("[ine] Skipped invalid observation: %s", exc)

    logger.info(
        "[ine] Parsed %d observations (%d series skipped as unrecognised).",
        len(records), skipped_series,
    )
    return records
