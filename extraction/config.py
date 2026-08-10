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
# Cost: ~1 credit per search page with asp=True
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
# Table 25171 = IPV by CCAA, quarterly (base 2015 = 100).
INE_BASE_URL: str = os.getenv("INE_BASE_URL", "https://servicios.ine.es/wstempus/js/ES")
INE_HPI_TABLE_ID: str = os.getenv("INE_HPI_TABLE_ID", "25171")
INE_HPI_N_PERIODS: int = int(os.getenv("INE_HPI_N_PERIODS", "16"))  # ~4 years of quarters
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
