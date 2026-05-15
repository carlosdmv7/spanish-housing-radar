from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import urljoin

import pandas as pd
from bs4 import BeautifulSoup

# Ensure project root is on PYTHONPATH
sys.path.insert(0, str(Path(__file__).parent.parent))

from extraction.config import IDEALISTA_BASE_URL, IDEALISTA_SELECTORS


HTML_PATH = Path("data/debug/idealista_search_madrid_sale.html")


def clean_price(text: str) -> float | None:
    match = re.search(r"([\d\.,]+)", text)

    if not match:
        return None

    return float(match.group(1).replace(".", "").replace(",", "."))


def extract_source_id(url: str) -> str | None:
    match = re.search(r"/inmueble/(\d+)/", url)

    if not match:
        return None

    return match.group(1)


def extract_size(details: list[str]) -> float | None:
    for text in details:
        normalized = text.lower().replace(".", "")
        match = re.search(r"(\d+(?:,\d+)?)\s*m²", normalized)

        if match:
            return float(match.group(1).replace(",", "."))

    return None


def extract_rooms(details: list[str]) -> int | None:
    for text in details:
        normalized = text.lower()
        match = re.search(r"(\d+)\s*(hab|habitaciones|dormitorios)", normalized)

        if match:
            return int(match.group(1))

    return None


def extract_bathrooms(details: list[str]) -> int | None:
    for text in details:
        normalized = text.lower()
        match = re.search(r"(\d+)\s*(baño|baños)", normalized)

        if match:
            return int(match.group(1))

    return None


def main() -> None:
    if not HTML_PATH.exists():
        raise FileNotFoundError(f"Missing cached HTML: {HTML_PATH}")

    html = HTML_PATH.read_text(encoding="utf-8")
    soup = BeautifulSoup(html, "lxml")

    cards = soup.select(IDEALISTA_SELECTORS["search_card"])
    print(f"Cards found: {len(cards)}")

    rows = []

    for card in cards:
        link_node = card.select_one(IDEALISTA_SELECTORS["search_link"])

        if not link_node:
            continue

        href = link_node.get("href")

        if not href:
            continue

        url = urljoin(IDEALISTA_BASE_URL, href)

        if "/inmueble/" not in url:
            continue

        source_id = extract_source_id(url)

        price_node = card.select_one(IDEALISTA_SELECTORS["search_price"])
        price = clean_price(price_node.get_text(" ", strip=True)) if price_node else None

        detail_nodes = card.select(IDEALISTA_SELECTORS["search_details"])
        details = [node.get_text(" ", strip=True) for node in detail_nodes]

        title = link_node.get_text(" ", strip=True)

        rows.append(
            {
                "source_id": source_id,
                "raw_url": url,
                "title": title,
                "price": price,
                "size_sqm": extract_size(details),
                "rooms": extract_rooms(details),
                "bathrooms": extract_bathrooms(details),
                "details": " | ".join(details),
            }
        )

    df = pd.DataFrame(rows)

    print(df.head(20).to_string(index=False))
    print()
    print(df.isna().sum())

    output_path = Path("data/debug/parsed_idealista_search_madrid_sale.csv")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False)

    print(f"\nSaved parsed CSV: {output_path}")


if __name__ == "__main__":
    main()