# extraction/schemas/raw_listings.py
"""
Pydantic v2 schema — validated before any row touches MotherDuck.
If a field is missing or the wrong type, the row is logged and skipped.
"""
from __future__ import annotations

from pydantic import BaseModel, Field, field_validator, model_validator


class RawListing(BaseModel):
    """Represents one property listing from any source portal."""

    # ── Identifiers ───────────────────────────────────────────────────────────
    source_id: str = Field(..., description="Portal's own ID for the listing")
    source_name: str = Field(..., description="e.g. 'idealista'")
    raw_url: str | None = Field(None, description="Original listing URL")

    # ── Price ─────────────────────────────────────────────────────────────────
    raw_price_eur: float = Field(..., gt=0)
    raw_operation_type: str = Field(..., description="'sale' or 'rent'")

    # ── Physical attributes ───────────────────────────────────────────────────
    raw_size_sqm: float = Field(..., gt=0, lt=10_000)
    raw_rooms: int | None = Field(None, ge=0, le=50)
    raw_bathrooms: int | None = Field(None, ge=0, le=20)
    raw_property_type: str = Field(..., description="Normalised in Silver layer")

    # ── Location ──────────────────────────────────────────────────────────────
    raw_lat: float | None = Field(None, ge=35.0, le=44.0)
    raw_lon: float | None = Field(None, ge=-9.5, le=4.5)
    raw_municipality: str
    raw_district: str | None = None
    raw_neighborhood: str | None = None
    # The portal's own listing title, kept verbatim. The three fields above are
    # the output of a text heuristic run over it; storing the input is what makes
    # a later parser fix applicable to rows already in the warehouse. Optional so
    # a source that has no title (Fotocasa parses structured fields) still
    # validates.
    raw_title: str | None = None

    @field_validator("raw_operation_type")
    @classmethod
    def normalise_operation(cls, v: str) -> str:
        mapping = {
            "sale": "sale",
            "buy": "sale",
            "sell": "sale",
            "venta": "sale",
            "rent": "rent",
            "alquiler": "rent",
        }

        normalised = mapping.get(v.lower().strip())

        if not normalised:
            raise ValueError(f"Unknown operation type: {v!r}")

        return normalised

    @model_validator(mode="after")
    def price_per_sqm_sanity(self) -> RawListing:
        ppsqm = self.raw_price_eur / self.raw_size_sqm

        if self.raw_operation_type == "sale" and not (100 < ppsqm < 50_000):
            raise ValueError(f"Implausible sale price/sqm: {ppsqm:.0f} €/m²")

        if self.raw_operation_type == "rent" and not (1 < ppsqm < 200):
            raise ValueError(f"Implausible rent price/sqm: {ppsqm:.2f} €/m²/month")

        return self
