"""Unit tests for IdealistaScraper's pure parsing helpers — no network involved."""
import pytest

from extraction.scrapers.idealista import IdealistaScraper

scraper = IdealistaScraper(province="madrid")


class TestParseLocation:
    def test_neighborhood_titled(self):
        muni, district, hood = scraper._parse_location(
            "Piso en venta en Barrio Salamanca, Madrid", fallback="madrid"
        )
        assert muni == "madrid"
        assert hood == "barrio salamanca"
        assert district is None

    def test_street_titled_drops_street_segment(self):
        muni, district, hood = scraper._parse_location(
            "Piso en alquiler en calle dels Vivons, Russafa, Valencia", fallback="valencia"
        )
        assert muni == "valencia"
        assert hood == "russafa"
        assert district is None

    def test_street_titled_no_operation_prefix(self):
        muni, district, hood = scraper._parse_location(
            "Piso en calle de Alcalá, Goya, Madrid", fallback="madrid"
        )
        assert muni == "madrid"
        assert hood == "goya"

    def test_street_with_house_number_segment(self):
        muni, district, hood = scraper._parse_location(
            "Piso en calle de los Vivons, 34, Russafa, Valencia", fallback="valencia"
        )
        assert muni == "valencia"
        assert hood == "russafa"

    def test_district_and_neighborhood_present(self):
        muni, district, hood = scraper._parse_location(
            "Piso en venta en Malasaña, Centro, Madrid", fallback="madrid"
        )
        assert muni == "madrid"
        assert district == "centro"
        assert hood == "malasaña"

    def test_no_location_info_falls_back(self):
        muni, district, hood = scraper._parse_location("Piso en calle Mayor", fallback="madrid")
        assert muni == "madrid"
        assert district is None
        assert hood is None


class TestTruncatedTitles:
    """A title with no location must not mint a municipality called "piso en"."""

    @pytest.mark.parametrize("title", ["Piso en", "piso en", "Piso en ", "Casa en", "Chalet adosado en"])
    def test_type_only_title_falls_back_to_searched_city(self, title):
        assert scraper._parse_location(title, fallback="valencia") == ("valencia", None, None)

    def test_empty_title_falls_back(self):
        assert scraper._parse_location("", fallback="valencia") == ("valencia", None, None)

    def test_type_phrase_as_last_segment_is_not_a_municipality(self):
        # Neighbourhood must not survive either: the finer parts are untrusted.
        muni, district, hood = scraper._parse_location("Russafa, Piso en", fallback="valencia")
        assert (muni, district, hood) == ("valencia", None, None)

    def test_real_titles_unaffected(self):
        assert scraper._parse_location("Piso en Russafa, València", fallback="valencia") == (
            "valència", None, "russafa")


