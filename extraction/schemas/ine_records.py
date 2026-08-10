# extraction/schemas/ine_records.py
"""
Pydantic v2 schema for INE Índice de Precios de Vivienda (IPV) records.
One row = one region × housing_type × metric × quarter observation.
Validated before any row touches MotherDuck.
"""
from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field

# Canonical slugs — the raw Spanish labels are normalised here so downstream SQL
# never has to match accented strings.
HOUSING_TYPE_SLUGS: dict[str, str] = {
    "General":              "general",
    "Vivienda nueva":       "new",
    "Vivienda segunda mano": "second_hand",
}
METRIC_SLUGS: dict[str, str] = {
    "Índice":                       "index",
    "Variación trimestral":         "qoq",
    "Variación anual":              "yoy",
    "Variación en lo que va de año": "ytd",
}


class IneHpiRecord(BaseModel):
    """A single INE house-price-index observation."""

    series_cod: str = Field(..., description="INE series code (COD)")
    region: str = Field(..., description="Verbatim INE region name, e.g. 'Comunitat Valenciana'")
    housing_type: str = Field(..., description="general | new | second_hand")
    metric: str = Field(..., description="index | qoq | yoy | ytd")
    period_date: date = Field(..., description="Reference date of the quarter")
    year: int = Field(..., ge=2000, le=2100)
    value: float = Field(..., description="Index level (base 2015=100) or % variation")


class IneIncomeRecord(BaseModel):
    """
    One income observation for one district, one metric, one year.

    From the Atlas de Distribución de Renta de los Hogares. The grain is
    deliberately the *district* and not the census section: sections are finer
    than any listing this app holds, so keeping them would multiply the table
    twentyfold for data nothing could join to.
    """

    municipality_code: str = Field(..., min_length=5, max_length=5,
                                   description="5-digit INE municipality code, e.g. '46250'")
    municipality_name: str = Field(..., description="Verbatim INE name, e.g. 'València'")
    district_code: str = Field(..., min_length=7, max_length=7,
                               description="7-digit INE district code, e.g. '4625001'")
    district_name: str = Field(..., description="Verbatim, e.g. 'València distrito 01'")
    metric: str = Field(..., description="net_income_per_person | …")
    year: int = Field(..., ge=2000, le=2100)
    # No upper bound beyond sanity: this is euros per person or per household and
    # the two differ by roughly 2.5x, so one shared ceiling would be arbitrary.
    value: float = Field(..., gt=0)
