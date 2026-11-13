"""
Idealista HTML scraper.

Strategy: search-card-only (no detail pages) → 1 Scrapfly credit per 30 listings.
All fields extracted from the <article class="item"> card on search result pages.

Selector reference (Idealista 2026):
  <article class="item">
    <a class="item-link" href="/inmueble/12345678/" title="Piso en venta en Malasaña, Madrid">
    <span class="item-price">350.000<span>€</span></span>
    <div class="item-detail-char">
      <span class="item-detail">3 hab.</span>
      <span class="item-detail">90 m²</span>
      <span class="item-detail">2 baños</span>
      <span class="item-detail">Planta 3ª exterior con ascensor</span>
    </div>
    <div class="item-description"><p class="ellipsis">free-text snippet</p></div>
    <div class="listing-tags-container"><span class="listing-tags">Lujo</span></div>
  </article>
In practice bathrooms never appear on the card (raw_bathrooms is null in every
row loaded so far); floor, lift, exterior/interior, garage, the portal's own
price-drop marker, the snippet and the tags do — see ADR-0012.
"""
from __future__ import annotations

from collections.abc import Iterator
import logging
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag

from extraction.config import (
    IDEALISTA_BASE_URL,
    IDEALISTA_MAX_LISTINGS,
    IDEALISTA_MAX_SEARCH_PAGES,
    IDEALISTA_SELECTORS,
    IDEALISTA_SORT,
    get_idealista_search_url,
)
from extraction.scrapers.base import AbstractScraper, CreditBudgetExhausted

logger = logging.getLogger(__name__)


# Search keys are ASCII slugs; Idealista titles, and so every municipality in
# the warehouse, carry the accents. Only the keys that differ are listed.
_MUNICIPALITY_BY_SEARCH_KEY: dict[str, str] = {
    "valencia": "valència",
    "malaga": "málaga",
}


