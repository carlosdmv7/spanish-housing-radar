"""
Fotocasa HTML scraper.

Fotocasa is a Next.js app, so listing data is embedded in a
<script id="__NEXT_DATA__"> JSON blob on every page — much more reliable
than CSS selectors against React-generated class names.

Parse strategy (in order):
  1. __NEXT_DATA__ JSON  → structured, stable, preferred
  2. CSS selectors       → fallback if JSON path changes after a redeploy

Both paths output dicts with identical field names so the loader and
Pydantic schema don't care which path ran.

Credit budget:
  With SCRAPFLY_ENABLED=true: ~1 credit per search page (~20-30 listings).
  FOTOCASA_MAX_SEARCH_PAGES=2 → 2 credits → ~50 listings per city/op run.

Fotocasa search URL pattern:
  https://www.fotocasa.es/es/comprar/viviendas/{province}/todas-las-zonas/l
  Page 2 → same URL + ?page=2 query param
"""
from __future__ import annotations

from collections.abc import Iterator
import json
import logging
import re
from urllib.parse import parse_qs, urlencode, urljoin, urlparse, urlunparse

from bs4 import BeautifulSoup, Tag

from extraction.config import (
    FOTOCASA_BASE_URL,
    FOTOCASA_MAX_LISTINGS,
    FOTOCASA_MAX_SEARCH_PAGES,
    get_fotocasa_search_url,
)
from extraction.scrapers.base import AbstractScraper

logger = logging.getLogger(__name__)


