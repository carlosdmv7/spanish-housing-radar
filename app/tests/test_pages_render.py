"""
Headless render check for every page.

This exists because a green unit-test suite already let a crash reach production
once: `MAX(_loaded_at::date)` arrives from DuckDB as a pandas Timestamp, so
`date.today() - last_run` raised, and the home page rendered "Can't reach the
warehouse" for a connection that was perfectly healthy.

Two things that check has to get right:

`at.exception` alone is not enough. Every view catches query failures and renders
a friendly `st.error`, so a genuinely broken page finishes its script run and
reports clean.

`at.error` alone over-reports. `st.error` is also a legitimate product widget —
the mortgage page uses it to say "you are €4,700 short of signing day", which is
the answer working, not the app breaking. So error text is matched against the
vocabulary of a *diagnostic* rather than a verdict.

Needs a live MotherDuck token and is skipped without one, which keeps the suite
runnable offline while still gating CI, where the token is a secret.
"""
from __future__ import annotations

import os
from pathlib import Path
import re

from dotenv import load_dotenv
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

# The app reads the token through `load_dotenv()` in connection.py, so a developer
# with a working `.env` has never had to export it. Loading it here too means the
# check runs for them by default instead of silently skipping — a test that skips
# on the machine where it matters most is not a test.
load_dotenv(REPO_ROOT / ".env")

PAGES = [
    "app/views/home.py",
    "app/views/01_opportunities.py",
    "app/views/02_market.py",
    "app/views/03_mortgage.py",
    "app/views/04_affordability.py",
    "app/views/05_how_it_works.py",
]

# Wording that only ever appears when something is broken, never in a verdict.
BROKEN = re.compile(
    r"can'?t reach|could not|failed|exception|traceback|unavailable|"
    r"not been built|no such|error:",
    re.IGNORECASE,
)

# CI hands the other app tests a placeholder token, because extraction/config.py
# demands *something* at import time. Treating that placeholder as a real
# credential would turn this check red on every fork PR for a reason that has
# nothing to do with the code under review.
_PLACEHOLDER_TOKENS = {"", "unused-in-ci"}

pytestmark = pytest.mark.skipif(
    os.getenv("MOTHERDUCK_TOKEN", "") in _PLACEHOLDER_TOKENS,
    reason="needs a live warehouse; set a real MOTHERDUCK_TOKEN to run",
)


@pytest.mark.parametrize("page", PAGES)
def test_page_renders_without_diagnostics(page: str) -> None:
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(REPO_ROOT / page), default_timeout=180).run()

    assert not at.exception, [e.value for e in at.exception]

    diagnostics = [e.value for e in at.error if BROKEN.search(e.value)]
    assert not diagnostics, diagnostics


def test_every_view_is_covered() -> None:
    """A new page must be added to PAGES, or it ships unchecked."""
    on_disk = {
        f"app/views/{p.name}"
        for p in (REPO_ROOT / "app" / "views").glob("*.py")
        if not p.name.startswith("_")
    }
    assert on_disk == set(PAGES), on_disk.symmetric_difference(PAGES)
