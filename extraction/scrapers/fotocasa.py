"""
Fotocasa scraper — HTML-based (no official API).
NOTE: Web scraping may violate Fotocasa's ToS. Review their robots.txt
and terms before running in production. This is provided as a template.

The class inherits AbstractScraper so it slots straight into the loader
without any changes downstream.
"""
from __future__ import annotations

import logging
from typing import Iterator
from urllib.parse import urlencode

from bs4 import BeautifulSoup

from extraction.scrapers.base import AbstractScraper

logger = logging.getLogger(__name__)

# Province → Fotocasa URL slug
PROVINCE_SLUGS: dict[str, str] = {
    "madrid":    "madrid-provincia",
    "barcelona": "barcelona-provincia",
    "valencia":  "valencia-provincia",
    "sevilla":   "sevilla-provincia",
    "malaga":    "malaga-provincia",
    "alicante":  "alicante-provincia",
    "zaragoza":  "zaragoza-provincia",
    "bilbao":    "bizkaia-provincia",
    "valladolid":"valladolid-provincia",
    "palma":     "islas-baleares-provincia",
}

OPERATION_SLUGS = {"sale": "comprar", "rent": "alquiler"}


class FotocasaScraper(AbstractScraper):
    source_name = "fotocasa"
    BASE_URL = "https://www.fotocasa.es/es"

    def _paginate(self, operation: str = "sale") -> Iterator[dict]:
        province_slug = PROVINCE_SLUGS.get(self.province)
        op_slug = OPERATION_SLUGS.get(operation, "comprar")

        if not province_slug:
            logger.error("Province %r not in PROVINCE_SLUGS for Fotocasa.", self.province)
            return

        page = 1
        max_pages = 20

        while page <= max_pages:
            url = f"{self.BASE_URL}/{op_slug}/viviendas/{province_slug}/l?page={page}"
            try:
                resp = self._get(url)
            except Exception as exc:
                logger.error("Fotocasa fetch error page %d: %s", page, exc)
                break

            soup = BeautifulSoup(resp.text, "lxml")
            items = soup.select("article.re-CardPackMinimal")

            if not items:
                logger.debug("No items on page %d — stopping.", page)
                break

            for item in items:
                parsed = self._parse_listing_html(item, operation)
                if parsed:
                    yield parsed

            logger.debug("Fotocasa page %d — %d items", page, len(items))
            page += 1
            self._polite_sleep()

    def _parse_listing(self, raw: dict) -> dict:
        # Not used directly (HTML path uses _parse_listing_html)
        return raw

    def _parse_listing_html(self, article, operation: str) -> dict:
        """Extract fields from a Fotocasa listing card HTML element."""
        try:
            source_id = article.get("data-test-id") or article.get("id", "")
            price_tag = article.select_one("[class*='Price']")
            price_text = price_tag.get_text(strip=True).replace(".", "").replace("€", "").replace("\xa0", "") if price_tag else "0"
            price = float("".join(filter(lambda c: c.isdigit() or c == ".", price_text)) or 0)

            size_tag = article.select_one("[class*='surface']") or article.select_one("[aria-label*='m²']")
            size_text = size_tag.get_text(strip=True).replace("m²", "").strip() if size_tag else "0"
            size = float(size_text.replace(",", ".") or 0)

            rooms_tag = article.select_one("[aria-label*='habitacion']")
            rooms = int(rooms_tag.get_text(strip=True)) if rooms_tag else None

            location_tag = article.select_one("[class*='location']") or article.select_one("address")
            location_text = location_tag.get_text(strip=True) if location_tag else ""
            location_parts = [p.strip().lower() for p in location_text.split(",")]

            return {
                "source_id":          source_id or f"fc_{hash(article.get_text()[:50])}",
                "source_name":        self.source_name,
                "raw_price_eur":      price,
                "raw_operation_type": operation,
                "raw_size_sqm":       size,
                "raw_rooms":          rooms,
                "raw_bathrooms":      None,
                "raw_property_type":  "apartment",
                "raw_lat":            None,
                "raw_lon":            None,
                "raw_municipality":   self.province,
                "raw_district":       location_parts[1] if len(location_parts) > 1 else None,
                "raw_neighborhood":   location_parts[0] if location_parts else None,
            }
        except Exception as exc:
            logger.debug("Could not parse Fotocasa card: %s", exc)
            return {}