class TestParseLocationProductionRegressions:
    """
    Every case here is a real title reconstructed from a value this parser
    actually wrote into the warehouse. Before the fix, 8 of 12 sampled titles
    produced a street name, a house number or a property type in the
    `neighborhood` column -- where the scoring model then used it as a benchmark
    grouping key indistinguishable from a real barrio.
    """

    @pytest.mark.parametrize("title,expected_hood", [
        # Street types the original keyword list missed entirely.
        ("Piso en gran vía de Ramón y Cajal, La Roqueta, Valencia", "la roqueta"),
        ("Piso en passatge de Ripalda, Sant Francesc, Valencia", "sant francesc"),
        ("Ático en rambla de Catalunya, Eixample, Barcelona", "eixample"),
        ("Piso en CL Lasala, Manuel, Zaragoza", "manuel"),
        ("Piso en avinguda del Port, Aiora, Valencia", "aiora"),
        ("Piso en ctra. de Madrid, Delicias, Zaragoza", "delicias"),
    ])
    def test_street_forms_never_become_neighbourhoods(self, title, expected_hood):
        _, _, hood = scraper._parse_location(title, fallback="?")
        assert hood == expected_hood

    @pytest.mark.parametrize("title,expected_hood", [
        # Multi-word property types: the old `^\S+\s+en\s+` stripped one word, so
        # "chalet adosado en russafa" was stored verbatim as a neighbourhood.
        ("Chalet adosado en Russafa, Valencia", "russafa"),
        ("Casa en Miralbueno, Zaragoza", "miralbueno"),
        ("Dúplex en calle del Doctor Monserrat, El Botànic, Valencia", "el botànic"),
        ("Ático dúplex en Nou Moles, Valencia", "nou moles"),
    ])
    def test_property_type_prefixes_are_stripped(self, title, expected_hood):
        _, _, hood = scraper._parse_location(title, fallback="?")
        assert hood == expected_hood

    @pytest.mark.parametrize("title", [
        "Piso en carretera d'Escrivà, 29, Valencia",
        "Piso en pasaje Virgen de Consolación, 12, Sevilla",
    ])
    def test_house_numbers_never_become_areas(self, title):
        muni, district, hood = scraper._parse_location(title, fallback="?")
        # The warehouse held districts literally named "29" and "12".
        assert district not in {"29", "12"}
        assert hood not in {"29", "12"}
        assert muni in {"valencia", "sevilla"}

    @pytest.mark.parametrize("title", [
        "Piso en Gran Via del Marqués del Túria, Gran Vía, València",
        "Piso en Calle del Comte d'Altea, Gran Vía, València",
    ])
    def test_a_barrio_named_after_a_street_type_survives(self, title):
        """
        València has a barrio called "Gran Vía". A loop that keeps dropping
        street-looking segments ate both the street *and* the barrio and returned
        no neighbourhood at all — found on live data, not in review. Idealista
        puts the street first and the area second, so exactly one segment is
        dropped.
        """
        _, _, hood = scraper._parse_location(title, fallback="?")
        assert hood == "gran vía"

    def test_a_number_between_street_and_barrio_is_dropped(self):
        _, _, hood = scraper._parse_location(
            "Piso en venta en calle de Sueca, 34, Russafa, Valencia", fallback="?"
        )
        assert hood == "russafa"

    def test_a_real_barrio_starting_with_a_number_survives(self):
        # Madrid's "12 de Octubre" must not be mistaken for a portal number.
        _, district, hood = scraper._parse_location(
            "Piso en venta en 12 de Octubre, Retiro, Madrid", fallback="?"
        )
        assert hood == "12 de octubre"
        assert district == "retiro"

    def test_an_unmarked_street_name_still_defeats_the_heuristic(self):
        """
        The residual failure, pinned deliberately rather than hidden.

        "Sierra de Bejar" is a street in Valladolid carrying no street keyword,
        so it is indistinguishable from a place name by text alone and lands in
        `neighborhood` while the real barrio is pushed to `district`. No keyword
        list can fix this -- it is why location is canonicalised against the
        `barrios_es` seed downstream instead of being trusted from the title.
        """
        _, district, hood = scraper._parse_location(
            "Chalet adosado en Sierra de Bejar, Covaresa - Parque Alameda, Valladolid",
            fallback="?",
        )
        assert hood == "sierra de bejar"          # not a barrio; the seed rejects it
        assert district == "covaresa - parque alameda"  # the real barrio


class TestExtractSize:
    def test_parses_square_meters(self):
        assert scraper._extract_size(["3 hab.", "90 m²"]) == 90.0

    def test_parses_comma_decimal(self):
        assert scraper._extract_size(["72,5 m2"]) == 72.5

    def test_returns_none_when_missing(self):
        assert scraper._extract_size(["3 hab.", "2 baños"]) is None

    @pytest.mark.parametrize(("text", "expected"), [
        ("1.674 m²", 1674.0),
        ("12.345 m2", 12345.0),
        ("85 m²", 85.0),
        ("85,5 m²", 85.5),
        ("1.674,5 m²", 1674.5),
        ("999 m²", 999.0),
    ])
    def test_spanish_number_formats(self, text, expected):
        assert scraper._extract_size(["4 hab.", text]) == expected


