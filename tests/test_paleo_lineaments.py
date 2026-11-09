import json

import pytest

from pipeline import paleo_lineaments as pl
from pipeline import paleo_samples as ps

GOOD = {
    "type": "Feature",
    "properties": {"name": "Linha de teste", "source": "https://exemplo.org/fonte"},
    "geometry": {"type": "LineString", "coordinates": [[-48.0, -27.0], [-40.0, -20.0]]},
}


def test_validate_accepts_good_feature():
    assert pl.validate(GOOD) is None


def test_validate_requires_source_and_name_and_line():
    no_src = {**GOOD, "properties": {"name": "x"}}
    assert "fonte" in pl.validate(no_src)
    no_name = {**GOOD, "properties": {"source": "s"}}
    assert "name" in pl.validate(no_name)
    point = {**GOOD, "geometry": {"type": "Point", "coordinates": [0, 0]}}
    assert pl.validate(point) is not None
    bad = {**GOOD, "geometry": {"type": "LineString", "coordinates": [[200, 0], [10, 0]]}}
    assert "fora" in pl.validate(bad)


def test_load_rejects_and_reports(tmp_path):
    (tmp_path / "a.geojson").write_text(json.dumps({
        "type": "FeatureCollection",
        "features": [GOOD, {**GOOD, "properties": {"name": "sem fonte"}}],
    }), encoding="utf-8")
    feats, rejected = pl.load(tmp_path)
    assert len(feats) == 1 and len(rejected) == 1


def test_age_from_bounds_range_single_and_text():
    r = ps.age_from_bounds("130000000 [12]", "136000000 [12]")
    assert r["age_ma"] == 133 and r["age_unc_ma"] == 3 and r["age_basis"] == "range"
    s = ps.age_from_bounds("", "100000000")
    assert s["age_ma"] == 100 and s["age_unc_ma"] is None and s["age_basis"] == "single"
    assert ps.age_from_bounds("", "") is None
    assert ps.age_from_bounds("CRETACEOUS", "") is None


def test_usable_and_frame_age():
    assert ps.usable({"age_ma": 134, "age_unc_ma": 2})
    assert not ps.usable({"age_ma": 200, "age_unc_ma": 1})
    assert not ps.usable({"age_ma": 100, "age_unc_ma": 20})
    assert ps.frame_age(134.0) == 135 and ps.frame_age(2.0) == 0 and ps.frame_age(147.4) == 145


def test_build_rotates_with_the_model(tmp_path):
    pytest.importorskip("pygplates")
    from pipeline import paleo

    if not paleo.ROT.exists():
        pytest.skip("modelo de placas nao baixado")
    (tmp_path / "in").mkdir()
    (tmp_path / "in" / "a.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": [GOOD]}), encoding="utf-8")
    out = tmp_path / "out"
    stats = pl.build(tmp_path / "in", out, max_ma=100, step=50)
    assert stats["lineamentos"] == 1
    at0 = json.loads((out / "lineaments_0.geojson").read_text(encoding="utf-8"))["features"][0]
    at100 = json.loads((out / "lineaments_100.geojson").read_text(encoding="utf-8"))["features"][0]
    assert at0["geometry"]["coordinates"][0][0] == [-48.0, -27.0]  # idade 0: sem mudanca
    assert at100["geometry"]["coordinates"][0][0] != [-48.0, -27.0]  # girou
