import json

import numpy as np
import pytest
from shapely.geometry import box

from pipeline import rift3d


class _Rot:
    def __init__(self, lat, lon, ang):
        self.v = (lat, lon, ang)

    def represents_identity_rotation(self):
        return self.v[2] == 0

    def get_lat_lon_euler_pole_and_angle_degrees(self):
        return self.v


class FakeModel:
    """get_rotation(age, plate, from_time, fixed_plate_id): identidade em 0 Ma e na placa fixa."""

    def get_rotation(self, age, plate, from_time=0.0, fixed_plate_id=0):
        if age == 0 or plate == fixed_plate_id:
            return _Rot(0.0, 0.0, 0.0)
        return _Rot(45.0, -30.0, float(age) / 2)


def test_rotation_table_fixed_plate_is_identity_and_has_all_ages():
    t = rift3d.rotation_table(FakeModel(), [701, 201], 701, [0, 5, 10])
    assert [r["age"] for r in t["201"]] == [0, 5, 10]
    assert all(r["angle_deg"] == 0.0 for r in t["701"])
    assert t["201"][0]["angle_deg"] == 0.0  # 0 Ma e identidade
    assert t["201"][2] == {"age": 10, "pole_lat": 45.0, "pole_lon": -30.0, "angle_deg": 5.0}


def test_rotation_table_relative_matches_absolute_composition():
    from pipeline import paleo

    if not paleo.ROT.exists():
        pytest.skip("modelo Merdith nao baixado")
    import pygplates as g

    rm = g.RotationModel(str(paleo.ROT))
    t = rift3d.rotation_table(rm, [201, 701], 701, [120])
    pole = t["201"][0]
    rel = g.FiniteRotation((pole["pole_lat"], pole["pole_lon"]), np.radians(pole["angle_deg"]))
    expect = rm.get_rotation(120.0, 701).get_inverse() * rm.get_rotation(120.0, 201)
    probe = g.PointOnSphere(-30.0, -50.0)
    a = (rel * probe).to_lat_lon()
    b = (expect * probe).to_lat_lon()
    assert abs(a[0] - b[0]) < 1e-4 and abs(a[1] - b[1]) < 1e-4
    assert t["701"][0]["angle_deg"] == 0.0


def test_build_writes_consistent_files(tmp_path, monkeypatch):
    monkeypatch.setattr(rift3d, "fetch_mosaic",
                        lambda z, x0, x1, y0, y1, cache_dir: np.zeros(((y1 - y0 + 1) * 256, (x1 - x0 + 1) * 256), np.float32))
    monkeypatch.setattr(rift3d, "static_polygons_in_bbox",
                        lambda: [(201, box(-60, -40, -30, -20)), (701, box(5, -40, 35, -20))])
    paleo_dir = tmp_path / "paleo"
    paleo_dir.mkdir()
    (paleo_dir / "lineaments_0.geojson").write_text(json.dumps(
        {"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {"plate_id": 555}, "geometry": None}]}))
    rift3d.build(out_dir=tmp_path / "out", cache_dir=tmp_path / "c", rm=FakeModel(), paleo_dir=paleo_dir)
    out = tmp_path / "out"
    g = json.loads((out / "grid.json").read_text())
    assert (out / "grid.bin").stat().st_size == g["width"] * g["height"] * 6  # int16 + uint32 por celula
    assert g["fixed_plate"] == 701 and set(g["plates"]) == {201, 701}
    assert g["plates_offset"] == g["width"] * g["height"] * 2
    rot = json.loads((out / "rotations.json").read_text())
    assert set(rot) == {"201", "701", "555"}  # inclui a placa de uma feicao fora da grade
    assert "Merdith" in json.loads((out / "index.json").read_text())["model"]["citation"]
