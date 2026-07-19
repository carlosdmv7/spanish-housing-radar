# scrpts/test_scrapfly_idealista.py
from __future__ import annotations

from pathlib import Path
import sys

# Ensure project root is on PYTHONPATH when running as a script
sys.path.insert(0, str(Path(__file__).parent.parent))

from scrapfly import ScrapeConfig, ScrapflyClient

from extraction.config import (
    SCRAPFLY_API_KEY,
    SCRAPFLY_ASP,
    SCRAPFLY_COUNTRY,
    SCRAPFLY_RENDER_JS,
)

URL = "https://www.idealista.com/venta-viviendas/madrid-madrid/"

if not SCRAPFLY_API_KEY:
    raise RuntimeError("SCRAPFLY_API_KEY is missing from .env")

client = ScrapflyClient(key=SCRAPFLY_API_KEY)

result = client.scrape(
    ScrapeConfig(
        url=URL,
        asp=SCRAPFLY_ASP,
        country=SCRAPFLY_COUNTRY,
        render_js=SCRAPFLY_RENDER_JS,
    )
)

html = result.content or ""

output_path = Path("data/debug/idealista_search_madrid_sale.html")
output_path.parent.mkdir(parents=True, exist_ok=True)
output_path.write_text(html, encoding="utf-8")

context = result.context or {}
cost_from_context = context.get("cost")

cost_from_header = result.headers.get("X-Scrapfly-Api-Cost")
remaining_credits = result.headers.get("X-Scrapfly-Remaining-Api-Credit")

print("Scrapfly request OK")
print(f"HTML length: {len(html)}")
print(f"Cost from context: {cost_from_context}")
print(f"Cost from header: {cost_from_header}")
print(f"Remaining credits: {remaining_credits}")
print(f"Saved: {output_path}")

if "Please enable JS" in html or "datadome" in html.lower():
    print("WARNING: Still received anti-bot page.")
elif "item-link" in html or "/inmueble/" in html:
    print("Looks like real Idealista HTML.")
else:
    print("HTML downloaded, but selectors may need inspection.")
