"""Contrato pipeline -> web (web/js/contract.json).

Roda `build()` com fontes sinteticas INJETADAS nas quatro camadas (usando os
normalizadores reais) e um `run` falso no lugar do tippecanoe que captura os
GeoJSON de entrada. As propriedades exportadas (GeoJSON, entradas do
tippecanoe e sources.json) tem que ser exatamente as do contrato, com o tipo
JSON do contrato (nulo permitido). Uma coluna renomeada falha aqui.
"""
import json
import subprocess
from pathlib import Path

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import LineString, box

from pipeline import build as build_mod
from pipeline.build import Source, build
from pipeline.common.model import CRS
from pipeline.glim import normalize_glim
from pipeline.gvp import load_hotspots, normalize_gvp
from pipeline.rockmap import load_mapping
from pipeline.samples import normalize_samples
from pipeline.tectonics import rank_zones

ROOT = Path(__file__).resolve().parents[1]
_RAW = json.loads((ROOT / "web" / "js" / "contract.json").read_text(encoding="utf-8"))
# camadas externas (tiles de terceiros, ex.: macrostrat) nao saem do pipeline: ficam fora
EXTERNAL = set(_RAW.get("$external", []))
CONTRACT = {k: v for k, v in _RAW.items() if k not in EXTERNAL and not k.startswith("$")}
LAYERS = ("volcanoes", "tectonic_zones", "geo_units", "samples")


def _meta(name, scale=None):
    return {"institution": f"Instituto {name}", "source_url": f"https://example.org/{name}",
            "license": "CC-BY-4.0", "attribution": f"Autores {name}",
            "acquisition_date": "2026-11-03", "original_scale": scale}


def _read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_gvp(path, **_):
    return normalize_gvp(pd.read_csv(path, dtype=str), "gvp")


def load_hot(path, **_):
    return load_hotspots(path, "hotspots")


def load_units(path, **_):
    rows = _read_json(path)
    raw = gpd.GeoDataFrame({"xx": [r["xx"] for r in rows]},
                           geometry=[box(*r["bbox"]) for r in rows], crs=CRS)
    return normalize_glim(raw, "glim")


def load_zones(path, **_):
    data = _read_json(path)
    bounds = gpd.GeoDataFrame({"name": [b["name"] for b in data["boundaries"]]},
                              geometry=[LineString(b["line"]) for b in data["boundaries"]],
                              crs=CRS)
    quakes = pd.DataFrame(data["quakes"], columns=["lat", "lon", "mw", "time"])
    return rank_zones(bounds, quakes, "usgs")


MAPPING = load_mapping(ROOT / "data" / "curated" / "rock_mapping_v1.csv")
COLMAP = {"sid": "id", "rock": "rock_name", "lat": "lat", "lon": "lon"}


def make_sample_loader(source_id, uncertainty=None):
    def load(path, **_):
        located = normalize_samples(pd.DataFrame(_read_json(path)), source_id, COLMAP,
                                    MAPPING).located
        if uncertainty is not None:  # como uma linha geocodificada
            located.loc[0, "coord_source"] = "geocoded"
            located.loc[0, "coord_uncertainty_m"] = uncertainty
        return located
    return load


def _write(raw, name, data):
    raw.mkdir(parents=True, exist_ok=True)
    (raw / name).write_text(json.dumps(data), encoding="utf-8")


