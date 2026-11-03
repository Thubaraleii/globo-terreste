"""Fallback GDAL dos PMTiles (sem tippecanoe) com dados SINTETICOS."""
import geopandas as gpd
import pandas as pd
import pytest
from pyogrio import read_dataframe, read_info
from shapely.geometry import Point, box

from pipeline import export
from pipeline.common.model import CRS, create_geopackage, write_layer
from pipeline.export import GDAL_PMTILES_OPTIONS, GDAL_WARNING, export_web

pytestmark = pytest.mark.skipif(not export.gdal_pmtiles_available(),
                                reason="drivers MVT/PMTiles de escrita ausentes no GDAL")


def _gpkg(tmp_path):
    g = tmp_path / "geoworld.gpkg"
    create_geopackage(g)
    for layer in ("volcanoes", "tectonic_zones"):
        write_layer(g, layer, gpd.GeoDataFrame(
            {"source_id": []}, geometry=[], crs=CRS))
    write_layer(g, "geo_units", gpd.GeoDataFrame(
        {"unit_id": ["u1", "u2"], "lith_class": ["vb", None], "source_id": ["glim", "glim"]},
        geometry=[box(0, 0, 10, 10), box(20, 20, 30, 30)], crs=CRS))
    write_layer(g, "samples", gpd.GeoDataFrame(
        {"id": ["s1", "s2"], "rock_name_original": ["basalt", "dunite"],
         "rock_class": ["mafic", "ultramafic"],
         "coord_uncertainty_m": pd.array([500, None], dtype="Int64"),
         "unit_id": ["u1", None], "source_id": ["s", "s"]},
        geometry=[Point(5, 5), Point(100, -20)], crs=CRS))
    return g


def test_gdal_fallback_writes_openable_pmtiles(tmp_path):
    out = tmp_path / "web"
    res = export_web(_gpkg(tmp_path), out, tippecanoe=None)
    assert GDAL_WARNING in res.warnings
    assert "GDAL" in GDAL_WARNING and "tippecanoe recomendado" in GDAL_WARNING
    for layer in ("samples", "geo_units"):
        path = out / f"{layer}.pmtiles"
        assert path.exists() and path in res.files
        info = read_info(path)
        assert info["layer_name"] == layer
        meta = info["dataset_metadata"]
        opts = GDAL_PMTILES_OPTIONS[layer]
        assert meta["minzoom"] == opts["MINZOOM"] and meta["maxzoom"] == opts["MAXZOOM"]
    # nao sobram arquivos temporarios do GDAL
    assert sorted(p.name for p in out.iterdir() if "tmp" in p.name) == []


def test_gdal_pmtiles_carry_extra_properties_and_nulls(tmp_path):
    out = tmp_path / "web"
    export_web(_gpkg(tmp_path), out, tippecanoe=None)
    maxz = GDAL_PMTILES_OPTIONS["samples"]["MAXZOOM"]
    samples = read_dataframe(out / "samples.pmtiles", ZOOM_LEVEL=maxz)
    by_id = samples.drop_duplicates("id").set_index("id")
    assert by_id.loc["s1", "unit_lith_class"] == "vb"
    assert by_id.loc["s1", "coord_uncertainty_m"] == 500
    assert pd.isna(by_id.loc["s2", "unit_lith_class"])
    assert pd.isna(by_id.loc["s2", "coord_uncertainty_m"])
    units = read_dataframe(out / "geo_units.pmtiles",
                           ZOOM_LEVEL=GDAL_PMTILES_OPTIONS["geo_units"]["MAXZOOM"])
    counts = units.drop_duplicates("unit_id").set_index("unit_id")["sample_count"]
    assert counts["u1"] == 1 and counts["u2"] == 0


def test_gdal_fallback_can_be_disabled(tmp_path):
    out = tmp_path / "web"
    res = export_web(_gpkg(tmp_path), out, tippecanoe=None, gdal_fallback=False)
    assert not list(out.glob("*.pmtiles"))
    assert GDAL_WARNING not in res.warnings


def test_tippecanoe_path_unchanged_when_binary_given(tmp_path):
    calls = []

    def run(cmd, **kw):
        calls.append(cmd)
        if "--version" not in cmd:
            from pathlib import Path
            Path(cmd[cmd.index("-o") + 1]).write_bytes(b"x")
        return type("P", (), {"stdout": b"tippecanoe v2.53.0", "stderr": b"", "returncode": 0})()

    res = export_web(_gpkg(tmp_path), tmp_path / "web", tippecanoe="tippecanoe", run=run)
    assert GDAL_WARNING not in res.warnings
    assert any("-o" in c for c in calls)
