"""
AbstractScraper — every source portal inherits from this.

Key addition vs previous version: _get_html() dispatches to either
plain requests or Scrapfly, controlled by SCRAPFLY_ENABLED in .env.
All subclasses get this for free without any extra code.
"""
from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from typing import Iterator

import requests
from tenacity import before_sleep_log, retry, stop_after_attempt, wait_exponential

from extraction.config import (
    DEFAULT_HEADERS,
    SCRAPER_DELAY_SECONDS,
    SCRAPER_MAX_RETRIES,
    SCRAPER_TIMEOUT_SECONDS,
    SCRAPFLY_API_KEY,
    SCRAPFLY_ASP,
    SCRAPFLY_COUNTRY,
    SCRAPFLY_ENABLED,
    SCRAPFLY_RENDER_JS,
)
from extraction.schemas.raw_listings import RawListing

logger = logging.getLogger(__name__)


class AbstractScraper(ABC):
    """Base class for all real estate portal scrapers."""

    source_name: str  # must be set by every subclass

    def __init__(self, province: str) -> None:
        self.province = province.lower().strip()
        # Reuse a single requests.Session for connection pooling + shared headers
        self.session = requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)

    # ── Public interface ──────────────────────────────────────────────────────

    def scrape(self, operation: str = "sale") -> list[RawListing]:
        """
        Main entry point.  Calls _paginate(), validates each raw dict
        against RawListing (Pydantic), and returns only valid rows.
        """
        listings: list[RawListing] = []
        invalid_count = 0

        for raw_record in self._paginate(operation=operation):
            try:
                listing = RawListing(**raw_record)
                listings.append(listing)
            except Exception as exc:
                invalid_count += 1
                logger.warning(
                    "Skipping invalid record from %s: %s | data=%s",
                    self.source_name,
                    exc,
                    raw_record,
                )

        logger.info(
            "[%s] province=%s op=%s  valid=%d  skipped=%d",
            self.source_name,
            self.province,
            operation,
            len(listings),
            invalid_count,
        )
        return listings

    # ── Abstract — implement per portal ───────────────────────────────────────

    @abstractmethod
    def _paginate(self, operation: str) -> Iterator[dict]:
        """
        Yield one raw dict per listing.
        Dict keys must match RawListing field names exactly.
        Must call self._polite_sleep() between page requests.
        """
        ...

    @abstractmethod
    def _parse_listing(self, raw: dict) -> dict:
        """Map a single source record to RawListing field names."""
        ...

    # ── HTTP helpers ──────────────────────────────────────────────────────────

    def _get_html(self, url: str) -> str:
        """
        Fetch a URL and return the response HTML as a string.

        Dispatches to Scrapfly when SCRAPFLY_ENABLED=true in .env,
        otherwise falls back to plain requests.

        Scrapfly handles:
          - Rotating residential proxies (country=ES)
          - Anti-bot bypass (asp=True)
          - Optional JS rendering (render_js=True for SPAs)

        To save credits during development:
          SCRAPFLY_ENABLED=false   → plain requests (often blocked by Idealista)
          IDEALISTA_MAX_SEARCH_PAGES=1  → only one page per run
        """
        if SCRAPFLY_ENABLED and SCRAPFLY_API_KEY:
            return self._scrapfly_get(url)
        return self._requests_get(url).text

    def _scrapfly_get(self, url: str) -> str:
        """Fetch via Scrapfly anti-bot API. Requires scrapfly-sdk installed."""
        try:
            from scrapfly import ScrapflyClient, ScrapeConfig  # type: ignore[import]
        except ImportError:
            raise RuntimeError(
                "scrapfly-sdk is not installed.\n"
                "Run: pip install scrapfly-sdk\n"
                "Or set SCRAPFLY_ENABLED=false in .env to use plain requests."
            )

        client = ScrapflyClient(key=SCRAPFLY_API_KEY)
        result = client.scrape(
            ScrapeConfig(
                url=url,
                asp=SCRAPFLY_ASP,
                country=SCRAPFLY_COUNTRY,
                render_js=SCRAPFLY_RENDER_JS,
            )
        )

        # Log credit usage so you can track your budget
        cost = result.scrape_result.get("cost", "?")
        remaining = result.scrape_result.get("remaining_api_calls", "?")
        logger.info(
            "[scrapfly] url=%s  cost=%s credits  remaining=%s",
            url, cost, remaining,
        )

        return result.content

    @retry(
        stop=stop_after_attempt(SCRAPER_MAX_RETRIES),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )
    def _requests_get(self, url: str, **kwargs) -> requests.Response:
        """Plain requests GET with retry + timeout."""
        resp = self.session.get(url, timeout=SCRAPER_TIMEOUT_SECONDS, **kwargs)
        if not resp.ok:
            logger.error(
                "GET failed url=%s status=%s snippet=%s",
                url, resp.status_code, resp.text[:300],
            )
        resp.raise_for_status()
        return resp

    # Keep _get() as an alias so any subclass code using self._get() still works
    def _get(self, url: str, **kwargs) -> requests.Response:
        return self._requests_get(url, **kwargs)

    @retry(
        stop=stop_after_attempt(SCRAPER_MAX_RETRIES),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )
    def _post(self, url: str, **kwargs) -> requests.Response:
        """Plain requests POST with retry + timeout."""
        resp = self.session.post(url, timeout=SCRAPER_TIMEOUT_SECONDS, **kwargs)
        if not resp.ok:
            logger.error(
                "POST failed url=%s status=%s snippet=%s",
                url, resp.status_code, resp.text[:300],
            )
        resp.raise_for_status()
        return resp

    def _polite_sleep(self) -> None:
        """Respect the configured delay between page requests."""
        time.sleep(SCRAPER_DELAY_SECONDS)
