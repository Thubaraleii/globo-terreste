"""Testes de export_web com dados SINTETICOS (sem rede, sem tippecanoe real)."""
import json
import shutil
import subprocess
from pathlib import Path

import geopandas as gpd
import pandas as pd
import pytest
from pyogrio import read_dataframe
from shapely.geometry import LineString, Point, box

from pipeline import export
from pipeline.common.model import CRS, create_geopackage, write_layer
from pipeline.export import ExportResult, export_web


def _gpkg(tmp_path, with_units=True, with_samples=True):
    g = tmp_path / "geoworld.gpkg"
    create_geopackage(g)
    write_layer(g, "volcanoes", gpd.GeoDataFrame(
        {"name": ["Etna", None], "kind": ["volcano", "volcano"], "source_id": ["gvp", "gvp"]},
        geometry=[Point(15.0, 37.75), Point(-10.5, 5.25)], crs=CRS,
    ))
    write_layer(g, "tectonic_zones", gpd.GeoDataFrame(
        {
            "rank": pd.array([1, None], dtype="Int64"),
            "name": ["zona A", None],
            "moment_total": [1.5e20, None],
            "source_id": ["tz", "tz"],
        },
        geometry=[LineString([(0, 0), (1, 1)]), box(2, 2, 3, 3)], crs=CRS,
    ))
    if with_units:
        write_layer(g, "geo_units", gpd.GeoDataFrame(
            {"unit_id": ["u1"], "lith_class": ["granite"], "source_id": ["glim"]},
            geometry=[box(0, 0, 1, 1)], crs=CRS,
        ))
    if with_samples:
        write_layer(g, "samples", gpd.GeoDataFrame(
            {"id": ["s1"], "rock_name_original": ["basalt"], "source_id": ["s"]},
            geometry=[Point(0.5, 0.5)], crs=CRS,
        ))
    return g


def _read(path):
    return json.loads(path.read_text(encoding="utf-8"))


class FakeRunner:
    """Registra os comandos e cria o arquivo de saida (-o) como o tippecanoe."""

    def __init__(self):
        self.calls = []

    def __call__(self, cmd, **kwargs):
        self.calls.append((list(cmd), kwargs))
        Path(cmd[cmd.index("-o") + 1]).write_bytes(b"PMTiles")
        return subprocess.CompletedProcess(cmd, 0, b"", b"")


def test_export_writes_geojson_for_small_layers(tmp_path):
    out = tmp_path / "web"
    res = export_web(_gpkg(tmp_path), out, tippecanoe=None)
    assert isinstance(res, ExportResult)
    v = _read(out / "volcanoes.geojson")
    t = _read(out / "tectonic_zones.geojson")
    assert v["type"] == "FeatureCollection" and len(v["features"]) == 2
    assert v["features"][0]["geometry"] == {"type": "Point", "coordinates": [15.0, 37.75]}
    assert v["features"][0]["properties"]["name"] == "Etna"
    assert set(v["features"][0]["properties"]) == {
        "name", "kind", "type", "last_eruption", "country", "reference", "source_id",
    }
    assert [f["geometry"]["type"] for f in t["features"]] == ["LineString", "Polygon"]
    assert t["features"][0]["properties"]["rank"] == 1
    assert isinstance(t["features"][0]["properties"]["rank"], int)
    assert {out / "volcanoes.geojson", out / "tectonic_zones.geojson"} <= set(res.files)


def test_geojson_nulls_stay_null(tmp_path):
    out = tmp_path / "web"
    export_web(_gpkg(tmp_path), out, tippecanoe=None)
    text = (out / "tectonic_zones.geojson").read_text(encoding="utf-8")
    assert "NaN" not in text
    props = _read(out / "tectonic_zones.geojson")["features"][1]["properties"]
    assert props["rank"] is None
    assert props["name"] is None
    assert props["moment_total"] is None
    assert props["period_start"] is None
    vprops = _read(out / "volcanoes.geojson")["features"][1]["properties"]
    assert vprops["name"] is None and vprops["country"] is None


def test_empty_layer_gives_valid_empty_feature_collection(tmp_path):
    g = tmp_path / "empty.gpkg"
    create_geopackage(g)
    out = tmp_path / "web"
    export_web(g, out, tippecanoe=None)
    assert _read(out / "volcanoes.geojson") == {"type": "FeatureCollection", "features": []}
    assert _read(out / "tectonic_zones.geojson") == {"type": "FeatureCollection", "features": []}


def test_export_without_tippecanoe_warns_and_skips_pmtiles(tmp_path):
    out = tmp_path / "web"
    res = export_web(_gpkg(tmp_path), out, tippecanoe=None)
    assert not (out / "geo_units.pmtiles").exists()
    assert not (out / "samples.pmtiles").exists()
    assert all(p.suffix == ".geojson" for p in res.files)
    assert any("tippecanoe" in w for w in res.warnings)


def test_stale_pmtiles_removed_when_tippecanoe_absent(tmp_path):
    out = tmp_path / "web"
    out.mkdir()
    for layer in ("geo_units", "samples"):
        (out / f"{layer}.pmtiles").write_bytes(b"antigo")
    res = export_web(_gpkg(tmp_path), out, tippecanoe=None)
    assert not (out / "geo_units.pmtiles").exists()
    assert not (out / "samples.pmtiles").exists()
    assert any("removid" in w and "geo_units.pmtiles" in w for w in res.warnings)


