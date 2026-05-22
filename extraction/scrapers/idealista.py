"""
Idealista HTML scraper.

Strategy: search-card-only (no detail pages) → 1 Scrapfly credit per 30 listings.
All fields extracted from the <article class="item"> card on search result pages.

Selector reference (Idealista 2026):
  <article class="item">
    <a class="item-link" href="/inmueble/12345678/" title="Piso en venta en Malasaña, Madrid">
    <span class="item-price">350.000<span>€</span></span>
    <div class="item-detail-char">
      <span class="item-detail">3 hab.</span>
      <span class="item-detail">90 m²</span>
      <span class="item-detail">2 baños</span>
    </div>
    <p class="item-description">free-text description</p>
  </article>
"""
from __future__ import annotations

import logging
import re
from typing import Iterator
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag

from extraction.config import (
    IDEALISTA_BASE_URL,
    IDEALISTA_MAX_LISTINGS,
    IDEALISTA_MAX_SEARCH_PAGES,
    IDEALISTA_SELECTORS,
    get_idealista_search_url,
)
from extraction.scrapers.base import AbstractScraper

logger = logging.getLogger(__name__)


class IdealistaScraper(AbstractScraper):
    source_name = "idealista"

    # ── AbstractScraper interface ─────────────────────────────────────────────

    def _paginate(self, operation: str = "sale") -> Iterator[dict]:
        search_url = get_idealista_search_url(self.province, operation)
        logger.info("[idealista] Starting: province=%s op=%s url=%s", self.province, operation, search_url)

        yielded = 0
        for page in range(1, IDEALISTA_MAX_SEARCH_PAGES + 1):
            page_url = self._build_page_url(search_url, page)
            logger.info("[idealista] Fetching page %d → %s", page, page_url)

            try:
                html = self._get_html(page_url)
            except Exception as exc:
                logger.warning("[idealista] Could not fetch page %d: %s", page, exc)
                break

            if self._is_blocked(html):
                logger.error(
                    "[idealista] Anti-bot page detected. Set SCRAPFLY_ENABLED=true in .env."
                )
                break

            cards = self._parse_search_page(html, operation)
            logger.info("[idealista] Page %d → %d valid cards", page, len(cards))

            if not cards:
                break

            for card in cards:
                yield card
                yielded += 1
                if yielded >= IDEALISTA_MAX_LISTINGS:
                    logger.info("[idealista] Hit IDEALISTA_MAX_LISTINGS=%d", IDEALISTA_MAX_LISTINGS)
                    return

            self._polite_sleep()

    def _parse_listing(self, raw: dict) -> dict:
        return raw  # search-card mode builds dicts directly

    # ── Page → cards ──────────────────────────────────────────────────────────

    def _parse_search_page(self, html: str, operation: str) -> list[dict]:
        soup = BeautifulSoup(html, "lxml")
        results = []
        for card in soup.select(IDEALISTA_SELECTORS["search_card"]):
            if card.select_one(".item-adv-label"):
                continue  # skip promoted ads
            parsed = self._parse_search_card(card, operation)
            if parsed:
                results.append(parsed)
        return results

    def _parse_search_card(self, card: Tag, operation: str) -> dict | None:
        try:
            link_tag = card.select_one(IDEALISTA_SELECTORS["search_link"])
            if not link_tag:
                return None

            href  = link_tag.get("href", "")
            url   = urljoin(IDEALISTA_BASE_URL, href)
            sid   = self._extract_id(url)
            title = link_tag.get("title", "")

            if not sid:
                return None

            price = self._extract_price(card)
            if price is None:
                return None

            details = [
                s.get_text(" ", strip=True)
                for s in card.select(IDEALISTA_SELECTORS["search_details"])
            ]

            size = self._extract_size(details)
            if size is None:
                return None

            muni, district, hood = self._parse_location(title, self.province)

            return {
                "source_id":          sid,
                "source_name":        self.source_name,
                "raw_url":            url,
                "raw_price_eur":      price,
                "raw_operation_type": operation,
                "raw_size_sqm":       size,
                "raw_rooms":          self._extract_rooms(details),
                "raw_bathrooms":      self._extract_bathrooms(details),
                "raw_property_type":  self._property_type(title),
                "raw_lat":            None,
                "raw_lon":            None,
                "raw_municipality":   muni,
                "raw_district":       district,
                "raw_neighborhood":   hood,
            }
        except Exception as exc:
            logger.debug("[idealista] Card parse error: %s", exc, exc_info=True)
            return None

    # ── Field extractors ──────────────────────────────────────────────────────

    @staticmethod
    def _extract_price(card: Tag) -> float | None:
        """
        <span class="item-price">350.000<span>€</span></span>
        Clone → strip child spans → parse the number text.
        Spanish thousands separator is "." (no decimal part in prices).
        """
        tag = card.select_one(".item-price")
        if not tag:
            return None
        clone = BeautifulSoup(str(tag), "lxml").select_one(".item-price")
        for child in clone.find_all("span"):
            child.decompose()
        raw = clone.get_text(strip=True)
        m = re.search(r"([\d\.]+)", raw)
        if not m:
            return None
        return float(m.group(1).replace(".", ""))

    @staticmethod
    def _extract_size(details: list[str]) -> float | None:
        for t in details:
            m = re.search(r"(\d+(?:[,\.]\d+)?)\s*m[²2]", t, re.IGNORECASE)
            if m:
                return float(m.group(1).replace(",", "."))
        return None

    @staticmethod
    def _extract_rooms(details: list[str]) -> int | None:
        for t in details:
            m = re.search(r"(\d+)\s*(?:hab\.?|habitaci[oó]nes?|dormitorios?)", t, re.IGNORECASE)
            if m:
                return int(m.group(1))
        return None

    @staticmethod
    def _extract_bathrooms(details: list[str]) -> int | None:
        for t in details:
            m = re.search(r"(\d+)\s*ba[ñn]os?", t, re.IGNORECASE)
            if m:
                return int(m.group(1))
        return None

    @staticmethod
    def _property_type(title: str) -> str:
        t = title.lower()
        if any(k in t for k in ["chalet", "villa", "casa", "unifamiliar"]):
            return "house"
        if any(k in t for k in ["ático", "atico", "penthouse", "dúplex", "duplex"]):
            return "penthouse"
        if any(k in t for k in ["estudio", "studio", "loft"]):
            return "studio"
        return "apartment"

    @staticmethod
    def _parse_location(title: str, fallback: str) -> tuple[str, str | None, str | None]:
        """
        Title: "Piso en venta en Barrio Salamanca, Madrid"
        → municipality="madrid", district=None, neighbourhood="barrio salamanca"
        """
        m = re.search(r"\ben\s+(?:venta|alquiler)\s+en\s+(.+)$", title, re.IGNORECASE)
        loc = m.group(1).strip() if m else title
        parts = [p.strip().lower() for p in loc.split(",") if p.strip()]

        if not parts:         return fallback, None, None
        if len(parts) == 1:   return parts[0], None, None
        if len(parts) == 2:   return parts[1], None, parts[0]
        return parts[-1], parts[1], parts[0]

    @staticmethod
    def _extract_id(url: str) -> str | None:
        m = re.search(r"/inmueble/(\d+)/", url)
        return m.group(1) if m else None

    @staticmethod
    def _build_page_url(base: str, page: int) -> str:
        if page == 1:
            return base
        return base.rstrip("/") + f"/pagina-{page}.htm"

    @staticmethod
    def _is_blocked(html: str) -> bool:
        """
        Detect a genuine Idealista block page.

        Do NOT check for "captcha" or "datadome" — Idealista embeds DataDome
        JS on every page including successful ones (confirmed via debug_scrapfly.py).
        Only flag when hard block signals appear AND listings are absent.
        """
        h = html.lower()

        # These strings only appear on real interstitial/block pages
        hard_blocks = [
            "please enable js and disable any ad blocker",
            "acceso denegado",
            "429 too many requests",
        ]
        if any(s in h for s in hard_blocks):
            return True

        # Short response with no article tags = wall page, not listings
        if len(html) < 5_000 and "<article" not in h:
            return True

        return False
