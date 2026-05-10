# extraction/scrapers/base.py
"""
AbstractScraper — every source portal inherits from this.
Guarantees a uniform interface so the loader doesn't care which portal
produced the data.
"""
from __future__ import annotations

import time
import logging
from abc import ABC, abstractmethod
from typing import Iterator

import requests
from tenacity import retry, stop_after_attempt, wait_exponential, before_sleep_log

from extraction.config import SCRAPER_DELAY_SECONDS, SCRAPER_MAX_RETRIES, SCRAPER_TIMEOUT_SECONDS
from extraction.schemas.raw_listings import RawListing

logger = logging.getLogger(__name__)

_DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "es-ES,es;q=0.9",
}


class AbstractScraper(ABC):
    """Base class for all real estate portal scrapers."""

    source_name: str  # must be set by subclass

    def __init__(self, province: str) -> None:
        self.province = province.lower().strip()
        self.session = requests.Session()
        self.session.headers.update(_DEFAULT_HEADERS)

    # ── Public interface ──────────────────────────────────────────────────────

    def scrape(self, operation: str = "sale") -> list[RawListing]:
        """
        Scrape all listings for the given province and operation type.
        Validates each row against RawListing before returning.
        """
        listings: list[RawListing] = []
        invalid_count = 0

        for raw_record in self._paginate(operation=operation):
            try:
                listing = RawListing(**raw_record)
                listings.append(listing)
            except Exception as exc:
                invalid_count += 1
                logger.warning("Skipping invalid record from %s: %s", self.source_name, exc)

        logger.info(
            "[%s] province=%s op=%s  valid=%d  skipped=%d",
            self.source_name, self.province, operation, len(listings), invalid_count,
        )
        return listings

    # ── Abstract — implement per portal ───────────────────────────────────────

    @abstractmethod
    def _paginate(self, operation: str) -> Iterator[dict]:
        """
        Yield raw dicts (one per listing) by iterating through portal pages.
        Must call self._polite_sleep() between page requests.
        """
        ...

    @abstractmethod
    def _parse_listing(self, raw: dict) -> dict:
        """Map a single portal response dict to the RawListing field names."""
        ...

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _polite_sleep(self) -> None:
        """Respect the configured delay between requests."""
        time.sleep(SCRAPER_DELAY_SECONDS)

    @retry(
        stop=stop_after_attempt(SCRAPER_MAX_RETRIES),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )
    def _get(self, url: str, **kwargs) -> requests.Response:
        """HTTP GET with automatic retry and timeout."""
        resp = self.session.get(url, timeout=SCRAPER_TIMEOUT_SECONDS, **kwargs)
        resp.raise_for_status()
        return resp

    @retry(
        stop=stop_after_attempt(SCRAPER_MAX_RETRIES),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )
    def _post(self, url: str, **kwargs) -> requests.Response:
        """HTTP POST with automatic retry and timeout."""
        resp = self.session.post(url, timeout=SCRAPER_TIMEOUT_SECONDS, **kwargs)
        resp.raise_for_status()
        return resp
