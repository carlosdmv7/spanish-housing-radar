"""
INE Atlas de Distribución de Renta de los Hogares (ADRH) — income by district.

Why this exists: the opportunity score says a flat is cheap *for its barrio*, but
never whether that barrio is cheap because it is a bargain or because nobody there
can afford more. District income is the missing denominator, and unlike listing
prices it is an official, transaction-grounded figure that does not evaporate when
an advert is taken down.

**Why a 64 MB CSV instead of the API.** The Tempus3 JSON API cannot serve table
30824: unfiltered it answers "No puede mostrarse por restricciones de volumen",
and every documented `tv=` filter combination returns HTTP 500. The bulk export
is the only route that works, so this streams it and discards ~99.9% of the rows
rather than pretending the API is an option. The data is annual, so the download
happens roughly once a year in anger.

Reference: https://www.ine.es/jaxiT3/Tabla.htm?t=30824 (ADRH, INE)
"""
from __future__ import annotations

import csv
import io
import logging

import requests

from extraction.schemas.ine_records import IneIncomeRecord

logger = logging.getLogger(__name__)

ADRH_CSV_URL = "https://www.ine.es/jaxiT3/files/t/es/csv_bdsc/30824.csv"
ADRH_TABLE_ID = "30824"

# The six indicators the table publishes, mapped to stable slugs. Anything not
# listed here is skipped rather than guessed at, so a new INE breakdown lands as
# a missing metric instead of a mislabelled one.
METRIC_SLUGS: dict[str, str] = {
    "Renta neta media por persona":         "net_income_per_person",
    "Renta neta media por hogar":           "net_income_per_household",
    "Renta bruta media por persona":        "gross_income_per_person",
    "Renta bruta media por hogar":          "gross_income_per_household",
    "Media de la renta por unidad de consumo":   "mean_income_per_consumption_unit",
    "Mediana de la renta por unidad de consumo": "median_income_per_consumption_unit",
}


def _parse_amount(raw: str) -> float | None:
    """
    "22.047" → 22047.0

    Spanish thousands separator is ".", and INE writes a missing value as "." or
    an empty string. A missing income must never become 0.0: a district reported
    as earning nothing would sail through every range test and quietly wreck any
    ratio built on it.
    """
    text = (raw or "").strip()
    if not text or text in {".", "..", "-"}:
        return None
    text = text.replace(".", "").replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return None


def _split_code_name(cell: str) -> tuple[str, str] | None:
    """`"4625001 València distrito 01"` → `("4625001", "València distrito 01")`."""
    text = (cell or "").strip()
    if not text:
        return None
    code, _, name = text.partition(" ")
    if not code.isdigit() or not name:
        return None
    return code, name.strip()


def fetch_ine_income(
    municipality_codes: set[str],
    *,
    url: str = ADRH_CSV_URL,
    timeout: int = 300,
) -> list[IneIncomeRecord]:
    """
    District-level income rows for the given INE municipality codes.

    `municipality_codes` are 5-digit INE codes ("46250" for València). Filtering
    at the source is what makes a 3-million-row file tractable: everything else
    is discarded as it streams past.

    Only **district** rows are kept — those with a district set and no census
    section. Section rows are a finer grain than any listing this app holds, and
    keeping them would inflate the table 20× for data nothing can join to.
    """
    logger.info("[ine-income] Downloading ADRH table %s (~64 MB)…", ADRH_TABLE_ID)
    response = requests.get(url, timeout=timeout, stream=True)
    response.raise_for_status()
    response.encoding = "utf-8-sig"

    records: list[IneIncomeRecord] = []
    skipped_metric = 0
    reader = csv.DictReader(io.StringIO(response.text), delimiter=";")

    for row in reader:
        municipality_cell = (row.get("Municipios") or "").strip()
        district_cell = (row.get("Distritos") or "").strip()
        section_cell = (row.get("Secciones") or "").strip()

        if not district_cell or section_cell:
            continue  # municipality totals and census sections are not our grain

        municipality = _split_code_name(municipality_cell)
        if municipality is None or municipality[0] not in municipality_codes:
            continue

        district = _split_code_name(district_cell)
        if district is None:
            continue

        metric = METRIC_SLUGS.get((row.get("Indicadores de renta media") or "").strip())
        if metric is None:
            skipped_metric += 1
            continue

        value = _parse_amount(row.get("Total", ""))
        if value is None:
            continue  # INE suppresses small-sample cells; absent is not zero

        try:
            year = int((row.get("Periodo") or "").strip())
        except ValueError:
            continue

        records.append(
            IneIncomeRecord(
                municipality_code=municipality[0],
                municipality_name=municipality[1],
                district_code=district[0],
                district_name=district[1],
                metric=metric,
                year=year,
                value=value,
            )
        )

    logger.info(
        "[ine-income] Kept %d district rows for %d municipalities (%d rows had an "
        "unrecognised indicator).",
        len(records), len(municipality_codes), skipped_metric,
    )
    return records