class IdealistaScraper(AbstractScraper):
    source_name = "idealista"

    # ── AbstractScraper interface ─────────────────────────────────────────────

    def _paginate(self, operation: str = "sale") -> Iterator[dict]:
        search_url = get_idealista_search_url(self.province, operation)
        logger.info("[idealista] Starting: province=%s op=%s url=%s", self.province, operation, search_url)

        yielded = 0
        for page in range(1, IDEALISTA_MAX_SEARCH_PAGES + 1):
            page_url = self._build_page_url(search_url, page, IDEALISTA_SORT)
            logger.info("[idealista] Fetching page %d → %s", page, page_url)

            try:
                html = self._get_html(page_url)
            except CreditBudgetExhausted as exc:
                # A clean stop, not a failure: every listing already yielded is
                # valid and gets loaded. Draining a monthly quota mid-run and
                # discarding the work would be the worse outcome.
                logger.warning("[idealista] Stopping at page %d — %s", page, exc)
                break
            except Exception as exc:
                logger.warning("[idealista] Could not fetch page %d: %s", page, exc)
                break

            if self._is_blocked(html):
                logger.error(
                    "[idealista] Anti-bot page detected. Set SCRAPFLY_ENABLED=true in .env."
                )
                break

            cards = self._parse_search_page(html, operation)
            logger.info("[idealista] Page %d → %d valid cards", page, len(cards))

            if not cards:
                break

            for card in cards:
                yield card
                yielded += 1
                if yielded >= IDEALISTA_MAX_LISTINGS:
                    logger.info("[idealista] Hit IDEALISTA_MAX_LISTINGS=%d", IDEALISTA_MAX_LISTINGS)
                    return

            self._polite_sleep()

    def _parse_listing(self, raw: dict) -> dict:
        return raw  # search-card mode builds dicts directly

    # ── Page → cards ──────────────────────────────────────────────────────────

    def _parse_search_page(self, html: str, operation: str) -> list[dict]:
        soup = BeautifulSoup(html, "lxml")
        results = []
        for card in soup.select(IDEALISTA_SELECTORS["search_card"]):
            if card.select_one(".item-adv-label"):
                continue  # skip promoted ads
            parsed = self._parse_search_card(card, operation)
            if parsed:
                results.append(parsed)
        return results

    def _parse_search_card(self, card: Tag, operation: str) -> dict | None:
        try:
            link_tag = card.select_one(IDEALISTA_SELECTORS["search_link"])
            if not link_tag:
                return None

            href  = link_tag.get("href", "")
            url   = urljoin(IDEALISTA_BASE_URL, href)
            sid   = self._extract_id(url)
            title = link_tag.get("title", "")

            if not sid:
                return None

            price = self._extract_price(card)
            if price is None:
                return None

            details = [
                s.get_text(" ", strip=True)
                for s in card.select(IDEALISTA_SELECTORS["search_details"])
            ]

            size = self._extract_size(details)
            if size is None:
                return None

            # The fallback is the municipality as the warehouse spells it, not
            # the search key: a title that names no place would otherwise file
            # the flat under "valencia", a second city beside "valència".
            searched = _MUNICIPALITY_BY_SEARCH_KEY.get(self.province, self.province)
            muni, district, hood = self._parse_location(title, searched)

            return {
                "source_id":          sid,
                "source_name":        self.source_name,
                "raw_url":            url,
                "raw_price_eur":      price,
                "raw_operation_type": operation,
                "raw_size_sqm":       size,
                "raw_rooms":          self._extract_rooms(details),
                "raw_bathrooms":      self._extract_bathrooms(details),
                "raw_property_type":  self._property_type(title),
                "raw_lat":            None,
                "raw_lon":            None,
                "raw_municipality":   muni,
                "raw_district":       district,
                "raw_neighborhood":   hood,
                # The three fields above are what `_parse_location` made of this
                # string. Keeping the string itself is what lets a later parser
                # fix be applied to rows already in the warehouse.
                "raw_title":          title,
                # Card attributes as the advertiser states them (ADR-0012).
                # None always means "the card does not say", never "no".
                **self._extract_card_attributes(card, details),
            }
        except Exception as exc:
            logger.debug("[idealista] Card parse error: %s", exc, exc_info=True)
            return None

    # ── Field extractors ──────────────────────────────────────────────────────

    @staticmethod
    def _extract_price(card: Tag) -> float | None:
        """
        <span class="item-price">350.000<span>€</span></span>
        Clone → strip child spans → parse the number text.
        Spanish thousands separator is "." (no decimal part in prices).
        """
        tag = card.select_one(".item-price")
        if not tag:
            return None
        clone = BeautifulSoup(str(tag), "lxml").select_one(".item-price")
        for child in clone.find_all("span"):
            child.decompose()
        raw = clone.get_text(strip=True)
        m = re.search(r"([\d\.]+)", raw)
        if not m:
            return None
        return float(m.group(1).replace(".", ""))

    @staticmethod
    def _extract_size(details: list[str]) -> float | None:
        for t in details:
            m = re.search(r"(\d+(?:[,\.]\d+)?)\s*m[²2]", t, re.IGNORECASE)
            if m:
                return float(m.group(1).replace(",", "."))
        return None

    @staticmethod
    def _extract_rooms(details: list[str]) -> int | None:
        for t in details:
            m = re.search(r"(\d+)\s*(?:hab\.?|habitaci[oó]nes?|dormitorios?)", t, re.IGNORECASE)
            if m:
                return int(m.group(1))
        return None

    @staticmethod
    def _extract_bathrooms(details: list[str]) -> int | None:
        for t in details:
            m = re.search(r"(\d+)\s*ba[ñn]os?", t, re.IGNORECASE)
            if m:
                return int(m.group(1))
        return None

    # ── Card attributes (ADR-0012) ────────────────────────────────────────────
    # What explains most of the price difference between two flats in the same
    # barrio — floor, lift, exterior or interior, garage — is printed on the
    # search card and was being thrown away. Variants seen in the cached pages
    # (debug_output/, 30 Madrid sale cards):
    #   "Planta 3ª exterior con ascensor"   floor + orientation + lift, one span
    #   "Planta 7ª interior con ascensor"
    #   "Garaje incluido"                   its own span, first in the row
    #   "Garaje opc. 60.000 €"              optional: NOT included in the price
    #   (no floor span at all)              houses and chalets
    # The cached pages are one luxury Madrid search, so "Bajo", "Entreplanta",
    # "Sótano"/"Semi-sótano" and "sin ascensor" do not occur in them; they are
    # handled from Idealista's documented vocabulary and covered by unit tests.

    # Floor encoding: the storey number as an integer, ground = 0.
    #   Sótano / Semi-sótano → -1   (any below-ground level; raw_floor_text keeps
    #                                which one)
    #   Bajo                 →  0
    #   Entreplanta          →  0   (a mezzanine between bajo and 1ª: an integer
    #                                cannot hold 0.5, and economically it prices
    #                                with the ground floor, not the first)
    #   Planta Nª            →  N   (also "Planta -1", "Planta 12")
    #   no floor stated      →  None (houses, or an advertiser who left it blank)
    _FLOOR_SPAN = re.compile(
        r"^\s*(?:planta\s+-?\d+|bajo\b|entreplanta\b|semi-?\s?s[óo]tano\b|s[óo]tano\b)",
        re.IGNORECASE,
    )

    @classmethod
    def _floor_text(cls, details: list[str]) -> str | None:
        """The detail span that states the floor, verbatim, or None."""
        for t in details:
            if cls._FLOOR_SPAN.match(t):
                return t.strip()
        return None

    @staticmethod
    def _extract_floor(floor_text: str | None) -> int | None:
        """Encode a floor span as an integer storey (see the table above)."""
        if not floor_text:
            return None
        t = floor_text.strip().lower()
        m = re.match(r"planta\s+(-?\d+)", t)
        if m:
            return int(m.group(1))
        if re.match(r"(?:semi-?\s?)?s[óo]tano", t):
            return -1
        if t.startswith(("bajo", "entreplanta")):
            return 0
        return None

    @staticmethod
    def _extract_is_exterior(details: list[str]) -> bool | None:
        """True for "exterior", False for "interior", None when not stated."""
        for t in details:
            if re.search(r"\bexterior\b", t, re.IGNORECASE):
                return True
            if re.search(r"\binterior\b", t, re.IGNORECASE):
                return False
        return None

    @staticmethod
    def _extract_has_lift(details: list[str]) -> bool | None:
        """True for "con ascensor", False for "sin ascensor", None when unstated."""
        for t in details:
            if re.search(r"\bsin\s+ascensor\b", t, re.IGNORECASE):
                return False
            if re.search(r"\bcon\s+ascensor\b", t, re.IGNORECASE):
                return True
        return None

    _GARAGE_SPAN = re.compile(r"^\s*garaje\b", re.IGNORECASE)

    @classmethod
    def _extract_garage(cls, details: list[str]) -> tuple[str | None, str | None, float | None]:
        """
        (garage_text, garage, garage_price_eur) from the card.

        garage is 'included' ("Garaje incluido": in the asking price) or
        'optional' ("Garaje opc. 60.000 €" / "Garaje opcional": sold separately,
        NOT in the asking price, with its own price when stated). A card with no
        garage span says nothing about a garage, so all three are None — never a
        'no garage'.
        """
        for t in details:
            if not cls._GARAGE_SPAN.match(t):
                continue
            text = re.sub(r"\s+", " ", t).strip()
            low = text.lower()
            if "incluid" in low:
                return text, "included", None
            if re.search(r"\bopc(?:\.|ional)?", low):
                m = re.search(r"(\d{1,3}(?:\.\d{3})+|\d+)\s*€", text)
                price = float(m.group(1).replace(".", "")) if m else None
                return text, "optional", price
            return text, None, None
        return None, None, None

    @staticmethod
    def _extract_price_drop(card: Tag) -> tuple[float | None, float | None]:
        """
        (previous_price_eur, price_drop_pct) from the portal's own price-drop
        marker, as the portal states it:
          <span class="pricedown">
            <span class="pricedown_price">845.000 €</span>
            <span class="pricedown_icon icon-pricedown">3%</span>
          </span>
        The struck-through price is the previous asking price (845.000 against
        a current 820.000 on that card), the percentage is the cut. Both None
        when the card carries no marker.
        """
        prev = None
        pct = None
        price_tag = card.select_one('[class*="pricedown_price"], [class*="price-down_price"]')
        if price_tag:
            m = re.search(r"(\d{1,3}(?:\.\d{3})+|\d+)", price_tag.get_text(" ", strip=True))
            if m:
                prev = float(m.group(1).replace(".", ""))
        pct_tag = card.select_one('[class*="pricedown_icon"], [class*="price-down_icon"]')
        if pct_tag:
            m = re.search(r"(\d+(?:[,\.]\d+)?)\s*%", pct_tag.get_text(" ", strip=True))
            if m:
                pct = float(m.group(1).replace(",", "."))
        return prev, pct

    # The card snippet is already cut by Idealista at ~550 characters; the cap
    # only guards against a layout change dumping the full description here.
    _DESCRIPTION_MAX_CHARS = 1000

    @classmethod
    def _extract_description(cls, card: Tag) -> str | None:
        """Card description snippet, whitespace collapsed, capped at a word boundary."""
        tag = card.select_one(IDEALISTA_SELECTORS["search_desc"]) or card.select_one(".item-description")
        if not tag:
            return None
        text = re.sub(r"\s+", " ", tag.get_text(" ", strip=True)).strip()
        if not text:
            return None
        cap = cls._DESCRIPTION_MAX_CHARS
        if len(text) > cap:
            cut = text[:cap]
            text = (cut.rsplit(" ", 1)[0] if " " in cut else cut) + "…"
        return text

    @staticmethod
    def _extract_tags(card: Tag) -> str | None:
        """Listing tags ("Lujo", "Villa", "Apartamento"…) joined with '|', or None."""
        tags = [
            re.sub(r"\s+", " ", s.get_text(" ", strip=True)).replace("|", "/")
            for s in card.select(IDEALISTA_SELECTORS["search_tags"])
        ]
        tags = [t for t in tags if t]
        return "|".join(tags) if tags else None

    @classmethod
    def _extract_card_attributes(cls, card: Tag, details: list[str]) -> dict:
        floor_text = cls._floor_text(details)
        garage_text, garage, garage_price = cls._extract_garage(details)
        prev_price, drop_pct = cls._extract_price_drop(card)
        return {
            "raw_floor":              cls._extract_floor(floor_text),
            "raw_floor_text":         floor_text,
            "raw_is_exterior":        cls._extract_is_exterior(details),
            "raw_has_lift":           cls._extract_has_lift(details),
            "raw_garage":             garage,
            "raw_garage_price_eur":   garage_price,
            "raw_garage_text":        garage_text,
            "raw_previous_price_eur": prev_price,
            "raw_price_drop_pct":     drop_pct,
            "raw_description":        cls._extract_description(card),
            "raw_tags":               cls._extract_tags(card),
        }

    @staticmethod
    def _property_type(title: str) -> str:
        t = title.lower()
        if any(k in t for k in ["chalet", "villa", "casa", "unifamiliar"]):
            return "house"
        if any(k in t for k in ["ático", "atico", "penthouse", "dúplex", "duplex"]):
            return "penthouse"
        if any(k in t for k in ["estudio", "studio", "loft"]):
            return "studio"
        return "apartment"

    # Every way Idealista titles name a *street* rather than an area. The list is
    # long because it was short: the first version missed `gran vía`, `carretera`,
    # `passatge`, `pasaje`, `rambla` and the `cl`/`ctra` abbreviations, and every
    # omission put a street name in the neighbourhood column of the warehouse —
    # where it became a benchmark grouping key indistinguishable from a real
    # barrio. Catalan and Valencian forms are here because half the coverage is
    # València and Barcelona.
    _STREET_KEYWORDS = re.compile(
        r"\b("
        r"calle|c/|cl|carrer|"
        r"avenida|avinguda|avda?\.?|av\.?|"
        r"paseo|passeig|pº|"
        r"plaza|pla[çc]a|pza\.?|pl\.?|"
        r"gran\s+v[íi]a|"
        r"carretera|ctra\.?|"
        r"passatge|pasaje|"
        r"rambla|"
        r"ronda|glorieta|traves[ií]a|travessera|"
        r"camino|cam[íi]|"
        r"callej[óo]n|cuesta|bajada|subida|costanilla|corredera|"
        r"bulevar|boulevard|"
        r"muelle|moll|"
        r"poligono|pol[íi]gono"
        r")\b",
        re.IGNORECASE,
    )

    # Property-type words Idealista puts in front of the location, e.g.
    # "Chalet adosado en Russafa". The original code stripped a single word
    # before " en ", so one-word types worked and "chalet adosado en …" survived
    # whole — which is why the warehouse holds a barrio literally called
    # "chalet adosado en russafa".
    _TYPE_PREFIX = re.compile(
        r"^(?:piso|pisos|apartamento|casa|casas|chalet|adosado|pareado|"
        r"unifamiliar|villa|finca|[áa]tico|d[úu]plex|estudio|studio|loft|"
        r"penthouse|bajo|planta|inmueble|vivienda|obra\s+nueva)\b",
        re.IGNORECASE,
    )

    # A bare house number: "34", "7 -5", "5 nb", "12 bis". Deliberately capped at
    # three trailing characters so a genuine barrio such as Madrid's
    # "12 de Octubre" is not mistaken for a portal number.
    _HOUSE_NUMBER = re.compile(r"^\d+\s*[-–]?\s*\w{0,3}$")

    @classmethod
    def _parse_location(cls, title: str, fallback: str) -> tuple[str, str | None, str | None]:
        """
        Idealista title templates vary, and street-style titles leak into the
        location chain in two different ways:
          "Piso en venta en Barrio Salamanca, Madrid"
            → neighbourhood-titled, regex below captures the location cleanly
          "Piso en alquiler en calle dels Vivons, Russafa, Valencia"
            → regex matches "en alquiler en" but the captured group still starts
              with the street, not the real neighbourhood
          "Piso en calle de Alcalá, Goya, Madrid"
            → no "venta/alquiler en" at all, so nothing gets stripped
          "Piso en calle de los Vivons, 34, Russafa, Valencia"
            → same, plus a bare house-number segment
        In every street-titled case, leading comma-segments that are a street
        name or a house number aren't real locations and must be dropped before
        the municipality/district/neighbourhood split — otherwise the street
        gets misread as the neighbourhood and pushes the real one to district.
        """
        m = re.search(r"\ben\s+(?:venta|alquiler)\s+en\s+(.+)$", title, re.IGNORECASE)
        loc = m.group(1).strip() if m else title
        parts = [p.strip().lower() for p in loc.split(",") if p.strip()]

        if parts and cls._TYPE_PREFIX.match(parts[0]):
            # Strip the property-type words up to the first " en ", however many
            # there are: "chalet adosado en russafa" → "russafa". Gated on a known
            # type word so a real barrio is never truncated at an inner " en ".
            # `(?:\s+|$)` so a truncated title ("Piso en", nothing after it) strips
            # to empty instead of surviving as the "municipality" "piso en".
            parts[0] = re.sub(r"^.*?\ben(?:\s+|$)", "", parts[0], count=1).strip()
            if not parts[0]:
                parts.pop(0)

        # At most ONE leading street segment is dropped, not every segment that
        # looks street-like. Idealista puts the street first and the area second,
        # so a loop that keeps popping eats the answer: València has a barrio
        # literally called "Gran Vía", and
        #   "Piso en Gran Via del Marqués del Túria, Gran Vía, València"
        # lost both segments and returned no neighbourhood at all. One pop takes
        # the street and leaves the barrio, which is the actual shape of the data.
        if parts and cls._STREET_KEYWORDS.search(parts[0]):
            parts.pop(0)

        # A house number can also sit between the street and the barrio
        # ("calle de Sueca, 34, Russafa"), and a trailing one before the city.
        # Dropping them anywhere is safe: a portal number is never an area.
        parts = [p for p in parts if not cls._HOUSE_NUMBER.match(p)]

        # A municipality that is still a property-type phrase ("piso en", "casa en
        # calle mayor") is the title talking about the flat, not a place. Price and
        # size on the card are valid, so keep the listing under the city that was
        # searched -- and say nothing finer, since the pieces we dropped are
        # exactly the ones we cannot trust.
        if parts and cls._TYPE_PREFIX.match(parts[-1]):
            return fallback, None, None

        if not parts:
            return fallback, None, None
        if len(parts) == 1:
            return parts[0], None, None
        if len(parts) == 2:
            return parts[1], None, parts[0]
        return parts[-1], parts[1], parts[0]

    @staticmethod
    def _extract_id(url: str) -> str | None:
        m = re.search(r"/inmueble/(\d+)/", url)
        return m.group(1) if m else None

    @staticmethod
    def _build_page_url(base: str, page: int, sort: str = "") -> str:
        url = base if page == 1 else base.rstrip("/") + f"/pagina-{page}.htm"
        # The same query string Idealista's own sort menu links to.
        return f"{url}?ordenado-por={sort}" if sort else url

    @staticmethod
    def _is_blocked(html: str) -> bool:
        """
        Detect a genuine Idealista block page.

        Do NOT check for "captcha" or "datadome" — Idealista embeds DataDome
        JS on every page including successful ones (confirmed via debug_scrapfly.py).
        Only flag when hard block signals appear AND listings are absent.
        """
        h = html.lower()

        # These strings only appear on real interstitial/block pages
        hard_blocks = [
            "please enable js and disable any ad blocker",
            "acceso denegado",
            "429 too many requests",
        ]
        if any(s in h for s in hard_blocks):
            return True

        # Short response with no article tags = wall page, not listings
        return len(html) < 5_000 and "<article" not in h