class TestExtractRoomsAndBathrooms:
    def test_extracts_rooms(self):
        assert scraper._extract_rooms(["3 hab."]) == 3

    def test_extracts_bathrooms(self):
        assert scraper._extract_bathrooms(["2 baños"]) == 2

    def test_returns_none_when_absent(self):
        assert scraper._extract_rooms(["90 m²"]) is None


class TestPropertyType:
    def test_house_keywords(self):
        assert scraper._property_type("Chalet en venta en Pozuelo") == "house"

    def test_penthouse_keywords(self):
        assert scraper._property_type("Ático en venta en Malasaña") == "penthouse"

    def test_studio_keywords(self):
        assert scraper._property_type("Estudio en alquiler en Lavapiés") == "studio"

    def test_defaults_to_apartment(self):
        assert scraper._property_type("Piso en venta en Goya") == "apartment"


class TestExtractId:
    def test_extracts_numeric_id(self):
        assert scraper._extract_id("https://www.idealista.com/inmueble/109947740/") == "109947740"

    def test_returns_none_without_match(self):
        assert scraper._extract_id("https://www.idealista.com/somewhere-else/") is None


class TestBuildPageUrl:
    def test_first_page_unchanged(self):
        assert scraper._build_page_url("https://x.com/venta-pisos/madrid/", 1) == "https://x.com/venta-pisos/madrid/"

    def test_subsequent_page_appends_suffix(self):
        assert (
            scraper._build_page_url("https://x.com/venta-pisos/madrid/", 3)
            == "https://x.com/venta-pisos/madrid/pagina-3.htm"
        )

    def test_sort_is_a_query_string_on_every_page(self):
        # The form Idealista's own sort menu links to (captured HTML):
        # /venta-viviendas/madrid-madrid/?ordenado-por=fecha-publicacion-desc
        base = "https://www.idealista.com/venta-viviendas/valencia-valencia/"
        assert (scraper._build_page_url(base, 1, "fecha-publicacion-desc")
                == base + "?ordenado-por=fecha-publicacion-desc")
        assert (scraper._build_page_url(base, 2, "fecha-publicacion-desc")
                == base + "pagina-2.htm?ordenado-por=fecha-publicacion-desc")


def test_search_keys_map_to_the_warehouse_spelling():
    # A fallback municipality must be one the gold test knows, or a truncated
    # title turns a red build into the new phantom city.
    from extraction.scrapers.idealista import _MUNICIPALITY_BY_SEARCH_KEY

    assert _MUNICIPALITY_BY_SEARCH_KEY["valencia"] == "valència"
    assert _MUNICIPALITY_BY_SEARCH_KEY["malaga"] == "málaga"

# ── Card attributes (ADR-0012) ────────────────────────────────────────────────
# The markup below is trimmed from the cached search page in debug_output/
# (gitignored), keeping only the elements the extractors read.
_CARD_WITH_DROP = """
<article class="item"><div class="item-info-container">
  <a class="item-link" href="/inmueble/110438977/" title="Piso en Calle de la Lechuga, Sol, Madrid">x</a>
  <div class="price-row">
    <span class="item-price h2-simulated">820.000<span class="txt-big">€</span></span>
    <span class="pricedown">
      <span class="pricedown_price">845.000 €</span>
      <span class="pricedown_icon icon-pricedown">3%</span>
    </span>
  </div>
  <div class="item-detail-char">
    <span class="item-detail">Garaje <span>opc.</span> 60.000 €</span>
    <span class="item-detail">4 hab.</span>
    <span class="item-detail">110 m²</span>
    <span class="item-detail">Planta 3ª exterior con ascensor</span>
  </div>
  <div class="item-description description"><p class="ellipsis">GILMAR pone a su
    disposición   magnífica vivienda</p></div>
  <div class="listing-tags-container"><span class="listing-tags">Lujo</span>
    <span class="listing-tags">Villa</span></div>
</div></article>
"""

