# extraction/config.py
"""
Centralised config — all settings read from environment variables.
Load .env automatically so plain `python run_extraction.py` just works.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root (two levels up from this file)
load_dotenv(Path(__file__).parent.parent / ".env")


# ── MotherDuck ────────────────────────────────────────────────────────────────
MOTHERDUCK_TOKEN: str = os.environ["MOTHERDUCK_TOKEN"]
MOTHERDUCK_DATABASE: str = os.getenv("MOTHERDUCK_DATABASE", "spanish_housing_radar")
MOTHERDUCK_DSN: str = f"md:{MOTHERDUCK_DATABASE}?motherduck_token={MOTHERDUCK_TOKEN}"

# ── Idealista API ─────────────────────────────────────────────────────────────
IDEALISTA_API_KEY: str = os.getenv("IDEALISTA_API_KEY", "")
IDEALISTA_API_SECRET: str = os.getenv("IDEALISTA_API_SECRET", "")
IDEALISTA_BASE_URL: str = "https://api.idealista.com/3.5/es"

# ── Scraping behaviour ────────────────────────────────────────────────────────
SCRAPER_DELAY_SECONDS: float = float(os.getenv("SCRAPER_DELAY_SECONDS", "2.0"))
SCRAPER_MAX_RETRIES: int = int(os.getenv("SCRAPER_MAX_RETRIES", "3"))
SCRAPER_TIMEOUT_SECONDS: int = int(os.getenv("SCRAPER_TIMEOUT_SECONDS", "15"))

# ── Spanish provinces available for extraction ────────────────────────────────
VALID_PROVINCES: list[str] = [
    "madrid", "barcelona", "valencia", "sevilla", "zaragoza",
    "malaga", "bilbao", "alicante", "valladolid", "palma",
]

# ── Target table names in MotherDuck (Bronze layer) ───────────────────────────
RAW_TABLE_MAP: dict[str, str] = {
    "idealista": "raw.idealista_listings",
    "fotocasa":  "raw.fotocasa_listings",
}
