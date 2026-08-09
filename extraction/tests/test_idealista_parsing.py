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
