# extraction/schemas/raw_listings.py
"""
Pydantic v2 schema — validated before any row touches MotherDuck.
If a field is missing or the wrong type the row is logged and skipped,
so a bad scrape never silently corrupts the Bronze layer.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, field_validator, model_validator


class RawListing(BaseModel):
    """Represents one property listing from any source portal."""

    # ── Identifiers ───────────────────────────────────────────────────────────
    source_id: str = Field(..., description="Portal's own ID for the listing")
    source_name: str = Field(..., description="e.g. 'idealista' or 'fotocasa'")

    # ── Price ─────────────────────────────────────────────────────────────────
    raw_price_eur: float = Field(..., gt=0)
    raw_operation_type: str = Field(..., description="'sale' or 'rent'")

    # ── Physical attributes ───────────────────────────────────────────────────
    raw_size_sqm: float = Field(..., gt=0, lt=10_000)
    raw_rooms: Optional[int] = Field(None, ge=0, le=50)
    raw_bathrooms: Optional[int] = Field(None, ge=0, le=20)
    raw_property_type: str = Field(..., description="Normalised in Silver layer")

    # ── Location ──────────────────────────────────────────────────────────────
    raw_lat: Optional[float] = Field(None, ge=35.0, le=44.0)   # Spain bounding box
    raw_lon: Optional[float] = Field(None, ge=-9.5, le=4.5)
    raw_municipality: str
    raw_district: Optional[str] = None
    raw_neighborhood: Optional[str] = None

    # ── Pipeline metadata (set by loader, not scraper) ────────────────────────
    _loaded_at: datetime = datetime.utcnow()
    _run_id: str = "manual"

    @field_validator("raw_operation_type")
    @classmethod
    def normalise_operation(cls, v: str) -> str:
        mapping = {"sale": "sale", "buy": "sale", "sell": "sale",
                   "rent": "rent", "alquiler": "rent", "venta": "sale"}
        normalised = mapping.get(v.lower().strip())
        if not normalised:
            raise ValueError(f"Unknown operation type: {v!r}")
        return normalised

    @model_validator(mode="after")
    def price_per_sqm_sanity(self) -> "RawListing":
        ppsqm = self.raw_price_eur / self.raw_size_sqm
        # Catches obvious data errors (price in cents, size in cm²…)
        if self.raw_operation_type == "sale" and not (100 < ppsqm < 50_000):
            raise ValueError(f"Implausible sale price/sqm: {ppsqm:.0f} €/m²")
        if self.raw_operation_type == "rent" and not (1 < ppsqm < 200):
            raise ValueError(f"Implausible rent price/sqm: {ppsqm:.2f} €/m²/mo")
        return self
