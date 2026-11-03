"""Testes do orquestrador incremental com fontes INJETADAS (sinteticas)."""
import json

import geopandas as gpd
import pytest
from pyogrio import read_dataframe
from shapely.geometry import Point, box

from pipeline import build as build_mod
from pipeline.build import Source, build
from pipeline.common.model import CRS


def _write_raw(raw_dir, name, rows):
    raw_dir.mkdir(parents=True, exist_ok=True)
    (raw_dir / name).write_text(json.dumps(rows), encoding="utf-8")


class Loader:
    """Le um JSON sintetico [{..., "lon":, "lat":}] e conta as chamadas."""

    def __init__(self, layer):
        self.layer = layer
        self.calls = 0
        self.kwargs = []

    def __call__(self, path, **kwargs):
        self.calls += 1
        self.kwargs.append(kwargs)
        rows = json.loads(path.read_text(encoding="utf-8"))
        if self.layer == "geo_units":
            geoms = [box(*r.pop("bbox")) for r in rows]
        else:
            geoms = [Point(r.pop("lon"), r.pop("lat")) for r in rows]
        return gpd.GeoDataFrame(rows, geometry=geoms, crs=CRS)


def _volcano_source(raw_dir, rows=None):
    _write_raw(raw_dir, "gvp.json", rows or [{"name": "Etna", "lon": 15.0, "lat": 37.75}])
    return Source("gvp", "gvp.json", "volcanoes", Loader("volcanoes"),
                  meta={"institution": "Smithsonian", "license": "CC-BY"})


def test_build_writes_gpkg_sources_table_and_report(tmp_path):
    raw, out = tmp_path / "raw", tmp_path / "out"
    src = _volcano_source(raw)
    rep = build(raw, out, [src])
    assert rep.statuses == {"gvp": "processed"}
    assert rep.counts["volcanoes"] == 1 and rep.counts["samples"] == 0
    v = read_dataframe(out / "geoworld.gpkg", layer="volcanoes")
    assert list(v["name"]) == ["Etna"] and list(v["source_id"]) == ["gvp"]
    s = read_dataframe(out / "geoworld.gpkg", layer="sources")
    assert list(s["source_id"]) == ["gvp"]
    assert s["institution"].iloc[0] == "Smithsonian"
    assert s["license"].iloc[0] == "CC-BY"
    assert s["source_url"].isna().all() and s["original_scale"].isna().all()
    assert (out / "volcanoes.geojson").exists()
    assert any("tippecanoe" in w for w in rep.warnings)


def test_build_skips_source_whose_hash_is_unchanged(tmp_path):
    raw, out = tmp_path / "raw", tmp_path / "out"
    src = _volcano_source(raw)
    build(raw, out, [src])
    rep = build(raw, out, [src])
    assert src.load.calls == 1
    assert rep.statuses == {"gvp": "skipped"}
    # dados anteriores mantidos
    v = read_dataframe(out / "geoworld.gpkg", layer="volcanoes")
    assert list(v["name"]) == ["Etna"]
    assert rep.counts["volcanoes"] == 1


def test_build_reprocesses_source_when_hash_changes(tmp_path):
    raw, out = tmp_path / "raw", tmp_path / "out"
    src = _volcano_source(raw)
    build(raw, out, [src])
    _write_raw(raw, "gvp.json", [{"name": "Vesuvius", "lon": 14.43, "lat": 40.82}])
    rep = build(raw, out, [src])
    assert src.load.calls == 2
    assert rep.statuses == {"gvp": "processed"}
    v = read_dataframe(out / "geoworld.gpkg", layer="volcanoes")
    assert list(v["name"]) == ["Vesuvius"]
    state = json.loads((out / "build_state.json").read_text(encoding="utf-8"))
    assert set(state) == {"gvp"}


def test_build_reprocesses_when_cache_is_missing(tmp_path):
    raw, out = tmp_path / "raw", tmp_path / "out"
    src = _volcano_source(raw)
    build(raw, out, [src])
    for f in (out / "_cache").iterdir():
        f.unlink()
    rep = build(raw, out, [src])
    assert rep.statuses == {"gvp": "processed"} and src.load.calls == 2


def test_missing_raw_file_raises(tmp_path):
    src = Source("x", "nao_existe.json", "volcanoes", Loader("volcanoes"))
    with pytest.raises(FileNotFoundError, match="nao_existe.json"):
        build(tmp_path / "raw", tmp_path / "out", [src])


