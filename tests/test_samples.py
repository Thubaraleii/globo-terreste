import math

import pandas as pd
import pytest

from pipeline.common.model import CRS, SCHEMAS
from pipeline.samples import NormalizeResult, normalize_samples

COLMAP = {
    "SampleID": "id",
    "Rock": "rock_name",
    "Lat": "lat",
    "Lon": "lon",
    "Place": "locality",
    "Nation": "country",
}
MAPPING = {"basalt": "mafic", "dunite": "ultramafic", "gabbro": "mafic"}


def _df(rows):
    cols = ["SampleID", "Rock", "Lat", "Lon", "Place", "Nation"]
    return pd.DataFrame(rows, columns=cols)


def _run(rows, colmap=COLMAP):
    return normalize_samples(_df(rows), "src1", colmap, MAPPING)


def test_unmapped_rock_names_excluded_and_counted():
    res = _run([
        ["a", "Basalt", -10.0, -50.0, None, None],
        ["b", "Granite", -10.0, -50.0, None, None],
        ["c", "granite ", -11.0, -51.0, None, None],
        ["d", None, -11.0, -51.0, None, None],
        ["e", "  ", -11.0, -51.0, None, None],
    ])
    assert isinstance(res, NormalizeResult)
    assert list(res.located["id"]) == ["a"]
    assert len(res.pending) == 0
    assert res.unmapped == {"granite": 2, "<vazio>": 2}
    assert res.dropped_invalid == 0


@pytest.mark.parametrize("lat,lon", [
    (0.0, 0.0),
    (91.0, -50.0),
    (-10.0, 181.0),
    (float("nan"), -50.0),
    (-10.0, None),
    ("abc", -50.0),
    (float("inf"), -50.0),
])
def test_invalid_coords_dropped_and_counted(lat, lon):
    res = _run([
        ["a", "Basalt", lat, lon, "Somewhere", "Brazil"],
        ["b", "Basalt", -10.0, -50.0, None, None],
    ])
    assert list(res.located["id"]) == ["b"]
    assert len(res.pending) == 0
    assert res.dropped_invalid == 1


def test_swapped_lat_lon_out_of_range_is_dropped():
    res = _run([["a", "Dunite", 120.0, 40.0, None, None]])
    assert len(res.located) == 0
    assert res.dropped_invalid == 1


def test_rows_without_coords_but_with_locality_go_to_pending():
    res = _run([
        ["a", "Basalt", None, None, "Serra Geral", "Brazil"],
        ["b", "Gabbro", "", " ", "Bushveld", None],
        ["c", "Basalt", None, None, None, "Brazil"],
        ["d", "Basalt", None, None, "  ", None],
        ["e", "Granite", None, None, "Somewhere", None],
    ])
    assert len(res.located) == 0
    assert list(res.pending["id"]) == ["a", "b"]
    assert list(res.pending["locality"]) == ["Serra Geral", "Bushveld"]
    assert res.pending["country"].iloc[0] == "Brazil"
    assert res.pending["country"].iloc[1] is None
    assert list(res.pending["rock_class"]) == ["mafic", "mafic"]
    assert "geometry" not in res.pending.columns
    assert res.dropped_invalid == 2
    assert res.unmapped == {"granite": 1}


def test_rock_name_original_preserved_verbatim():
    res = _run([["a", "  BASÁLTO ", -10.0, -50.0, None, None]])
    # "basalto" nao esta no mapa -> excluido; testa com nome mapeado
    assert len(res.located) == 0
    res = _run([["a", "  Basalt ", -10.0, -50.0, None, None]])
    assert res.located["rock_name_original"].iloc[0] == "  Basalt "
    assert res.located["rock_class"].iloc[0] == "mafic"


def test_coord_source_reported_and_uncertainty_null():
    res = _run([["a", "Basalt", -10.5, -50.25, None, None]])
    gdf = res.located
    assert list(gdf.columns) == SCHEMAS["samples"]
    assert gdf.crs == CRS
    assert gdf["coord_source"].iloc[0] == "reported"
    assert math.isnan(gdf["coord_uncertainty_m"].iloc[0])
    assert gdf["unit_id"].iloc[0] is None
    assert gdf["dup_group"].iloc[0] is None
    assert gdf["source_id"].iloc[0] == "src1"
    pt = gdf.geometry.iloc[0]
    assert (pt.x, pt.y) == (-50.25, -10.5)


def test_id_is_string_and_falls_back_to_source_and_row_index():
    res = _run([
        [123, "Basalt", -10.0, -50.0, None, None],
        [None, "Basalt", -10.0, -50.0, None, None],
        ["  ", "Basalt", -10.0, -50.0, None, None],
    ])
    assert list(res.located["id"]) == ["123", "src1:1", "src1:2"]


def test_missing_optional_columns_and_id_column():
    colmap = {"Rock": "rock_name", "Lat": "lat", "Lon": "lon"}
    df = pd.DataFrame({"Rock": ["Basalt", "Basalt"], "Lat": [1.0, None], "Lon": [2.0, None]})
    res = normalize_samples(df, "src2", colmap, MAPPING)
    assert list(res.located["id"]) == ["src2:0"]
    assert len(res.pending) == 0
    assert res.dropped_invalid == 1


def test_located_writes_to_geopackage(tmp_path):
    from pipeline.common.model import create_geopackage, write_layer
    import pyogrio

    res = _run([["a", "Basalt", -10.0, -50.0, None, None]])
    gpkg = tmp_path / "t.gpkg"
    create_geopackage(gpkg)
    write_layer(gpkg, "samples", res.located)
    back = pyogrio.read_dataframe(gpkg, layer="samples")
    assert list(back["id"]) == ["a"]
