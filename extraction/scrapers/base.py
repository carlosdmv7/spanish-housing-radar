"""
AbstractScraper — every source portal inherits from this.

Key addition vs previous version: _get_html() dispatches to either
plain requests or Scrapfly, controlled by SCRAPFLY_ENABLED in .env.
All subclasses get this for free without any extra code.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator
import logging
import os
import time

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

logger_cost = logging.getLogger(__name__)

# Hard ceiling on credits one process may spend, from SCRAPFLY_CREDIT_BUDGET.
# 0 disables it. This exists because Scrapfly bills per request and a paginated
# run can empty a monthly quota in minutes with no warning: the first deep run
# of this scraper cost ~25 credits a page against an ADR that claimed ~1.
SCRAPFLY_CREDIT_BUDGET: int = int(os.getenv("SCRAPFLY_CREDIT_BUDGET", "0"))


class CreditBudgetExhausted(RuntimeError):
    """Raised when a run reaches SCRAPFLY_CREDIT_BUDGET, so it stops rather than
    silently draining the quota. Callers treat it as a clean stop, not a crash:
    everything scraped before it is already valid and worth loading."""


def _extract_cost(result) -> int | None:
    """
    Credits this scrape cost, or None if the SDK did not say.

    None must never be coerced to 0 — an unknown cost that reads as free is how
    a budget guard silently stops guarding.
    """
    for probe in (
        lambda: result.scrape_result["cost"]["total"],
        lambda: result.scrape_result["cost"],
        lambda: result.context["cost"]["total"],
        lambda: result.context["cost"],
    ):
        try:
            value = probe()
        except (KeyError, TypeError, AttributeError):
            continue
        if isinstance(value, int | float):
            return int(value)
    return None

logger = logging.getLogger(__name__)


class AbstractScraper(ABC):
    """Base class for all real estate portal scrapers."""

    source_name: str  # must be set by every subclass

    def __init__(self, province: str) -> None:
        self.province = province.lower().strip()
        # Reuse a single requests.Session for connection pooling + shared headers
        self.session = requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)
        # Credits this scraper instance has spent, for the budget guard below.
        self._credits_spent = 0

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
            from scrapfly import ScrapeConfig, ScrapflyClient  # type: ignore[import]
        except ImportError as exc:
            raise RuntimeError(
                "scrapfly-sdk is not installed.\n"
                "Run: pip install scrapfly-sdk\n"
                "Or set SCRAPFLY_ENABLED=false in .env to use plain requests."
            ) from exc

        client = ScrapflyClient(key=SCRAPFLY_API_KEY)
        result = client.scrape(
            ScrapeConfig(
                url=url,
                asp=SCRAPFLY_ASP,
                country=SCRAPFLY_COUNTRY,
                render_js=SCRAPFLY_RENDER_JS,
            )
        )

        # Credit accounting. This used to read keys that are not in the payload,
        # so every line logged "cost=? remaining=?" and the real price of a scrape
        # was invisible -- which is how ADR-0001's "~1 credit per search card"
        # went unchallenged while Idealista, behind ASP, actually costs ~25.
        # Several shapes are tried because the SDK has moved this field around
        # between versions, and an unparsed cost must read as unknown, never 0.
        cost = _extract_cost(result)
        self._credits_spent += cost or 0
        logger.info(
            "[scrapfly] url=%s  cost=%s credits  spent this run=%d",
            url, cost if cost is not None else "unknown", self._credits_spent,
        )

        if SCRAPFLY_CREDIT_BUDGET and self._credits_spent >= SCRAPFLY_CREDIT_BUDGET:
            raise CreditBudgetExhausted(
                f"Spent {self._credits_spent} credits, at or over the "
                f"SCRAPFLY_CREDIT_BUDGET of {SCRAPFLY_CREDIT_BUDGET}. "
                "Raise the budget to continue."
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