@pytest.fixture
def exported(tmp_path, monkeypatch):
    raw, out = tmp_path / "raw", tmp_path / "out"
    raw.mkdir()
    (raw / "gvp.csv").write_bytes((ROOT / "tests" / "fixtures" / "gvp_sample.csv").read_bytes())
    (raw / "hotspots.csv").write_text(
        "name,lon,lat,reference\nHotspot Sintetico,-155.0,19.0,Referencia sintetica 2026\n",
        encoding="utf-8")
    _write(raw, "units.json", [{"xx": "vb", "bbox": [0, 0, 2, 2]},
                               {"xx": "pb", "bbox": [5, 5, 6, 6]}])
    _write(raw, "zones.json", {
        "boundaries": [{"name": "Zona A", "line": [[30, -1], [30, 1]]},
                       {"name": "Zona B", "line": [[50, -1], [50, 1]]}],
        "quakes": [[0.0, 30.1, 9.0, "2000-01-01"], [0.0, 50.1, 7.0, "2010-06-30"]],
    })
    _write(raw, "a.json", [{"sid": "a1", "rock": "basalto", "lat": 1.0, "lon": 1.0},
                           {"sid": "a2", "rock": "basalto", "lat": 40.0, "lon": 40.0}])
    _write(raw, "b.json", [{"sid": "b1", "rock": "basalto", "lat": 1.0, "lon": 1.0}])
    sources = [
        Source("gvp", "gvp.csv", "volcanoes", load_gvp, meta=_meta("gvp")),
        Source("hotspots", "hotspots.csv", "volcanoes", load_hot, meta=_meta("hotspots")),
        Source("glim", "units.json", "geo_units", load_units, meta=_meta("glim", "1:3.750.000")),
        Source("usgs", "zones.json", "tectonic_zones", load_zones, meta=_meta("usgs")),
        Source("src_a", "a.json", "samples", make_sample_loader("src_a", 250.0),
               meta=_meta("src_a")),
        Source("src_b", "b.json", "samples", make_sample_loader("src_b"), meta=_meta("src_b")),
    ]
    inputs = {}

    def run(cmd, **kwargs):
        if "--version" in cmd:
            return subprocess.CompletedProcess(cmd, 0, b"", b"tippecanoe v2.53.0\n")
        inputs[cmd[cmd.index("-l") + 1]] = _read_json(cmd[-1])
        Path(cmd[cmd.index("-o") + 1]).write_bytes(b"PMTiles")
        return subprocess.CompletedProcess(cmd, 0, b"", b"")

    real_export = build_mod.export_web
    monkeypatch.setattr(build_mod, "export_web",
                        lambda gpkg, out_dir, tippecanoe, **kw:
                        real_export(gpkg, out_dir, tippecanoe, run=run, **kw))
    rep = build(raw, out, sources, tippecanoe="tippecanoe")
    assert set(rep.statuses.values()) == {"processed"}
    features = {
        "volcanoes": _read_json(out / "volcanoes.geojson")["features"],
        "tectonic_zones": _read_json(out / "tectonic_zones.geojson")["features"],
        "geo_units": inputs["geo_units"]["features"],
        "samples": inputs["samples"]["features"],
    }
    return {
        "props": {layer: [f["properties"] for f in features[layer]] for layer in LAYERS},
        "sources": _read_json(out / "sources.json"),
    }


def _type_ok(value, kind):
    if value is None:
        return True
    if kind == "string":
        return isinstance(value, str)
    if kind == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if kind == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    raise AssertionError(f"tipo desconhecido no contrato: {kind}")


def _check(rows, contract, label):
    assert rows, f"{label}: nenhuma linha exportada"
    for row in rows:
        assert set(row) == set(contract), (
            f"{label}: propriedades {sorted(row)} != contrato {sorted(contract)}")
        for name, kind in contract.items():
            assert _type_ok(row[name], kind), f"{label}.{name}={row[name]!r} nao e {kind}"
    # cada propriedade aparece preenchida ao menos uma vez (o tipo foi exercitado)
    for name in contract:
        assert any(r[name] is not None for r in rows), f"{label}.{name} sempre nulo"


def test_contract_lists_all_web_layers():
    assert set(CONTRACT) == {*LAYERS, "sources"}
    assert EXTERNAL == {"macrostrat"} and EXTERNAL.isdisjoint(CONTRACT)


@pytest.mark.parametrize("layer", LAYERS)
def test_exported_layer_matches_contract(exported, layer):
    _check(exported["props"][layer], CONTRACT[layer], layer)


def test_sources_json_matches_contract(exported):
    _check(exported["sources"], CONTRACT["sources"], "sources")
    assert {s["source_id"] for s in exported["sources"]} == {
        "gvp", "hotspots", "glim", "usgs", "src_a", "src_b"}


def test_contract_check_detects_renamed_column():
    contract = CONTRACT["geo_units"]
    row = {k: None for k in contract} | {"unit_id": "u1"}
    renamed = {("lith" if k == "lith_class" else k): v for k, v in row.items()}
    with pytest.raises(AssertionError):
        _check([renamed], contract, "geo_units")
