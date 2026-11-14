"""
Centralised config — all settings from environment variables.
python-dotenv loads .env automatically.

URL GENERATION
──────────────
Instead of maintaining a dict with one entry per city × operation,
we build URLs programmatically.  To add a new city you only need to
add it to SCRAPING_CITIES (and optionally _IDEALISTA_SLUG_OVERRIDES
if its URL slug differs from the default pattern).

Idealista slug pattern: {city}-{city}  (e.g. madrid-madrid)
Override needed when city ≠ province:  bilbao-vizcaya, palma-illes-balears
"""
from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import quote

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")


# ── MotherDuck ────────────────────────────────────────────────────────────────
MOTHERDUCK_TOKEN: str = os.environ["MOTHERDUCK_TOKEN"]
MOTHERDUCK_DATABASE: str = os.getenv("MOTHERDUCK_DATABASE", "spanish_housing_radar")
MOTHERDUCK_DSN: str = f"md:{MOTHERDUCK_DATABASE}?motherduck_token={MOTHERDUCK_TOKEN}"


# ── Generic scraping ──────────────────────────────────────────────────────────
SCRAPER_DELAY_SECONDS: float = float(os.getenv("SCRAPER_DELAY_SECONDS", "3.0"))
SCRAPER_MAX_RETRIES: int = int(os.getenv("SCRAPER_MAX_RETRIES", "2"))
SCRAPER_TIMEOUT_SECONDS: int = int(os.getenv("SCRAPER_TIMEOUT_SECONDS", "20"))

DEFAULT_HEADERS: dict[str, str] = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
    "Connection": "keep-alive",
}


# ── Scrapfly ──────────────────────────────────────────────────────────────────
# Free tier: 1 000 credits/month. pip install scrapfly-sdk
# Cost: 25 credits per search page. ASP is billed at a flat rate whether or not
# render_js is on, so the whole monthly budget is 40 pages ≈ 1 200 listings.
# Measured, not estimated — see ADR-0001. Every page here is a budget decision.
SCRAPFLY_ENABLED: bool = os.getenv("SCRAPFLY_ENABLED", "false").lower() == "true"
SCRAPFLY_API_KEY: str = os.getenv("SCRAPFLY_API_KEY", "")
SCRAPFLY_ASP: bool = os.getenv("SCRAPFLY_ASP", "true").lower() == "true"
SCRAPFLY_COUNTRY: str = os.getenv("SCRAPFLY_COUNTRY", "ES")
SCRAPFLY_RENDER_JS: bool = os.getenv("SCRAPFLY_RENDER_JS", "false").lower() == "true"


# ── Cities to scrape ──────────────────────────────────────────────────────────
# Single source of truth — add a city here and it appears in both scrapers
# and the CLI automatically.
SCRAPING_CITIES: list[str] = [
    "madrid",
    "barcelona",
    "valencia",
    "sevilla",
    "malaga",
    "bilbao",
    "alicante",
    "zaragoza",
    "palma",
    "valladolid",
]
VALID_PROVINCES = SCRAPING_CITIES   # alias used by CLI


# ══════════════════════════════════════════════════════════════════════════════
# IDEALISTA
# ══════════════════════════════════════════════════════════════════════════════

IDEALISTA_BASE_URL: str = "https://www.idealista.com"

# Credit-saving levers — keep low in dev, raise in production
IDEALISTA_MAX_SEARCH_PAGES: int = int(os.getenv("IDEALISTA_MAX_SEARCH_PAGES", "1"))
IDEALISTA_MAX_LISTINGS: int = int(os.getenv("IDEALISTA_MAX_LISTINGS", "30"))

# Which listings the pages we can afford actually show. Idealista's default is
# "relevance", and relevance is sticky: 77 of the 107 sale listings on
# 2026-09-22 had already been seen in August, so a week's credits bought about
# 30 new flats. Newest first buys a fresh page of the market every week, and
# with int_listings_screened dropping anything unseen for 60 days, the pool is
# then roughly the last two months of new listings — which is what "on the
# market right now" means. The cost: a listing is rarely seen twice, so days on
# market and price cuts light up less often (ADR-0010). Empty string restores
# Idealista's default.
IDEALISTA_SORT: str = os.getenv("IDEALISTA_SORT", "fecha-publicacion-desc")

# Most cities follow {city}-{city}. List ONLY the exceptions here.
_IDEALISTA_SLUG_OVERRIDES: dict[str, str] = {
    "bilbao":     "bilbao-vizcaya",
    "palma":      "palma-illes-balears",
    "santander":  "santander-cantabria",
    "donostia":   "donostia-san-sebastian-gipuzkoa",
    "vitoria":    "vitoria-gasteiz-araba",
    "pamplona":   "pamplona-irunea-navarra",
}

