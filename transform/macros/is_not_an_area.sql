-- transform/macros/is_not_an_area.sql
--
-- True when a scraped location string is plainly not a place: a street, a portal
-- number, or a property type that leaked out of the listing title.
--
-- This exists because the extraction-side heuristic is fallible by construction.
-- Idealista titles do not label their segments, so a parser can only guess which
-- comma-separated part is an area, and when it guesses wrong the wrong value
-- lands in `neighborhood` -- where fct_listings_scored happily uses it as a
-- benchmark grouping key. The warehouse has held barrios called "34", "7 -5",
-- "chalet adosado en russafa" and "piso en calle dels vivons".
--
-- Rejecting them here, in silver, rather than only at extraction time is
-- deliberate: silver can be rebuilt from raw at any moment, so a fix to this
-- pattern repairs every historical row on the next `dbt build`. A fix to the
-- Python parser only ever helps rows scraped afterwards.
--
-- The pattern is intentionally conservative. It rejects only what cannot be an
-- area; anything ambiguous is left alone and handled by the barrios_es seed
-- lookup, which decides canonicality by positive evidence instead.
{% macro is_not_an_area(col) %}
    (
        {{ col }} is null
        -- A bare portal number: "34", "7 -5", "5 nb", "12 bis". Capped at three
        -- trailing characters so Madrid's real "12 de Octubre" survives.
        or regexp_matches(lower(trim({{ col }})), '^[0-9]+\s*[-–]?\s*\w{0,3}$')
        -- A street, in Spanish, Catalan/Valencian or abbreviated form.
        or regexp_matches(lower(trim({{ col }})),
             '(^|\s)(calle|c/|cl|carrer|avenida|avinguda|avda?|av|paseo|passeig|'
             'plaza|placa|plaça|pza|pl|gran\s+v[ií]a|carretera|ctra|passatge|'
             'pasaje|rambla|ronda|glorieta|traves[ií]a|travessera|camino|cam[ií]|'
             'callej[oó]n|cuesta|bajada|subida|costanilla|corredera|bulevar|'
             'boulevard|muelle|moll|pol[ií]gono)(\s|$)')
        -- A property type still attached to the location, e.g. the parser's
        -- old single-word prefix strip leaving "chalet adosado en russafa".
        or regexp_matches(lower(trim({{ col }})),
             '^(piso|pisos|apartamento|casa|casas|chalet|adosado|pareado|'
             'unifamiliar|villa|finca|[aá]tico|d[uú]plex|estudio|studio|loft|'
             'penthouse|bajo|planta|inmueble|vivienda)(\s|$)')
    )
{% endmacro %}
