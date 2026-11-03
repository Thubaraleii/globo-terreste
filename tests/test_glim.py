"""Testes de normalize_glim com dados SINTETICOS (nao sao dados reais do GLiM)."""
import geopandas as gpd
import pytest
from shapely.geometry import LineString, MultiPolygon, Polygon, box

from pipeline.common.model import CRS, SCHEMAS, create_geopackage, write_layer
from pipeline.glim import GLIM_CLASSES, GLIM_COLUMNS, normalize_glim

CODE_COL = next(src for src, logical in GLIM_COLUMNS.items() if logical == "code")


def _units(codes, geoms, crs=CRS, **extra):
    return gpd.GeoDataFrame({CODE_COL: codes, **extra}, geometry=geoms, crs=crs)


def test_normalize_glim_keeps_original_code():
    gdf = _units(["vb", "SU "], [box(0, 0, 1, 1), box(1, 0, 2, 1)])
    out = normalize_glim(gdf, "glim")
    assert list(out.columns) == SCHEMAS["geo_units"]
    assert out.crs == CRS
    assert list(out["lith_original"]) == ["vb", "SU "]
    assert list(out["lith_class"]) == ["basic_volcanic", "unconsolidated_sediments"]
    assert list(out["source_id"]) == ["glim", "glim"]


def test_unknown_code_class_is_null():
    gdf = _units(["zz", None, "", "mt"], [box(i, 0, i + 1, 1) for i in range(4)])
    out = normalize_glim(gdf, "glim")
    assert out["lith_class"].isna().tolist() == [True, True, True, False]
    assert out["lith_original"].iloc[0] == "zz"
    assert out["lith_original"].iloc[1] is None
    assert out["lith_class"].iloc[3] == "metamorphics"


def test_classes_cover_glim_first_level_codes():
    assert set(GLIM_CLASSES) == {
        "su", "ss", "sc", "sm", "py", "va", "vi", "vb",
        "pa", "pi", "pb", "mt", "ev", "wb", "ig", "nd",
    }


def test_invalid_polygons_repaired():
    bowtie = Polygon([(0, 0), (2, 2), (2, 0), (0, 2)])
    gdf = _units(["vb", "va"], [bowtie, box(5, 5, 6, 6)])
    out = normalize_glim(gdf, "glim")
    assert len(out) == 2
    assert out.geometry.is_valid.all()
    assert out.geometry.iloc[0].area == pytest.approx(2.0)
    assert out.attrs["repaired"] == 1
    assert out.attrs["dropped_non_polygon"] == 0


def test_non_polygonal_parts_dropped():
    # poligono com "espinho" de area nula -> make_valid devolve GeometryCollection
    spike = Polygon([(0, 0), (1, 0), (1, 1), (0, 1), (0, 0.5), (-1, 0.5), (0, 0.5)])
    flat = Polygon([(0, 0), (1, 1), (2, 2), (0, 0)])  # degenerado -> linha
    gdf = _units(
        ["vb", "va", "mt", "pb"],
        [spike, flat, LineString([(0, 0), (1, 1)]), None],
    )
    out = normalize_glim(gdf, "glim")
    assert list(out["unit_id"]) == ["glim:0"]
    assert out.geometry.iloc[0].geom_type in ("Polygon", "MultiPolygon")
    assert out.geometry.iloc[0].area == pytest.approx(1.0)
    assert out.attrs["dropped_non_polygon"] == 3


def test_unit_id_stable_from_input_position():
    flat = Polygon([(0, 0), (1, 1), (2, 2), (0, 0)])
    gdf = _units(["vb", "va", "mt"], [box(0, 0, 1, 1), flat, box(2, 0, 3, 1)])
    gdf.index = [10, 20, 30]
    a = normalize_glim(gdf, "glim")
    b = normalize_glim(gdf, "glim")
    assert list(a["unit_id"]) == ["glim:0", "glim:2"]
    assert list(a["unit_id"]) == list(b["unit_id"])


def test_unit_id_uses_source_id_column_when_mapped():
    cols = {**GLIM_COLUMNS, "IDENT": "id"}
    gdf = _units(["vb", "va"], [box(0, 0, 1, 1), box(1, 0, 2, 1)], IDENT=["A7", " "])
    out = normalize_glim(gdf, "glim", columns=cols)
    assert list(out["unit_id"]) == ["A7", "glim:1"]


def test_reprojects_to_wgs84_and_requires_crs():
    gdf = _units(["vb"], [box(0, 0, 1000, 1000)], crs="EPSG:3857")
    out = normalize_glim(gdf, "glim")
    assert out.crs == CRS
    with pytest.raises(ValueError):
        normalize_glim(_units(["vb"], [box(0, 0, 1, 1)], crs=None), "glim")


def test_missing_code_column_raises():
    gdf = gpd.GeoDataFrame({"other": ["vb"]}, geometry=[box(0, 0, 1, 1)], crs=CRS)
    with pytest.raises(ValueError, match="codigo"):
        normalize_glim(gdf, "glim")


def test_output_writes_to_geopackage(tmp_path):
    gpkg = tmp_path / "out.gpkg"
    create_geopackage(gpkg)
    gdf = _units(
        ["vb", "pb"],
        [box(0, 0, 1, 1), MultiPolygon([box(2, 0, 3, 1), box(4, 0, 5, 1)])],
    )
    write_layer(gpkg, "geo_units", normalize_glim(gdf, "glim"))
    back = gpd.read_file(gpkg, layer="geo_units")
    assert list(back["unit_id"]) == ["glim:0", "glim:1"]