_IDEALISTA_OP_SLUGS: dict[str, str] = {
    "sale": "venta-viviendas",
    "rent": "alquiler-viviendas",
}


def get_idealista_search_url(city: str, operation: str) -> str:
    """
    Build an Idealista search URL for any city + operation.

    Examples:
      get_idealista_search_url("madrid", "sale")
        → "https://www.idealista.com/venta-viviendas/madrid-madrid/"
      get_idealista_search_url("bilbao", "rent")
        → "https://www.idealista.com/alquiler-viviendas/bilbao-vizcaya/"
    """
    op_slug = _IDEALISTA_OP_SLUGS.get(operation)
    if not op_slug:
        raise ValueError(f"Unknown operation {operation!r}. Use 'sale' or 'rent'.")
    city_slug = _IDEALISTA_SLUG_OVERRIDES.get(city, f"{city}-{city}")
    return f"{IDEALISTA_BASE_URL}/{op_slug}/{city_slug}/"


# ── Zones: one search over an area no single municipality URL covers ─────────
# Idealista has no listing URL per comarca. What it does have is the "draw your
# area" search, /areas/<op>/?shape=((<polygon>)), and it links one from every
# search page it serves (seen on the València-province results page captured on
# 2026-11-14, debug_output/idealista_valencia_provincia_sale.html). The polygon
# is a Google encoded polyline, precision 5, wrapped in "((…))".
#
# One polygon over l'Horta Nord + Camp de Túria costs what one municipality page
# costs, and newest-first it returns whatever was just listed anywhere in it;
# one URL per town would be ~40 towns × 25+ credits a week. The edge follows the
# València city boundary and stays clear of Manises, Quart, Sagunt and the
# Serranos; whatever still lands outside the area is dropped by the scraper
# against the `comarca` column of transform/seeds/ccaa_by_municipality.csv.
#
# Vertices are (lat, lon), clockwise from the coast at Alboraia.
IDEALISTA_ZONES: dict[str, list[tuple[float, float]]] = {
    "horta-nord-camp-turia": [
        (39.497, -0.318),   # coast, Alboraia / Port Saplaya
        (39.635, -0.265),   # coast, Puçol / Sagunt line
        (39.655, -0.385),   # inland of Puçol, short of Segart
        (39.760, -0.450),   # Serra, Sierra Calderona
        (39.790, -0.530),   # Gátova / Marines
        (39.720, -0.640),   # Olocau / Casinos
        (39.700, -0.715),   # Casinos west
        (39.640, -0.690),   # short of Pedralba
        (39.570, -0.680),   # Vilamarxant west
        (39.500, -0.640),   # Loriguilla, short of Cheste
        (39.480, -0.560),   # Riba-roja south
        (39.505, -0.480),   # Paterna, north of Manises
        (39.497, -0.440),   # Paterna town, València boundary
        (39.500, -0.415),   # Burjassot / Benimàmet
        (39.497, -0.380),   # Tavernes Blanques / Orriols
    ],
}


def encode_polyline(points: list[tuple[float, float]]) -> str:
    """Google encoded polyline (precision 5), the format Idealista's shape= uses."""
    out: list[str] = []
    prev_lat = prev_lon = 0
    for lat, lon in points:
        ilat, ilon = round(lat * 1e5), round(lon * 1e5)
        for delta in (ilat - prev_lat, ilon - prev_lon):
            v = ~(delta << 1) if delta < 0 else delta << 1
            while v >= 0x20:
                out.append(chr((0x20 | (v & 0x1F)) + 63))
                v >>= 5
            out.append(chr(v + 63))
        prev_lat, prev_lon = ilat, ilon
    return "".join(out)


def get_idealista_zone_url(zone: str, operation: str) -> str:
    """
    The /areas/ search for a polygon in IDEALISTA_ZONES.

    The shape value is percent-encoded twice, exactly as Idealista's own links
    carry it ("%2528%2528…" for "(("): its front end decodes it once more.
    """
    op_slug = _IDEALISTA_OP_SLUGS.get(operation)
    if not op_slug:
        raise ValueError(f"Unknown operation {operation!r}. Use 'sale' or 'rent'.")
    shape = "((" + encode_polyline(IDEALISTA_ZONES[zone]) + "))"
    return f"{IDEALISTA_BASE_URL}/areas/{op_slug}/?shape={quote(quote(shape, safe=''), safe='')}"


def get_idealista_target_url(target: str, operation: str) -> str:
    """A zone key → its polygon search; anything else is a city slug."""
    if target in IDEALISTA_ZONES:
        return get_idealista_zone_url(target, operation)
    return get_idealista_search_url(target, operation)


# The scrape plan (which targets, how many pages each) is SCRAPE_TARGETS, parsed
# in shared/scrape_plan.py so the flow can read it without this module's
# MotherDuck settings.

