"""
Scrapfly diagnostic script — run this to see exactly what's coming back.

Usage:
    python extraction/debug_scrapfly.py

Saves the raw HTML to debug_output/scrapfly_response.html
so you can open it in a browser and see what Scrapfly actually returned.
"""
from __future__ import annotations

import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
from dotenv import load_dotenv

load_dotenv()

from scrapfly import ScrapeConfig, ScrapflyClient  # type: ignore  # noqa: E402

API_KEY = os.environ.get("SCRAPFLY_API_KEY", "")
URL     = "https://www.idealista.com/venta-viviendas/madrid-madrid/"
OUT_DIR = Path("debug_output")
OUT_DIR.mkdir(exist_ok=True)

def main() -> None:
    print(f"\n{'='*60}")
    print(f"Scrapfly debug — {URL}")
    print(f"{'='*60}\n")

    # ── 1. Account check (0 credits) ─────────────────────────────────────────
    client = ScrapflyClient(key=API_KEY)
    try:
        account = client.account()
        print("✓ Account OK")
        print(f"  Plan       : {account.get('subscription', {}).get('plan_name', '?')}")
        print(f"  Credits    : {account.get('subscription', {}).get('usage', {})}")
    except Exception as e:
        print(f"✗ Account check failed: {e}")
        print("  → Check your SCRAPFLY_API_KEY in .env")
        sys.exit(1)

    # ── 2. Minimal scrape — no ASP, no JS (cheapest, 1 credit) ───────────────
    print("\n[Test 1] Plain scrape (asp=False, render_js=False) — 1 credit")
    _scrape_and_save(client, URL, asp=False, render_js=False, tag="plain")

    # ── 3. ASP only, no JS (still 1 credit, bypasses basic blocks) ───────────
    print("\n[Test 2] ASP only (asp=True, render_js=False) — 1 credit")
    _scrape_and_save(client, URL, asp=True, render_js=False, tag="asp_only")

    # ── 4. Full: ASP + JS (5 credits, needed for DataDome JS challenge) ──────
    print("\n[Test 3] Full bypass (asp=True, render_js=True) — ~5 credits")
    _scrape_and_save(client, URL, asp=True, render_js=True, tag="full")

    print("\n✓ Done — open files in debug_output/ to inspect the HTML")


def _scrape_and_save(
    client: ScrapflyClient,
    url: str,
    asp: bool,
    render_js: bool,
    tag: str,
) -> None:
    try:
        result = client.scrape(ScrapeConfig(
            url=url,
            asp=asp,
            country="ES",
            render_js=render_js,
        ))
    except Exception as e:
        print(f"  ✗ Scrape failed: {e}")
        return

    # ── Inspect result object ─────────────────────────────────────────────────
    meta = result.scrape_result or {}
    print(f"  Status code : {result.status_code}")
    print(f"  Content len : {len(result.content):,} chars")
    print(f"  meta keys   : {list(meta.keys())}")

    # Try every possible credit-cost key name across SDK versions
    for key in ("cost", "credits_used", "credit_cost", "api_call_cost"):
        if key in meta:
            print(f"  Cost key    : {key!r} = {meta[key]}")

    # ── Block detection ───────────────────────────────────────────────────────
    html = result.content.lower()
    signals = {
        "datadome":       "datadome"    in html,
        "js_challenge":   "dd={'rt'"    in html or "please enable js" in html,
        "captcha":        "captcha"     in html,
        "article.item":   "article"     in html and "item-link" in html,  # real listings
        "item-price":     "item-price"  in html,
    }
    for signal, found in signals.items():
        icon = "✓" if (signal in ("article.item", "item-price") and found) else ("✗" if found and signal not in ("article.item", "item-price") else " ")
        print(f"  {icon} {signal:<20} {'FOUND' if found else 'not found'}")

    # ── Save HTML ─────────────────────────────────────────────────────────────
    out_file = OUT_DIR / f"scrapfly_{tag}.html"
    out_file.write_text(result.content, encoding="utf-8")
    print(f"  → Saved to {out_file}  (open in browser to inspect)")

    # ── First 500 chars of body for quick triage ──────────────────────────────
    body_start = result.content[:600].replace("\n", " ").strip()
    print(f"  Preview     : {body_start[:300]!r}")


if __name__ == "__main__":
    main()
