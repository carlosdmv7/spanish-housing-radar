"""
Fetch València's official barrio outlines for the Overview map.

    uv run python scripts/fetch_barrio_shapes.py

Writes app/assets/valencia_barrios.geojson. The source is the city's own
Geoportal layer (88 barrios, already WGS84), found through the open-data
catalogue at opendata.vlci.valencia.es, package `barris-barrios`. Run it again
only if the city redraws a barrio; the shapes are static reference data, and
they are committed so the app never depends on the Geoportal being up.

Each outline is keyed by the barrio's canonical name in
transform/seeds/barrios_es.csv — the name the warehouse groups on — so the app
joins the map to its medians without a lookup table of its own. A barrio that
matches no seed name keeps its Geoportal name and is reported: the warehouse
cannot group listings on a name the seed does not know, so the map draws it
grey, and the report says why rather than leaving it to be noticed.

Kept: districts 1–16 and 18, the contiguous city. Left out: 17 (Pobles del
Nord) and 19 (Pobles del Sud), the villages across the huerta and the
Albufera. They are two thirds of the municipality's area and would shrink the
city itself to a corner of the map.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path
import unicodedata
import urllib.request

ROOT = Path(__file__).resolve().parent.parent
SEED = ROOT / "transform" / "seeds" / "barrios_es.csv"
OUT = ROOT / "app" / "assets" / "valencia_barrios.geojson"
URL = ("https://geoportal.valencia.es/server/rest/services/OPENDATA/"
       "UrbanismoEInfraestructuras/MapServer/224/query"
       "?where=1=1&outFields=nombre,coddistrit&f=geojson")
LEFT_OUT = {"17", "19"}
# Where the Geoportal's name and the seed's differ by more than accents.
GEOPORTAL_TO_SEED = {
    "cabanyal-canyamelar": "el cabanyal",
    "ciutat de les arts i de les ciencies": "ciutat de les arts",
    "la gran via": "gran via",
}
DECIMALS = 5  # ~1 m at this latitude; the source carries 15


def _key(name: str) -> str:
    plain = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return " ".join(plain.lower().split())


def _clockwise(ring: list[list[float]], outer: bool) -> list[list[float]]:
    """
    Wind an outer ring clockwise and a hole counter-clockwise.

    Vega draws with d3-geo, which reads rings on the sphere: a ring wound the
    other way encloses everything *except* the barrio. The Geoportal winds its
    outer rings counter-clockwise (the RFC 7946 convention), and the first
    render of this map was one rust rectangle — every barrio covering the globe.
    """
    area2 = sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(ring, ring[1:], strict=False))
    is_clockwise = area2 < 0
    return ring if is_clockwise == outer else ring[::-1]


def _seed_names() -> dict[str, str]:
    """Accent-free alias → canonical barrio name, for València."""
    with SEED.open(encoding="utf-8") as fh:
        rows = [r for r in csv.DictReader(fh) if r["municipality"] == "valència"]
    names = {_key(r["alias"]): r["neighborhood"] for r in rows}
    names.update({_key(r["neighborhood"]): r["neighborhood"] for r in rows})
    return names


def main() -> None:
    with urllib.request.urlopen(URL, timeout=60) as resp:  # noqa: S310 — fixed https URL
        source = json.load(resp)

    seed = _seed_names()
    features, unmatched = [], []
    for f in source["features"]:
        props = f["properties"]
        if str(props["coddistrit"]) in LEFT_OUT:
            continue
        key = _key(props["nombre"])
        name = seed.get(GEOPORTAL_TO_SEED.get(key, key))
        if name is None:
            unmatched.append(props["nombre"])
            name = props["nombre"].lower()
        rings = [_clockwise([[round(x, DECIMALS), round(y, DECIMALS)] for x, y in ring],
                            outer=i == 0)
                 for i, ring in enumerate(f["geometry"]["coordinates"])]
        features.append({
            "type": "Feature",
            "properties": {"name": name},
            "geometry": {"type": f["geometry"]["type"], "coordinates": rings},
        })

    OUT.write_text(json.dumps({"type": "FeatureCollection", "features": features},
                              ensure_ascii=False, separators=(",", ":")),
                   encoding="utf-8")
    print(f"{len(features)} barrios → {OUT.relative_to(ROOT)} "
          f"({OUT.stat().st_size / 1024:.0f} KB)")
    if unmatched:
        print(f"Not in barrios_es.csv, drawn without data: {', '.join(sorted(unmatched))}")


if __name__ == "__main__":
    main()