_HOUSE_CARD = """
<article class="item"><div class="item-info-container">
  <a class="item-link" href="/inmueble/111278247/" title="Chalet pareado en Calle de Darío Aparicio, Valdemarín, Madrid">x</a>
  <div class="price-row"><span class="item-price h2-simulated">2.290.000<span class="txt-big">€</span></span>
    <span class="item-price-by-area">5.725 €/m²</span></div>
  <div class="item-detail-char">
    <span class="item-detail">5 hab.</span>
    <span class="item-detail">400 m²</span>
  </div>
</div></article>
"""


def _card(html: str):
    from bs4 import BeautifulSoup
    return BeautifulSoup(html, "lxml").select_one("article.item")


def _details(card) -> list[str]:
    return [s.get_text(" ", strip=True) for s in card.select(".item-detail-char span.item-detail")]


class TestFloor:
    @pytest.mark.parametrize("text, expected", [
        ("Planta 3ª exterior con ascensor", 3),
        ("Planta 9ª exterior con ascensor", 9),
        ("Planta 12ª interior sin ascensor", 12),
        ("Planta 1º exterior", 1),
        ("Planta -1 interior", -1),
        ("Bajo exterior sin ascensor", 0),
        ("Bajo", 0),
        ("Entreplanta interior con ascensor", 0),
        ("Sótano interior", -1),
        ("Semisótano exterior", -1),
        ("Semi-sótano exterior sin ascensor", -1),
        ("Semi sótano", -1),
    ])
    def test_encoding(self, text, expected):
        floor_text = scraper._floor_text(["3 hab.", "90 m²", text])
        assert floor_text == text
        assert scraper._extract_floor(floor_text) == expected

    def test_a_house_has_no_floor(self):
        assert scraper._floor_text(["Garaje incluido", "5 hab.", "400 m²"]) is None
        assert scraper._extract_floor(None) is None

    def test_other_spans_are_not_floors(self):
        # "Garaje", rooms and size must never be read as a floor span.
        assert scraper._floor_text(["Garaje opc. 60.000 €", "3 hab.", "218 m²"]) is None


class TestExteriorAndLift:
    @pytest.mark.parametrize("text, exterior, lift", [
        ("Planta 3ª exterior con ascensor", True, True),
        ("Planta 6ª interior con ascensor", False, True),
        ("Bajo exterior sin ascensor", True, False),
        ("Entreplanta interior", False, None),
        ("Planta 2ª", None, None),
    ])
    def test_stated_values(self, text, exterior, lift):
        details = ["2 hab.", "70 m²", text]
        assert scraper._extract_is_exterior(details) is exterior
        assert scraper._extract_has_lift(details) is lift

    def test_unstated_is_none_never_false(self):
        details = ["Garaje incluido", "5 hab.", "400 m²"]
        assert scraper._extract_is_exterior(details) is None
        assert scraper._extract_has_lift(details) is None


class TestGarage:
    def test_included(self):
        assert scraper._extract_garage(["Garaje incluido", "5 hab."]) == ("Garaje incluido", "included", None)

    def test_optional_with_price_is_not_in_the_asking_price(self):
        assert scraper._extract_garage(["Garaje opc. 60.000 €", "3 hab."]) == (
            "Garaje opc. 60.000 €", "optional", 60000.0,
        )

    def test_optional_spelled_out(self):
        assert scraper._extract_garage(["Garaje opcional 20.000 €"]) == (
            "Garaje opcional 20.000 €", "optional", 20000.0,
        )

    def test_optional_without_price(self):
        assert scraper._extract_garage(["Garaje opc."]) == ("Garaje opc.", "optional", None)

    def test_unrecognised_garage_wording_keeps_the_text_only(self):
        assert scraper._extract_garage(["Garaje comunitario"]) == ("Garaje comunitario", None, None)

    def test_no_garage_span_is_unknown_not_no(self):
        assert scraper._extract_garage(["3 hab.", "90 m²"]) == (None, None, None)