def test_post_steps_link_duplicates_and_units(tmp_path):
    raw, out = tmp_path / "raw", tmp_path / "out"
    _write_raw(raw, "units.json", [{"unit_id": "u1", "lith_class": "basalt", "bbox": [0, 0, 1, 1]}])
    _write_raw(raw, "a.json", [
        {"id": "a1", "rock_name_original": "Basalt", "lon": 0.5, "lat": 0.5},
        {"id": "a2", "rock_name_original": "Granite", "lon": 5.0, "lat": 5.0},
    ])
    _write_raw(raw, "b.json", [{"id": "b1", "rock_name_original": "basalt", "lon": 0.5, "lat": 0.5}])
    sources = [
        Source("glim", "units.json", "geo_units", Loader("geo_units")),
        Source("src_a", "a.json", "samples", Loader("samples")),
        Source("src_b", "b.json", "samples", Loader("samples")),
    ]
    rep = build(raw, out, sources)
    s = read_dataframe(out / "geoworld.gpkg", layer="samples").set_index("id")
    assert s.loc["a1", "dup_group"] is not None
    assert s.loc["a1", "dup_group"] == s.loc["b1", "dup_group"]
    assert s["dup_group"].isna()["a2"]
    assert s.loc["a1", "unit_id"] == "u1" and s.loc["b1", "unit_id"] == "u1"
    assert s["unit_id"].isna()["a2"]
    assert dict(s["source_id"]) == {"a1": "src_a", "a2": "src_a", "b1": "src_b"}
    assert rep.counts["samples"] == 3 and rep.counts["geo_units"] == 1


def test_empty_sample_source_is_assembled_cleanly(tmp_path):
    raw, out = tmp_path / "raw", tmp_path / "out"
    _write_raw(raw, "a.json", [{"id": "a1", "rock_name_original": "basalt", "lon": 0.5, "lat": 0.5}])
    _write_raw(raw, "e.json", [])
    sources = [
        Source("src_a", "a.json", "samples", Loader("samples")),
        Source("src_e", "e.json", "samples", Loader("samples")),
    ]
    rep = build(raw, out, sources)
    assert rep.counts["samples"] == 1
    s = read_dataframe(out / "geoworld.gpkg", layer="samples")
    assert s["unit_id"].isna().all() and s["dup_group"].isna().all()


def test_network_source_skipped_without_allow_network(tmp_path):
    raw, out = tmp_path / "raw", tmp_path / "out"
    _write_raw(raw, "geo.json", [{"id": "g1", "lon": 1.0, "lat": 1.0}])
    net = Source("geo", "geo.json", "samples", Loader("samples"), needs_network=True)
    rep = build(raw, out, [net])
    assert rep.statuses == {"geo": "skipped_network"}
    assert net.load.calls == 0
    assert rep.counts["samples"] == 0
    assert not json.loads((out / "build_state.json").read_text(encoding="utf-8"))


def test_network_flag_passed_only_to_network_sources(tmp_path):
    raw, out = tmp_path / "raw", tmp_path / "out"
    local = _volcano_source(raw)
    _write_raw(raw, "geo.json", [{"id": "g1", "lon": 1.0, "lat": 1.0}])
    net = Source("geo", "geo.json", "samples", Loader("samples"), needs_network=True)
    rep = build(raw, out, [local, net], allow_network=True)
    assert rep.statuses == {"gvp": "processed", "geo": "processed"}
    assert local.load.kwargs == [{}]
    assert net.load.kwargs == [{"allow_network": True}]
    assert rep.counts["samples"] == 1


def test_build_passes_tippecanoe_to_export(tmp_path, monkeypatch):
    seen = {}
    real = build_mod.export_web

    def fake(gpkg, out_dir, tippecanoe, **kw):
        seen["tippecanoe"] = tippecanoe
        return real(gpkg, out_dir, None)

    monkeypatch.setattr(build_mod, "export_web", fake)
    raw, out = tmp_path / "raw", tmp_path / "out"
    build(raw, out, [_volcano_source(raw)], tippecanoe="/x/tippecanoe")
    assert seen["tippecanoe"] == "/x/tippecanoe"


def test_default_registry_is_empty():
    assert build_mod.SOURCES == []


def test_cli_with_empty_registry_prints_message(tmp_path, capsys):
    code = build_mod.main(["--raw", str(tmp_path / "raw"), "--out", str(tmp_path / "out")])
    assert code == 0
    assert "nenhuma fonte" in capsys.readouterr().out.lower()
    assert not (tmp_path / "out" / "geoworld.gpkg").exists()
