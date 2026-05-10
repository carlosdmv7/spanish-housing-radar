"""
Idealista HTML scraper.

This scraper does not use the official Idealista API. It extracts listing URLs
from public search pages and then parses each listing detail page.

Keep the first version intentionally small:
- limited pages
- limited listings
- slow request rate
- no phone numbers
- no personal/contact data
"""
from __future__ import annotations

import logging
import re
from typing import Iterator
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from extraction.config import (
    IDEALISTA_BASE_URL,
    IDEALISTA_MAX_LISTINGS,
    IDEALISTA_MAX_SEARCH_PAGES,
    IDEALISTA_SEARCH_URLS,
)
from extraction.constants import IDEALISTA_SELECTORS
from extraction.scrapers.base import AbstractScraper

logger = logging.getLogger(__name__)


class IdealistaScraper(AbstractScraper):
    source_name = "idealista"

    def _paginate(self, operation: str = "sale") -> Iterator[dict]:
        search_url = IDEALISTA_SEARCH_URLS.get((self.province, operation))

        if not search_url:
            raise ValueError(
                f"No Idealista search URL configured for province={self.province!r}, "
                f"operation={operation!r}. Add it to IDEALISTA_SEARCH_URLS in config.py."
            )

        listing_urls = self._collect_listing_urls(search_url)

        logger.info(
            "Collected %d Idealista listing URLs for province=%s operation=%s",
            len(listing_urls),
            self.province,
            operation,
        )

        for idx, url in enumerate(listing_urls, start=1):
            logger.info("Scraping listing %d/%d: %s", idx, len(listing_urls), url)

            try:
                response = self._get(url)
            except Exception as exc:
                logger.warning("Failed to fetch listing url=%s error=%s", url, exc)
                continue

            parsed = self._parse_listing_html(response.text, url=url, operation=operation)

            if parsed:
                yield parsed

            self._polite_sleep()

    def _collect_listing_urls(self, first_page_url: str) -> list[str]:
        urls: list[str] = []
        seen: set[str] = set()

        for page in range(1, IDEALISTA_MAX_SEARCH_PAGES + 1):
            page_url = self._build_search_page_url(first_page_url, page)

            logger.info("Scraping Idealista search page %d: %s", page, page_url)

            try:
                response = self._get(page_url)
            except Exception as exc:
                logger.warning("Failed to fetch search page=%s error=%s", page_url, exc)
                break

            page_urls = self._parse_search_page(response.text, base_url=page_url)

            logger.info("Found %d listing URLs on search page %d", len(page_urls), page)

            if not page_urls:
                break

            for url in page_urls:
                if url not in seen:
                    seen.add(url)
                    urls.append(url)

                if len(urls) >= IDEALISTA_MAX_LISTINGS:
                    return urls

            self._polite_sleep()

        return urls

    @staticmethod
    def _build_search_page_url(first_page_url: str, page: int) -> str:
        if page == 1:
            return first_page_url

        return first_page_url.rstrip("/") + f"/pagina-{page}.htm"

    def _parse_search_page(self, html: str, base_url: str) -> list[str]:
        soup = BeautifulSoup(html, "lxml")

        links = soup.select(IDEALISTA_SELECTORS["listing_link"])

        urls = []
        for link in links:
            href = link.get("href")

            if not href:
                continue

            absolute_url = urljoin(IDEALISTA_BASE_URL, href)

            if "/inmueble/" not in absolute_url:
                continue

            urls.append(absolute_url)

        return urls

    def _parse_listing(self, raw: dict) -> dict:
        """
        Required by AbstractScraper.

        Not used directly because this scraper parses HTML pages rather than API dicts.
        """
        return raw

    def _parse_listing_html(self, html: str, url: str, operation: str) -> dict:
        soup = BeautifulSoup(html, "lxml")

        try:
            source_id = self._extract_source_id(url)

            price = self._extract_price(soup)
            size_sqm = self._extract_size_sqm(soup)

            if price is None or size_sqm is None:
                raise ValueError("Missing price or size")

            location_text = self._text_or_none(
                soup.select_one(IDEALISTA_SELECTORS["location"])
            )

            municipality, district, neighborhood = self._parse_location(location_text)

            return {
                "source_id": source_id,
                "source_name": self.source_name,
                "raw_url": url,
                "raw_price_eur": price,
                "raw_operation_type": operation,
                "raw_size_sqm": size_sqm,
                "raw_rooms": self._extract_rooms(soup),
                "raw_bathrooms": self._extract_bathrooms(soup),
                "raw_property_type": "home",
                "raw_lat": None,
                "raw_lon": None,
                "raw_municipality": municipality or self.province,
                "raw_district": district,
                "raw_neighborhood": neighborhood,
            }

        except Exception as exc:
            logger.debug("Could not parse listing url=%s error=%s", url, exc)
            return {}

    @staticmethod
    def _extract_source_id(url: str) -> str:
        match = re.search(r"/inmueble/(\d+)/", url)
        if not match:
            raise ValueError(f"Could not extract source_id from URL: {url}")
        return match.group(1)

    @staticmethod
    def _extract_price(soup: BeautifulSoup) -> float | None:
        price_node = soup.select_one(IDEALISTA_SELECTORS["price"])

        if not price_node:
            return None

        text = price_node.get_text(" ", strip=True)

        # Examples: "350.000 €", "1.250 €/mes"
        match = re.search(r"([\d\.,]+)", text)

        if not match:
            return None

        return float(match.group(1).replace(".", "").replace(",", "."))

    @staticmethod
    def _extract_size_sqm(soup: BeautifulSoup) -> float | None:
        feature_texts = [
            node.get_text(" ", strip=True)
            for node in soup.select(IDEALISTA_SELECTORS["features"])
        ]

        for text in feature_texts:
            normalized = text.lower().replace(".", "")
            match = re.search(r"(\d+(?:,\d+)?)\s*m²", normalized)

            if match:
                return float(match.group(1).replace(",", "."))

        return None

    @staticmethod
    def _extract_rooms(soup: BeautifulSoup) -> int | None:
        feature_texts = [
            node.get_text(" ", strip=True).lower()
            for node in soup.select(IDEALISTA_SELECTORS["features"])
        ]

        for text in feature_texts:
            match = re.search(r"(\d+)\s*(hab|habitaciones|dormitorios)", text)

            if match:
                return int(match.group(1))

        return None

    @staticmethod
    def _extract_bathrooms(soup: BeautifulSoup) -> int | None:
        feature_texts = [
            node.get_text(" ", strip=True).lower()
            for node in soup.select(IDEALISTA_SELECTORS["features"])
        ]

        for text in feature_texts:
            match = re.search(r"(\d+)\s*(baño|baños)", text)

            if match:
                return int(match.group(1))

        return None

    @staticmethod
    def _parse_location(location_text: str | None) -> tuple[str | None, str | None, str | None]:
        if not location_text:
            return None, None, None

        parts = [part.strip().lower() for part in location_text.split(",") if part.strip()]

        # Idealista often shows things like:
        # "Barrio de Salamanca, Madrid"
        # "Russafa, València"
        # "La Dreta de l'Eixample, Barcelona"
        if len(parts) == 1:
            return parts[0], None, None

        if len(parts) == 2:
            neighborhood = parts[0]
            municipality = parts[1]
            return municipality, None, neighborhood

        neighborhood = parts[0]
        district = parts[1]
        municipality = parts[-1]

        return municipality, district, neighborhood

    @staticmethod
    def _text_or_none(node) -> str | None:
        if not node:
            return None

        text = node.get_text(" ", strip=True)
        return text or None