def test_tippecanoe_command_built_without_shell(tmp_path):
    out = tmp_path / "web"
    run = FakeRunner()
    res = export_web(_gpkg(tmp_path), out, tippecanoe="/opt/bin/tippecanoe", run=run)
    assert len(run.calls) == 2
    for (cmd, kwargs), layer in zip(run.calls, ["geo_units", "samples"]):
        assert cmd[:7] == [
            "/opt/bin/tippecanoe", "-o", str(out / f"{layer}.pmtiles"),
            "-zg", "--drop-densest-as-needed", "-l", layer,
        ]
        assert len(cmd) == 8 and cmd[7].endswith(".geojson")
        assert kwargs.get("shell", False) is False
        assert kwargs["check"] is True and kwargs["capture_output"] is True
    assert out / "geo_units.pmtiles" in res.files
    assert out / "samples.pmtiles" in res.files
    assert res.warnings == []


def test_tippecanoe_input_is_the_layer_as_geojson(tmp_path):
    seen = {}

    def run(cmd, **kwargs):
        seen[cmd[cmd.index("-l") + 1]] = _read(Path(cmd[-1]))
        Path(cmd[cmd.index("-o") + 1]).write_bytes(b"")
        return subprocess.CompletedProcess(cmd, 0)

    export_web(_gpkg(tmp_path), tmp_path / "web", tippecanoe="tippecanoe", run=run)
    assert seen["samples"]["features"][0]["properties"]["id"] == "s1"
    assert seen["geo_units"]["features"][0]["properties"]["unit_id"] == "u1"


def test_samples_tiles_carry_unit_lith_class(tmp_path):
    g = tmp_path / "geoworld.gpkg"
    create_geopackage(g)
    write_layer(g, "geo_units", gpd.GeoDataFrame(
        {"unit_id": ["u1", "u2"], "lith_class": ["granite", None], "source_id": ["glim"] * 2},
        geometry=[box(0, 0, 1, 1), box(2, 0, 3, 1)], crs=CRS,
    ))
    write_layer(g, "samples", gpd.GeoDataFrame(
        {"id": ["s1", "s2", "s3", "s4"], "unit_id": ["u1", None, "u2", "u9"],
         "source_id": ["s"] * 4},
        geometry=[Point(0.5, 0.5), Point(9, 9), Point(2.5, 0.5), Point(8, 8)], crs=CRS,
    ))
    seen = {}

    def run(cmd, **kwargs):
        seen[cmd[cmd.index("-l") + 1]] = _read(Path(cmd[-1]))
        Path(cmd[cmd.index("-o") + 1]).write_bytes(b"")
        return subprocess.CompletedProcess(cmd, 0)

    export_web(g, tmp_path / "web", tippecanoe="tippecanoe", run=run)
    props = {f["properties"]["id"]: f["properties"] for f in seen["samples"]["features"]}
    assert props["s1"]["unit_lith_class"] == "granite"
    assert props["s2"]["unit_lith_class"] is None   # unit_id nulo
    assert props["s3"]["unit_lith_class"] is None   # lith_class nulo
    assert props["s4"]["unit_lith_class"] is None   # unidade inexistente
    assert "unit_lith_class" not in seen["geo_units"]["features"][0]["properties"]
    # o gpkg nao muda
    assert "unit_lith_class" not in read_dataframe(g, layer="samples").columns


def test_empty_pmtiles_layer_is_skipped_with_warning(tmp_path):
    run = FakeRunner()
    res = export_web(_gpkg(tmp_path, with_samples=False), tmp_path / "web",
                     tippecanoe="tippecanoe", run=run)
    assert [c[0][c[0].index("-l") + 1] for c in run.calls] == ["geo_units"]
    assert any("samples" in w for w in res.warnings)


def test_export_warns_when_file_over_95mb(tmp_path, monkeypatch):
    out = tmp_path / "web"
    real = export.file_size
    big = out / "volcanoes.geojson"
    monkeypatch.setattr(
        export, "file_size", lambda p: 96 * 1024 * 1024 if p == big else real(p),
    )
    res = export_web(_gpkg(tmp_path), out, tippecanoe=None)
    over = [w for w in res.warnings if "95 MB" in w]
    assert len(over) == 1 and "volcanoes.geojson" in over[0]


def test_export_does_not_warn_at_exactly_95mb(tmp_path, monkeypatch):
    monkeypatch.setattr(export, "file_size", lambda p: 95 * 1024 * 1024)
    res = export_web(_gpkg(tmp_path), tmp_path / "web", tippecanoe=None)
    assert not [w for w in res.warnings if "95 MB" in w]


@pytest.mark.skipif(shutil.which("tippecanoe") is None, reason="tippecanoe nao instalado")
def test_real_tippecanoe_writes_pmtiles(tmp_path):
    out = tmp_path / "web"
    res = export_web(_gpkg(tmp_path), out, tippecanoe=shutil.which("tippecanoe"))
    assert (out / "geo_units.pmtiles").stat().st_size > 0
    assert (out / "samples.pmtiles").stat().st_size > 0
    assert res.warnings == []