class TestPriceDrop:
    def test_reads_the_portals_marker(self):
        assert scraper._extract_price_drop(_card(_CARD_WITH_DROP)) == (845000.0, 3.0)

    def test_no_marker_is_none(self):
        assert scraper._extract_price_drop(_card(_HOUSE_CARD)) == (None, None)

    def test_price_marker_does_not_leak_into_current_price(self):
        assert scraper._extract_price(_card(_CARD_WITH_DROP)) == 820000.0


class TestDescriptionAndTags:
    def test_description_collapses_whitespace(self):
        assert scraper._extract_description(_card(_CARD_WITH_DROP)) == (
            "GILMAR pone a su disposición magnífica vivienda"
        )

    def test_description_is_capped_at_a_word_boundary(self):
        long = "<article class='item'><div class='item-description'><p>" + "palabra " * 300 + "</p></div></article>"
        text = scraper._extract_description(_card(long))
        assert len(text) <= scraper._DESCRIPTION_MAX_CHARS + 1
        assert text.endswith("palabra…")

    def test_missing_description_and_tags_are_none(self):
        card = _card(_HOUSE_CARD)
        assert scraper._extract_description(card) is None
        assert scraper._extract_tags(card) is None

    def test_tags_are_pipe_delimited(self):
        assert scraper._extract_tags(_card(_CARD_WITH_DROP)) == "Lujo|Villa"


class TestParseSearchCard:
    def test_a_flat_card_end_to_end(self):
        from extraction.schemas.raw_listings import RawListing

        row = scraper._parse_search_card(_card(_CARD_WITH_DROP), "sale")
        listing = RawListing(**row)
        assert listing.raw_price_eur == 820000.0
        assert listing.raw_floor == 3
        assert listing.raw_floor_text == "Planta 3ª exterior con ascensor"
        assert listing.raw_is_exterior is True
        assert listing.raw_has_lift is True
        assert listing.raw_garage == "optional"
        assert listing.raw_garage_price_eur == 60000.0
        assert listing.raw_previous_price_eur == 845000.0
        assert listing.raw_price_drop_pct == 3.0
        assert listing.raw_tags == "Lujo|Villa"
        assert listing.raw_bathrooms is None   # never on the card

    def test_a_house_card_states_nothing_about_floor_or_lift(self):
        from extraction.schemas.raw_listings import RawListing

        listing = RawListing(**scraper._parse_search_card(_card(_HOUSE_CARD), "sale"))
        for field in ("raw_floor", "raw_floor_text", "raw_is_exterior", "raw_has_lift",
                      "raw_garage", "raw_previous_price_eur", "raw_price_drop_pct",
                      "raw_description", "raw_tags"):
            assert getattr(listing, field) is None, field


class TestCoverageStats:
    def test_stats_count_pages_cards_and_blocks(self, monkeypatch):
        monkeypatch.setattr("extraction.scrapers.idealista.IDEALISTA_MAX_SEARCH_PAGES", 4)
        s = IdealistaScraper(province="valencia")
        pages = iter(["<html>ok</html>", "BLOCK"])
        s._get_html = lambda _url: next(pages)
        s._is_blocked = lambda html: html == "BLOCK"
        s._polite_sleep = lambda: None
        s._parse_search_page = lambda _html, _op: [{"source_id": "1"}]
        list(s._paginate("sale"))
        assert s.stats == {
            "pages_requested": 2, "pages_with_cards": 1, "pages_blocked": 1, "listings": 0,
            "cards_out_of_area": 0,
        }

    def test_a_page_that_repeats_earlier_cards_stops_the_run(self, monkeypatch):
        """An area search that ignores pagination must not buy page 1 five times."""
        s = IdealistaScraper(province="valencia", max_pages=5)
        fetched = []
        s._get_html = lambda url: fetched.append(url) or "<html>ok</html>"
        s._is_blocked = lambda _html: False
        s._polite_sleep = lambda: None
        s._parse_search_page = lambda _html, _op: [{"source_id": "1"}, {"source_id": "2"}]
        assert len(list(s._paginate("sale"))) == 2
        assert len(fetched) == 2


# ── Zones: the l'Horta Nord + Camp de Túria area search (ADR-0013) ─────────────

