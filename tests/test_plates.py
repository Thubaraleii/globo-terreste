"""Camadas `plate_boundaries` e `plate_labels` (PB2002) com arquivos SINTETICOS
no formato de boundaries.json / plates.json."""
import json

import pytest
from pyogrio import read_dataframe

from pipeline import realsources as rs
from pipeline.build import build
from pipeline.common.model import SCHEMAS


def _fc(features):
    return {"type": "FeatureCollection", "features": features}


def _seg(name, a, b, coords, typ=""):
    return {"type": "Feature", "geometry": {"type": "LineString", "coordinates": coords},
            "properties": {"LAYER": "plate boundary", "Name": name, "Source": "Fonte [2026]",
                           "PlateA": a, "PlateB": b, "Type": typ}}


def _plate(code, name, geom):
    return {"type": "Feature", "geometry": geom,
            "properties": {"LAYER": "plate", "Code": code, "PlateName": name}}


def _poly(w, s, e, n):
    return {"type": "Polygon", "coordinates": [[[w, s], [e, s], [e, n], [w, n], [w, s]]]}


@pytest.fixture
def raw(tmp_path):
    d = tmp_path / "raw" / "pb2002"
    d.mkdir(parents=True)
    (d / "boundaries.json").write_text(json.dumps(_fc([
        _seg("AA-BB", "AA", "BB", [[0, 0], [1, 1]], "subduction"),
        _seg("AA-BB", "AA", "BB", [[1, 1], [2, 1]]),            # mesmo par: NAO dissolve
        _seg("BB-ZZ", "BB", "ZZ", [[5, 5], [6, 6]]),            # ZZ sem nome
    ])), encoding="utf-8")
    (d / "plates.json").write_text(json.dumps(_fc([
        _plate("AA", "Placa Alfa", _poly(0, 0, 10, 10)),
        _plate("BB", "Placa Beta", _poly(20, 0, 30, 10)),
        # dividida no antimeridiano: metade leste grande, metade oeste pequena
        _plate("PA", "Pacifica", _poly(100, -40, 180, 40)),
        _plate("PA", "Pacifica", _poly(-180, -40, -170, 40)),
        # codigo repetido com nomes conflitantes
        _plate("XX", "Nome 1", _poly(40, 0, 41, 1)),
        _plate("XX", "Nome 2", _poly(42, 0, 43, 1)),
    ])), encoding="utf-8")
    return d.parent


def test_schemas_declare_plate_layers():
    assert SCHEMAS["plate_boundaries"] == [
        "name", "plate_a", "plate_b", "plate_a_name", "plate_b_name", "type",
        "source_id", "geometry"]
    assert SCHEMAS["plate_labels"] == ["code", "name", "source_id", "geometry"]


def test_load_plate_boundaries_keeps_every_segment_with_names(raw):
    out = rs.load_plate_boundaries(raw / "pb2002" / "boundaries.json")
    assert len(out) == 3  # sem dissolver
    first = out.iloc[0]
    assert (first["name"], first["plate_a"], first["plate_b"]) == ("AA-BB", "AA", "BB")
    assert (first["plate_a_name"], first["plate_b_name"]) == ("Placa Alfa", "Placa Beta")
    assert list(out["type"]) == ["subduction", None, None]  # '' vira nulo


def test_plate_name_falls_back_to_raw_code_never_invented(raw):
    out = rs.load_plate_boundaries(raw / "pb2002" / "boundaries.json")
    last = out.iloc[2]
    assert last["plate_b"] == "ZZ" and last["plate_b_name"] == "ZZ"   # codigo desconhecido
    # sem plates.json: tudo cai no codigo
    (raw / "pb2002" / "plates.json").unlink()
    out = rs.load_plate_boundaries(raw / "pb2002" / "boundaries.json")
    assert list(out["plate_a_name"]) == ["AA", "AA", "BB"]


def test_load_plate_labels_one_point_per_code(raw):
    out = rs.load_plate_labels(raw / "pb2002" / "plates.json")
    assert out["code"].is_unique
    assert set(out["code"]) == {"AA", "BB", "PA", "XX"}
    assert set(out.geometry.geom_type) == {"Point"}
    by = out.set_index("code")
    assert by.loc["AA", "name"] == "Placa Alfa"
    assert by.loc["XX", "name"] == "XX"  # nomes conflitantes: nao inventa, usa o codigo


def test_label_point_of_split_plate_uses_largest_part_inside_it(raw):
    out = rs.load_plate_labels(raw / "pb2002" / "plates.json").set_index("code")
    p = out.loc["PA"].geometry
    assert 100 < p.x < 180 and -40 < p.y < 40   # metade leste (maior), nao a oeste
    assert abs(p.x) < 180                         # nunca na borda do antimeridiano


def test_label_point_prefers_largest_polygon_of_multipolygon(tmp_path):
    f = tmp_path / "plates.json"
    multi = {"type": "MultiPolygon", "coordinates": [
        _poly(0, 0, 1, 1)["coordinates"], _poly(50, 0, 80, 30)["coordinates"]]}
    f.write_text(json.dumps(_fc([_plate("MP", "Multi", multi)])), encoding="utf-8")
    p = rs.load_plate_labels(f).iloc[0].geometry
    assert 50 < p.x < 80 and 0 < p.y < 30


def test_registry_has_pb2002_sources():
    by_id = {s.source_id: s for s in rs.registry()}
    b, p = by_id["pb2002"], by_id["pb2002_plates"]
    assert (b.layer, b.raw_file) == ("plate_boundaries", "pb2002/boundaries.json")
    assert (p.layer, p.raw_file) == ("plate_labels", "pb2002/plates.json")
    for s in (b, p):
        assert "Open Data Commons Attribution" in s.meta["license"]
        assert "10.1029/2001GC000252" in s.meta["attribution"]
        assert s.meta["acquisition_date"] == "2026-11-03"
        assert s.meta["original_scale"] is None


def test_build_writes_plate_geojson_and_provenance(raw, tmp_path):
    sources = [s for s in rs.registry() if s.source_id.startswith("pb2002")]
    out = tmp_path / "out"
    rep = build(raw, out, sources, tippecanoe=None)
    assert rep.counts["plate_boundaries"] == 3 and rep.counts["plate_labels"] == 4
    b = json.loads((out / "plate_boundaries.geojson").read_text(encoding="utf-8"))
    assert len(b["features"]) == 3
    assert set(b["features"][0]["properties"]) == set(SCHEMAS["plate_boundaries"]) - {"geometry"}
    assert {f["properties"]["source_id"] for f in b["features"]} == {"pb2002"}
    lab = json.loads((out / "plate_labels.geojson").read_text(encoding="utf-8"))
    assert {f["properties"]["code"] for f in lab["features"]} == {"AA", "BB", "PA", "XX"}
    srcs = {s["source_id"] for s in json.loads((out / "sources.json").read_text(encoding="utf-8"))}
    assert srcs == {"pb2002", "pb2002_plates"}
    assert read_dataframe(out / "geoworld.gpkg", layer="plate_labels").shape[0] == 4
    # segunda execucao: nada reprocessado
    rep2 = build(raw, out, sources, tippecanoe=None)
    assert set(rep2.statuses.values()) == {"skipped"}
