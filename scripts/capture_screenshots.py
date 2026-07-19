"""
Capture README screenshots of the running Streamlit app with Playwright.

Usage (the app must already be running):
    streamlit run app/main.py --server.headless true &
    python scripts/capture_screenshots.py [--base-url http://localhost:8501]

Writes PNGs to docs/img/. Run via the "Capture screenshots" GitHub Actions
workflow, which has the browser system deps the local WSL setup lacks.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys
import time
import urllib.request

from playwright.sync_api import sync_playwright

OUT_DIR = Path(__file__).resolve().parents[1] / "docs" / "img"

# (url_path, output name, extra settle seconds for charts/tiles)
PAGES = [
    ("", "home", 3),
    ("opportunities", "opportunities", 6),
    ("market", "market", 6),
    ("mortgage", "mortgage", 4),
    ("affordability", "affordability", 6),
]


def wait_for_app(base_url: str, timeout_s: int = 120) -> None:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"{base_url}/_stcore/health", timeout=5) as r:
                if r.status == 200:
                    return
        except Exception:
            time.sleep(2)
    raise SystemExit(f"App at {base_url} not healthy after {timeout_s}s")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost:8501")
    args = parser.parse_args()

    wait_for_app(args.base_url)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=1.5)

        def goto_and_settle(url: str, settle: int) -> None:
            page.goto(url, wait_until="networkidle", timeout=90_000)
            # Streamlit shows a status widget ("RUNNING…") while the script
            # executes; wait for it to detach so we never shoot a half-loaded
            # page (the first MotherDuck query can take >10s cold).
            try:
                page.wait_for_selector(
                    '[data-testid="stStatusWidget"]', state="detached", timeout=90_000
                )
            except Exception:
                pass  # widget may never have appeared on an instant page
            time.sleep(settle)  # let plotly/pydeck finish painting

        # Warm-up: first load opens the MotherDuck connection (slow, cold);
        # every capture after this hits the cached connection + cached queries.
        goto_and_settle(args.base_url, 2)

        for url_path, name, settle in PAGES:
            goto_and_settle(f"{args.base_url}/{url_path}", settle)
            page.screenshot(path=OUT_DIR / f"{name}.png")
            print(f"captured {name}.png")
        browser.close()

    sys.exit(0)


if __name__ == "__main__":
    main()