def _zone_card(sid: str, title: str) -> str:
    return f"""
<article class="item"><div class="item-info-container">
  <a class="item-link" href="/inmueble/{sid}/" title="{title}">x</a>
  <span class="item-price">250.000<span>€</span></span>
  <div class="item-detail-char"><span class="item-detail">3 hab.</span>
  <span class="item-detail">95 m²</span></div>
</div></article>"""


class TestZones:
    def test_polyline_matches_the_reference_encoding(self):
        from extraction.config import encode_polyline

        # Google's documented example for the encoded-polyline format.
        pts = [(38.5, -120.2), (40.7, -120.95), (43.252, -126.453)]
        assert encode_polyline(pts) == "_p~iF~ps|U_ulLnnqC_mqNvxq`@"

    def test_zone_url_has_idealista_shape_form(self):
        from extraction.config import get_idealista_target_url

        url = get_idealista_target_url("horta-nord-camp-turia", "sale")
        assert url.startswith("https://www.idealista.com/areas/venta-viviendas/?shape=%2528%2528")
        assert url.endswith("%2529%2529")
        assert get_idealista_target_url("valencia", "rent").endswith(
            "/alquiler-viviendas/valencia-valencia/")

    def test_page_urls_for_city_and_area(self):
        b = IdealistaScraper._build_page_url
        city = "https://www.idealista.com/venta-viviendas/valencia-valencia/"
        assert b(city, 1, "fecha-publicacion-desc") == city + "?ordenado-por=fecha-publicacion-desc"
        assert b(city, 2, "fecha-publicacion-desc") == (
            "https://www.idealista.com/venta-viviendas/valencia-valencia/pagina-2.htm"
            "?ordenado-por=fecha-publicacion-desc")
        area = "https://www.idealista.com/areas/venta-viviendas/?shape=%2528%2528abc%2529%2529"
        assert b(area, 1, "") == area
        assert b(area, 3, "fecha-publicacion-desc") == (
            "https://www.idealista.com/areas/venta-viviendas/pagina-3"
            "?shape=%2528%2528abc%2529%2529&ordenado-por=fecha-publicacion-desc")

    @pytest.mark.parametrize(("raw", "canonical"), [
        ("alboraya", "alboraia"), ("puzol", "puçol"), ("pobla de farnals (la)", "la pobla de farnals"),
        ("eliana (l')", "l'eliana"), ("l´eliana", "l'eliana"), ("ribarroja del turia", "riba-roja de túria"),
        ("montcada", "moncada"), ("valència", "valència"), ("godella", "godella"),
    ])
    def test_town_spellings_collapse_to_the_seed(self, raw, canonical):
        assert IdealistaScraper._canonical_municipality(raw) == canonical

    def test_seed_names_every_canonical_alias_target(self):
        from extraction.config import comarca_municipalities
        from extraction.scrapers.idealista import _MUNICIPALITY_ALIASES

        assert set(_MUNICIPALITY_ALIASES.values()) <= comarca_municipalities()

    def test_area_search_keeps_only_seeded_towns(self):
        s = IdealistaScraper(province="horta-nord-camp-turia")
        html = "".join([
            _zone_card("1", "Piso en Calle de Sant Pancrás, Zona Concordia, Burjassot"),
            _zone_card("2", "Casa o chalet en La Presa - Collado - La Malla, Manises"),
            _zone_card("3", "Chalet adosado en Alboraya"),
            _zone_card("4", "Piso en"),            # names no place: no fallback in a zone
        ])
        cards = s._keep_in_area(s._parse_search_page(html, "sale"))
        assert [(c["source_id"], c["raw_municipality"]) for c in cards] == [
            ("1", "burjassot"), ("3", "alboraia")]
        assert s.stats["cards_out_of_area"] == 1

    def test_a_city_search_keeps_its_fallback(self):
        s = IdealistaScraper(province="valencia")
        cards = s._parse_search_page(_zone_card("9", "Piso en"), "sale")
        assert cards[0]["raw_municipality"] == "valència"