# The comarca each municipality belongs to, from the same seed dbt reads — one
# list, so the scraper cannot keep a town the warehouse will reject.
SEED_MUNICIPALITIES_CSV = (
    Path(__file__).parent.parent / "transform" / "seeds" / "ccaa_by_municipality.csv"
)


def comarca_municipalities() -> set[str]:
    """Municipalities the seed assigns a comarca to (the towns, not the cities)."""
    import csv

    with SEED_MUNICIPALITIES_CSV.open(encoding="utf-8") as fh:
        return {r["municipality"] for r in csv.DictReader(fh) if r.get("comarca")}


# CSS selectors for Idealista search result pages (verified 2026).
# Update ONLY this dict if Idealista redesigns — scraper logic stays the same.
IDEALISTA_SELECTORS: dict[str, str] = {
    "search_card":    "article.item",
    "search_link":    "a.item-link",
    "search_price":   ".item-price",
    "search_details": ".item-detail-char span.item-detail",
    "search_desc":    ".item-description p",
    "search_tags":    ".listing-tags-container span",
    # Detail page (Phase 2 — not used yet)
    "detail_price":    ".info-data-price",
    "detail_title":    "h1 .main-info__title-main",
    "detail_location": ".main-info__title-minor",
    "detail_features": ".info-features span",
}


# ══════════════════════════════════════════════════════════════════════════════
# FOTOCASA
# ══════════════════════════════════════════════════════════════════════════════

FOTOCASA_BASE_URL: str = "https://www.fotocasa.es/es"

FOTOCASA_MAX_SEARCH_PAGES: int = int(os.getenv("FOTOCASA_MAX_SEARCH_PAGES", "1"))
FOTOCASA_MAX_LISTINGS: int = int(os.getenv("FOTOCASA_MAX_LISTINGS", "30"))

# Cities that need an explicit province slug (differs from just city name)
_FOTOCASA_SLUG_OVERRIDES: dict[str, str] = {
    "bilbao":     "vizcaya",
    "palma":      "islas-baleares",
    "valladolid": "valladolid",
}

_FOTOCASA_OP_SLUGS: dict[str, str] = {
    "sale": "comprar",
    "rent": "alquiler",
}


def get_fotocasa_search_url(city: str, operation: str) -> str:
    """
    Build a Fotocasa search URL.

    Examples:
      get_fotocasa_search_url("madrid", "sale")
        → ".../es/comprar/viviendas/madrid/todas-las-zonas/l"
      get_fotocasa_search_url("bilbao", "rent")
        → ".../es/alquiler/viviendas/vizcaya/todas-las-zonas/l"
    """
    op_slug = _FOTOCASA_OP_SLUGS.get(operation)
    if not op_slug:
        raise ValueError(f"Unknown operation {operation!r}. Use 'sale' or 'rent'.")
    city_slug = _FOTOCASA_SLUG_OVERRIDES.get(city, city)
    return f"{FOTOCASA_BASE_URL}/{op_slug}/viviendas/{city_slug}/todas-las-zonas/l"


# ── MotherDuck target tables ──────────────────────────────────────────────────
RAW_TABLE_MAP: dict[str, str] = {
    "idealista": "raw.idealista_listings",
    "fotocasa":  "raw.fotocasa_listings",
}


# ══════════════════════════════════════════════════════════════════════════════
# INE — Índice de Precios de Vivienda (official market context)
# ══════════════════════════════════════════════════════════════════════════════
# Public Tempus3 JSON API — no key, no proxy, no credits. Grounds the scraped
# ASKING prices against the official, transaction-based house-price index (IPV)
# so the app can show where the real market is heading, per autonomous community.
# Table 79563 = IPV by CCAA, quarterly (base 2025 = 100). INE rebased the index
# with the Q1 2026 release and published it under new tables and series codes;
# the old base-2015 table, 25171, stops at Q4 2025 and will not move again, so
# the warehouse sat at Q4 2025 while INE published two more quarters.
INE_BASE_URL: str = os.getenv("INE_BASE_URL", "https://servicios.ine.es/wstempus/js/ES")
INE_HPI_TABLE_ID: str = os.getenv("INE_HPI_TABLE_ID", "79563")
INE_HPI_N_PERIODS: int = int(os.getenv("INE_HPI_N_PERIODS", "20"))  # five years of quarters
INE_HPI_RAW_TABLE: str = "raw.ine_hpi"
# ADRH district income. Annual, so this refreshes about once a year in anger.
INE_INCOME_RAW_TABLE: str = "raw.ine_income"
# INE municipality codes we hold listings for, keyed by our own city slug. The
# 64 MB ADRH export is filtered against these as it streams, which is what makes
# a 3-million-row file tractable.
INE_MUNICIPALITY_CODES: dict[str, str] = {
    "valència": "46250",
}
INE_TIMEOUT_SECONDS: int = int(os.getenv("INE_TIMEOUT_SECONDS", "30"))
