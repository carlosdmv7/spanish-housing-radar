# extraction/schemas/raw_listings.py
"""
Pydantic v2 schema — validated before any row touches MotherDuck.
If a field is missing or the wrong type, the row is logged and skipped.
"""
from __future__ import annotations

import logging
from typing import ClassVar, Literal

from pydantic import BaseModel, Field, ValidationInfo, field_validator, model_validator

logger = logging.getLogger(__name__)


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

    # ── Card attributes, as the advertiser states them (ADR-0012) ────────────
    # Every one is optional and None means "the card does not say" — never
    # "no". A house has no floor, and a flat whose card omits the lift may well
    # have one. Floor is the storey as an integer: sótano/semi-sótano -1,
    # bajo/entreplanta 0, "Planta Nª" N; raw_floor_text keeps the span verbatim.
    raw_floor: int | None = None
    raw_floor_text: str | None = None
    raw_is_exterior: bool | None = None
    raw_has_lift: bool | None = None
    # 'included' (in the asking price) or 'optional' (sold separately, for
    # raw_garage_price_eur when the card states it).
    raw_garage: Literal["included", "optional"] | None = None
    raw_garage_price_eur: float | None = None
    raw_garage_text: str | None = None
    # The portal's own price-drop marker: the previous asking price it shows
    # struck through, and the cut as a percentage.
    raw_previous_price_eur: float | None = None
    raw_price_drop_pct: float | None = None
    raw_description: str | None = None
    # '|'-delimited, e.g. "Lujo|Villa".
    raw_tags: str | None = None

    # These attributes are secondary to the listing. A garbled one is a parser
    # problem, not a reason to lose a listing whose price, size and location are
    # sound — so an implausible value is dropped to None (and logged) instead of
    # failing validation the way a bad price or size does.
    _ATTRIBUTE_RANGES: ClassVar[dict[str, tuple[float, float]]] = {
        # Below ground is at most a few levels; Spain's tallest residential
        # towers have under 50 storeys.
        "raw_floor": (-3, 60),
        "raw_garage_price_eur": (1, 1_000_000),
        "raw_previous_price_eur": (1, 100_000_000),
        # A 0% or 100% "cut" is not a price drop.
        "raw_price_drop_pct": (0.01, 99.99),
    }

    @field_validator(
        "raw_floor", "raw_garage_price_eur", "raw_previous_price_eur", "raw_price_drop_pct",
    )
    @classmethod
    def implausible_attribute_is_unknown(cls, v: float | None, info: ValidationInfo) -> float | None:
        if v is None:
            return None
        lo, hi = cls._ATTRIBUTE_RANGES[info.field_name]
        if not (lo <= v <= hi):
            logger.warning("Dropping implausible %s=%r to None", info.field_name, v)
            return None
        return v

    @field_validator(
        "raw_floor_text", "raw_garage_text", "raw_description", "raw_tags",
    )
    @classmethod
    def blank_text_is_unknown(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        return v or None

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
