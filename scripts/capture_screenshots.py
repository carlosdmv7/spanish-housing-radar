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

# (url_path, output name, extra settle seconds for charts/tiles).
# home goes LAST: the first page load pays the cold MotherDuck connection
# (>10s), and a long settle there proved flaky — by the end the connection and
# query caches are warm and home renders instantly.
PAGES = [
    ("opportunities", "opportunities", 8),
    ("market", "market", 8),
    ("mortgage", "mortgage", 5),
    ("affordability", "affordability", 8),
    ("", "home", 12),
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

        # Deliberately simple: plain goto + fixed sleep, one session per page.
        # A fancier variant (warm-up visit + waiting on Streamlit's status
        # widget) kept crashing the server on the runner — rapid session churn
        # against the shared MotherDuck connection took the process down with
        # no traceback. Sequential single visits are what reliably works.
        for url_path, name, settle in PAGES:
            page.goto(f"{args.base_url}/{url_path}", wait_until="networkidle", timeout=90_000)
            time.sleep(settle)  # cover query time + plotly/pydeck painting
            page.screenshot(path=OUT_DIR / f"{name}.png")
            print(f"captured {name}.png", flush=True)
        browser.close()

    sys.exit(0)


if __name__ == "__main__":
    main()