class FotocasaScraper(AbstractScraper):
    source_name = "fotocasa"

    # ── AbstractScraper interface ─────────────────────────────────────────────

    def _paginate(self, operation: str = "sale") -> Iterator[dict]:
        search_url = get_fotocasa_search_url(self.province, operation)
        logger.info("[fotocasa] Starting: province=%s op=%s url=%s", self.province, operation, search_url)

        yielded = 0
        for page in range(1, FOTOCASA_MAX_SEARCH_PAGES + 1):
            page_url = self._build_page_url(search_url, page)
            logger.info("[fotocasa] Fetching page %d → %s", page, page_url)

            try:
                html = self._get_html(page_url)
            except Exception as exc:
                logger.warning("[fotocasa] Could not fetch page %d: %s", page, exc)
                break

            if self._is_blocked(html):
                logger.error("[fotocasa] Anti-bot page detected. Set SCRAPFLY_ENABLED=true.")
                break

            listings = self._parse_page(html, operation)
            logger.info("[fotocasa] Page %d → %d listings", page, len(listings))

            if not listings:
                break

            for item in listings:
                yield item
                yielded += 1
                if yielded >= FOTOCASA_MAX_LISTINGS:
                    logger.info("[fotocasa] Hit FOTOCASA_MAX_LISTINGS=%d", FOTOCASA_MAX_LISTINGS)
                    return

            self._polite_sleep()

    def _parse_listing(self, raw: dict) -> dict:
        return raw

    # ── Page parsing: JSON first, CSS fallback ────────────────────────────────

    def _parse_page(self, html: str, operation: str) -> list[dict]:
        """Try __NEXT_DATA__ JSON, then CSS fallback."""
        listings = self._parse_next_data(html, operation)
        if listings:
            logger.debug("[fotocasa] Parsed %d listings via __NEXT_DATA__", len(listings))
            return listings

        logger.debug("[fotocasa] __NEXT_DATA__ empty or missing — trying CSS fallback")
        listings = self._parse_css(html, operation)
        logger.debug("[fotocasa] CSS fallback → %d listings", len(listings))
        return listings

    # ── Strategy 1: __NEXT_DATA__ JSON ───────────────────────────────────────

    def _parse_next_data(self, html: str, operation: str) -> list[dict]:
        """
        Extract listings from the embedded Next.js data blob.

        Fotocasa embeds ALL listing data as JSON in:
          <script id="__NEXT_DATA__" type="application/json">{...}</script>

        The path through the JSON (as of 2026):
          props.pageProps.initialSearch.result.realEstates   ← list of listings

        If Fotocasa refactors, update the _find_listings_in_json() traversal.
        """
        script_tag = re.search(
            r'<script[^>]+id="__NEXT_DATA__"[^>]*>(.*?)</script>',
            html, re.DOTALL
        )
        if not script_tag:
            return []

        try:
            data = json.loads(script_tag.group(1))
        except json.JSONDecodeError as exc:
            logger.warning("[fotocasa] Could not parse __NEXT_DATA__ JSON: %s", exc)
            return []

        raw_listings = self._find_listings_in_json(data)
        if not raw_listings:
            logger.debug("[fotocasa] No listings array found in __NEXT_DATA__ — path may have changed.")
            return []

        results = []
        for item in raw_listings:
            parsed = self._parse_json_listing(item, operation)
            if parsed:
                results.append(parsed)
        return results

    @staticmethod
    def _find_listings_in_json(data: dict) -> list | None:
        """
        Walk known JSON paths where Fotocasa stores listing arrays.
        Returns the first non-empty list found, or None.
        """
        # Primary path (2025-2026)
        try:
            listings = (
                data["props"]["pageProps"]["initialSearch"]["result"]["realEstates"]
            )
            if isinstance(listings, list) and listings:
                return listings
        except (KeyError, TypeError):
            pass

        # Alternative: some pages use a different key
        try:
            listings = data["props"]["pageProps"]["initialProps"]["listings"]
            if isinstance(listings, list) and listings:
                return listings
        except (KeyError, TypeError):
            pass

        # Deep search: find any key "realEstates" anywhere in the top 4 levels
        def _deep_find(obj, target_key: str, depth: int = 0) -> list | None:
            if depth > 4:
                return None
            if isinstance(obj, dict):
                if target_key in obj and isinstance(obj[target_key], list):
                    return obj[target_key]
                for v in obj.values():
                    result = _deep_find(v, target_key, depth + 1)
                    if result:
                        return result
            return None

        return _deep_find(data, "realEstates") or _deep_find(data, "listings")

    def _parse_json_listing(self, item: dict, operation: str) -> dict | None:
        """Map a single Fotocasa JSON listing object to RawListing fields."""
        try:
            source_id = str(item.get("id") or item.get("propertyId") or "")
            if not source_id:
                return None

            # Price
            price_data = item.get("price") or item.get("prices") or {}
            if isinstance(price_data, dict):
                price = float(price_data.get("value") or price_data.get("amount") or 0)
            elif isinstance(price_data, int | float):
                price = float(price_data)
            else:
                price = 0.0
            if price <= 0:
                return None

            # Features — Fotocasa sends a list like:
            #   [{"key": "rooms", "value": 3}, {"key": "surface", "value": 90}]
            # or flat keys at the top level depending on the API version
            features = item.get("features") or item.get("characteristics") or []
            feature_map: dict[str, float] = {}
            if isinstance(features, list):
                for f in features:
                    if isinstance(f, dict):
                        k = str(f.get("key") or f.get("type") or "").lower()
                        v = f.get("value") or f.get("amount")
                        if k and v is not None:
                            feature_map[k] = float(v)
            elif isinstance(features, dict):
                feature_map = {k.lower(): float(v) for k, v in features.items() if v}

            # Surface / size — try several key spellings
            size = (
                feature_map.get("surface")
                or feature_map.get("area")
                or feature_map.get("constructedarea")
                or item.get("surface")
                or item.get("area")
            )
            if size is None or float(size) <= 0:
                return None

            rooms     = feature_map.get("rooms") or feature_map.get("bedrooms") or item.get("rooms")
            bathrooms = feature_map.get("bathrooms") or item.get("bathrooms")

            # Location
            address = item.get("address") or item.get("ubication") or {}
            if isinstance(address, dict):
                neighborhood = (
                    address.get("neighborhood") or
                    address.get("zone") or
                    address.get("barrio")
                )
                district = address.get("district") or address.get("distrito")
                municipality = (
                    address.get("municipality") or
                    address.get("city") or
                    address.get("municipio") or
                    self.province
                )
                lat = address.get("latitude") or address.get("lat")
                lon = address.get("longitude") or address.get("lng") or address.get("lon")
            else:
                neighborhood = district = None
                municipality = self.province
                lat = lon = None

            # URL
            url_path = item.get("url") or item.get("slug") or f"/inmuebles/{source_id}/"
            url = urljoin(FOTOCASA_BASE_URL, url_path)

            # Property type
            type_str = (
                item.get("propertyType") or
                item.get("typology") or
                item.get("type") or ""
            )
            prop_type = self._property_type(str(type_str))

            return {
                "source_id":          source_id,
                "source_name":        self.source_name,
                "raw_url":            url,
                "raw_price_eur":      price,
                "raw_operation_type": operation,
                "raw_size_sqm":       float(size),
                "raw_rooms":          int(rooms) if rooms is not None else None,
                "raw_bathrooms":      int(bathrooms) if bathrooms is not None else None,
                "raw_property_type":  prop_type,
                "raw_lat":            float(lat) if lat else None,
                "raw_lon":            float(lon) if lon else None,
                "raw_municipality":   str(municipality).lower().strip() if municipality else self.province,
                "raw_district":       str(district).lower().strip() if district else None,
                "raw_neighborhood":   str(neighborhood).lower().strip() if neighborhood else None,
            }

        except Exception as exc:
            logger.debug("[fotocasa] JSON listing parse error: %s", exc, exc_info=True)
            return None

    # ── Strategy 2: CSS fallback ──────────────────────────────────────────────

    def _parse_css(self, html: str, operation: str) -> list[dict]:
        """
        CSS fallback when __NEXT_DATA__ is absent.
        Fotocasa's React class names change often — use data attributes when possible.
        """
        soup = BeautifulSoup(html, "lxml")

        # Try several card selectors (class names rotate on deploys)
        card_selectors = [
            "article[data-testid='property-card']",
            "article.re-CardPackMinimal",
            "article.re-CardPackPremium",
            "[data-test='property-card']",
            "article[class*='Card']",
        ]

        cards: list[Tag] = []
        for selector in card_selectors:
            found = soup.select(selector)
            if found:
                cards = found
                logger.debug("[fotocasa] CSS: found %d cards with selector %r", len(found), selector)
                break

        if not cards:
            logger.warning("[fotocasa] CSS fallback: no cards found. HTML snippet: %s", html[:500])
            return []

        results = []
        for card in cards:
            parsed = self._parse_css_card(card, operation)
            if parsed:
                results.append(parsed)
        return results

    def _parse_css_card(self, card: Tag, operation: str) -> dict | None:
        try:
            # ID: usually in data-id or data-property-id attribute
            source_id = (
                card.get("data-id") or
                card.get("data-property-id") or
                card.get("data-testid") or
                card.get("id") or
                ""
            )
            if not source_id:
                return None
            source_id = re.sub(r"[^\d]", "", str(source_id))  # keep only digits
            if not source_id:
                return None

            # URL
            link = card.select_one("a[href*='/inmueble']") or card.select_one("a[href]")
            url = urljoin(FOTOCASA_BASE_URL, link.get("href", "")) if link else ""

            # Price — look for elements that likely contain price
            price_tag = (
                card.select_one("[data-testid='price']") or
                card.select_one("[class*='Price']") or
                card.select_one("[class*='price']")
            )
            price = self._css_extract_price(price_tag)
            if price is None:
                return None

            # All text snippets for regex extraction
            all_texts = [t.get_text(" ", strip=True) for t in card.find_all(True)]

            size      = self._css_extract_size(all_texts)
            rooms     = self._css_extract_rooms(all_texts)
            bathrooms = self._css_extract_bathrooms(all_texts)

            if size is None:
                return None

            # Location
            location_tag = (
                card.select_one("[data-testid='address']") or
                card.select_one("[class*='location']") or
                card.select_one("[class*='Location']") or
                card.select_one("address")
            )
            loc_text = location_tag.get_text(" ", strip=True) if location_tag else ""
            muni, district, hood = self._parse_location(loc_text, self.province)

            title_tag = card.select_one("[class*='title']") or card.select_one("h2") or card.select_one("h3")
            title = title_tag.get_text(strip=True) if title_tag else ""

            return {
                "source_id":          source_id,
                "source_name":        self.source_name,
                "raw_url":            url,
                "raw_price_eur":      price,
                "raw_operation_type": operation,
                "raw_size_sqm":       size,
                "raw_rooms":          rooms,
                "raw_bathrooms":      bathrooms,
                "raw_property_type":  self._property_type(title),
                "raw_lat":            None,
                "raw_lon":            None,
                "raw_municipality":   muni,
                "raw_district":       district,
                "raw_neighborhood":   hood,
            }
        except Exception as exc:
            logger.debug("[fotocasa] CSS card parse error: %s", exc, exc_info=True)
            return None

    # ── Shared field extractors ────────────────────────────────────────────────

    @staticmethod
    def _css_extract_price(tag: Tag | None) -> float | None:
        if not tag:
            return None
        raw = tag.get_text(" ", strip=True)
        # "350.000 €" or "1.250 €/mes" — Spanish "." = thousands separator
        m = re.search(r"([\d\.]+)", raw.replace(",", ""))
        if not m:
            return None
        try:
            return float(m.group(1).replace(".", ""))
        except ValueError:
            return None

    @staticmethod
    def _css_extract_size(texts: list[str]) -> float | None:
        for t in texts:
            m = re.search(r"(\d+(?:[,\.]\d+)?)\s*m[²2]", t, re.IGNORECASE)
            if m:
                return float(m.group(1).replace(",", "."))
        return None

    @staticmethod
    def _css_extract_rooms(texts: list[str]) -> int | None:
        for t in texts:
            m = re.search(r"(\d+)\s*(?:hab\.?|habitaci[oó]nes?|dormitorios?|dorm\.?)", t, re.IGNORECASE)
            if m:
                return int(m.group(1))
        return None

    @staticmethod
    def _css_extract_bathrooms(texts: list[str]) -> int | None:
        for t in texts:
            m = re.search(r"(\d+)\s*ba[ñn]os?", t, re.IGNORECASE)
            if m:
                return int(m.group(1))
        return None

    @staticmethod
    def _property_type(type_str: str) -> str:
        t = type_str.lower()
        if any(k in t for k in ["chalet", "villa", "casa", "house", "unifamiliar", "adosado"]):
            return "house"
        if any(k in t for k in ["ático", "atico", "penthouse", "duplex", "dúplex"]):
            return "penthouse"
        if any(k in t for k in ["estudio", "studio", "loft"]):
            return "studio"
        return "apartment"

    @staticmethod
    def _parse_location(loc_text: str, fallback: str) -> tuple[str, str | None, str | None]:
        parts = [p.strip().lower() for p in loc_text.split(",") if p.strip()]
        if not parts:
            return fallback, None, None
        if len(parts) == 1:
            return parts[0], None, None
        if len(parts) == 2:
            return parts[1], None, parts[0]
        return parts[-1], parts[1], parts[0]

    # ── Utilities ─────────────────────────────────────────────────────────────

    @staticmethod
    def _build_page_url(base_url: str, page: int) -> str:
        """Fotocasa paginates via ?page=N query parameter."""
        if page == 1:
            return base_url
        parsed = urlparse(base_url)
        params = parse_qs(parsed.query)
        params["page"] = [str(page)]
        new_query = urlencode({k: v[0] for k, v in params.items()})
        return urlunparse(parsed._replace(query=new_query))

    @staticmethod
    def _is_blocked(html: str) -> bool:
        signals = ["datadome", "captcha", "access denied", "acceso denegado",
                   "please enable js", "too many requests", "robot"]
        return any(s in html.lower() for s in signals)


