"""
The Overview map: the shapes on disk, the bands, and how the geometry travels.
"""
from __future__ import annotations

import base64
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from components.charts import _map_band, map_barrio_ppsqm  # noqa: E402
import pandas as pd  # noqa: E402

SHAPES = Path(__file__).resolve().parent.parent / "assets" / "valencia_barrios.geojson"


def _shapes() -> dict:
    return json.loads(SHAPES.read_text(encoding="utf-8"))


def test_bands_split_at_five_and_fifteen_percent():
    assert _map_band(-20) == "15%+ under"
    assert _map_band(-10) == "5–15% under"
    assert _map_band(0) == "Within 5%"
    assert _map_band(10) == "5–15% over"
    assert _map_band(40) == "15%+ over"


def test_outer_rings_wind_clockwise():
    # d3-geo fills the complement of a counter-clockwise ring: the first render
    # of this map was one rust rectangle covering the globe.
    for f in _shapes()["features"]:
        ring = f["geometry"]["coordinates"][0]
        area2 = sum(x0 * y1 - x1 * y0
                    for (x0, y0), (x1, y1) in zip(ring, ring[1:], strict=False))
        assert area2 < 0, f["properties"]["name"]


def test_geometry_travels_as_a_url_and_thin_barrios_stay_drawn():
    # Inline values are converted to Arrow by st.altair_chart, which destroys
    # nested geometry — the map rendered as a legend over nothing.
    stats = pd.DataFrame({"neighborhood": ["russafa", "benimaclet"],
                          "listings": [30, 3], "median_ppsqm": [5000.0, 3000.0]})
    spec = map_barrio_ppsqm(_shapes(), stats, 4000.0, 8).to_dict()
    url = spec["data"]["url"]
    assert url.startswith("data:application/json;base64,")
    features = json.loads(base64.b64decode(url.split(",", 1)[1]))["features"]
    bands = {f["properties"]["area"]: f["properties"]["band"] for f in features}
    assert bands["Russafa"] == "15%+ over"
    assert bands["Benimaclet"] == "Too few listings"
    assert len(features) == len(_shapes()["features"])
