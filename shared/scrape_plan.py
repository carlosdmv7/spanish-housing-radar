"""
The scrape plan: what one scheduled run buys, target by target.

SCRAPE_TARGETS is a comma-separated list of target:operation:pages, e.g.

    horta-nord-camp-turia:sale:5,valencia:sale:1,valencia:rent:1

`target` is a city slug (valencia, madrid, …) or a zone key of
extraction.config.IDEALISTA_ZONES (a polygon search). It is meant to be a repo
variable, so the plan can be retuned without a code change.

Credit maths. Measured 2026-11-14: an Idealista search page through Scrapfly's
ASP now bills 30 credits (25 residential proxy + 5 browser), not the flat 25
ADR-0001 measured. The free tier is 1 000 credits a month.

    default plan = 5 + 1 + 1 = 7 pages ≈ 210 credits a run (175 at 25)
    4 Monday runs a month ≈ 840. A 5-Monday month would need 1 050, so its last
    run stops early at the quota — a clean stop, not a failure (ADR-0001).

Lives outside extraction/ because the flow reads it, and extraction.config
requires MotherDuck settings at import.
"""
from __future__ import annotations

from dataclasses import dataclass

CREDITS_PER_PAGE = 30
DEFAULT_SCRAPE_TARGETS = "horta-nord-camp-turia:sale:5,valencia:sale:1,valencia:rent:1"
OPERATIONS = ("sale", "rent")


@dataclass(frozen=True)
class ScrapeTarget:
    target: str
    operation: str
    pages: int

    @property
    def label(self) -> str:
        return f"{self.target}:{self.operation}"


def parse_scrape_targets(spec: str) -> list[ScrapeTarget]:
    """Parse SCRAPE_TARGETS; raise on anything malformed rather than guess."""
    out: list[ScrapeTarget] = []
    for item in (s.strip() for s in spec.split(",")):
        if not item:
            continue
        parts = [p.strip().lower() for p in item.split(":")]
        if len(parts) != 3 or not parts[0]:
            raise ValueError(f"Scrape target {item!r} is not target:operation:pages")
        target, operation, pages = parts
        if operation not in OPERATIONS:
            raise ValueError(f"Scrape target {item!r}: operation must be sale or rent")
        if not pages.isdigit() or int(pages) < 1:
            raise ValueError(f"Scrape target {item!r}: pages must be a positive integer")
        out.append(ScrapeTarget(target, operation, int(pages)))
    return out


def total_pages(targets: list[ScrapeTarget]) -> int:
    return sum(t.pages for t in targets)
