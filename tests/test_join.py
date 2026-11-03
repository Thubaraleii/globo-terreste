"""Testes de attach_units com dados SINTETICOS."""
import geopandas as gpd
import pytest
from shapely.geometry import Point, box

from pipeline.common.model import CRS
from pipeline.join import attach_units


def _units(ids, geoms, crs=CRS):
    return gpd.GeoDataFrame({"unit_id": ids}, geometry=geoms, crs=crs)


def _samples(points, crs=CRS, index=None):
    n = len(points)
    return gpd.GeoDataFrame(
        {
            "id": [f"s{i}" for i in range(n)],
            "rock_class": ["mafic"] * n,
            "unit_id": [None] * n,
        },
        geometry=points, crs=crs, index=index,
    )


def test_sample_inside_unit_gets_unit_id():
    units = _units(["u1", "u2"], [box(0, 0, 1, 1), box(2, 0, 3, 1)])
    samples = _samples([Point(2.5, 0.5), Point(0.5, 0.5)])
    out = attach_units(samples, units)
    assert list(out["unit_id"]) == ["u2", "u1"]


def test_sample_outside_all_units_gets_null():
    units = _units(["u1"], [box(0, 0, 1, 1)])
    out = attach_units(_samples([Point(5, 5), Point(0.5, 0.5)]), units)
    assert out["unit_id"].iloc[0] is None
    assert out["unit_id"].iloc[1] == "u1"


def test_sample_on_shared_boundary_gets_lowest_unit_id():
    # ordem de entrada invertida para provar que o desempate e por unit_id
    units = _units(["u9", "u10", "u2"], [box(1, 0, 2, 1), box(0, 1, 1, 2), box(0, 0, 1, 1)])
    samples = _samples([Point(1, 0.5), Point(1, 1)])
    first = attach_units(samples, units)
    again = attach_units(samples, units.iloc[::-1])
    # (1, 0.5): borda de u2 e u9 -> "u2"; (1, 1): canto de u2, u9, u10 -> "u10"
    assert list(first["unit_id"]) == ["u2", "u10"]
    assert list(again["unit_id"]) == list(first["unit_id"])


def test_overlapping_units_resolve_to_lowest_unit_id():
    units = _units(["b", "a"], [box(0, 0, 2, 2), box(1, 1, 3, 3)])
    out = attach_units(_samples([Point(1.5, 1.5), Point(0.5, 0.5)]), units)
    assert list(out["unit_id"]) == ["a", "b"]


def test_polygon_touching_antimeridian_matches_points_on_both_sides():
    units = _units(["east", "west"], [box(179, -10, 180, 10), box(-180, -10, -179, 10)])
    pts = [
        Point(179.5, 0), Point(-179.5, 0), Point(180, 5),
        Point(-180, -5), Point(0, 0),
    ]
    out = attach_units(_samples(pts), units)
    assert len(out) == len(pts)
    assert list(out["unit_id"]) == ["east", "west", "east", "west", None]


def test_preserves_rows_order_index_and_other_columns():
    units = _units(["u1"], [box(0, 0, 1, 1)])
    samples = _samples([Point(5, 5), Point(0.5, 0.5), Point(0.2, 0.2)], index=[7, 7, 3])
    before = samples.copy()
    out = attach_units(samples, units)
    assert out is not samples
    assert list(out.index) == [7, 7, 3]
    assert list(out.columns) == list(samples.columns)
    assert out.crs == samples.crs
    assert list(out["unit_id"]) == [None, "u1", "u1"]
    assert out.drop(columns="unit_id").equals(before.drop(columns="unit_id"))
    assert samples["unit_id"].isna().all()  # entrada intacta


def test_null_or_empty_sample_geometry_gets_null():
    units = _units(["u1"], [box(-1, -1, 1, 1)])
    out = attach_units(_samples([None, Point(), Point(0, 0)]), units)
    assert list(out["unit_id"]) == [None, None, "u1"]


def test_adds_unit_id_column_when_absent():
    units = _units(["u1"], [box(0, 0, 1, 1)])
    samples = _samples([Point(0.5, 0.5)]).drop(columns="unit_id")
    assert list(attach_units(samples, units)["unit_id"]) == ["u1"]


def test_empty_inputs():
    units = _units([], [])
    out = attach_units(_samples([Point(0.5, 0.5)]), units)
    assert out["unit_id"].iloc[0] is None
    empty = attach_units(_samples([]), _units(["u1"], [box(0, 0, 1, 1)]))
    assert len(empty) == 0


@pytest.mark.parametrize("s_crs,u_crs", [(None, CRS), (CRS, None), (CRS, "EPSG:3857")])
def test_crs_mismatch_or_missing_raises(s_crs, u_crs):
    units = _units(["u1"], [box(0, 0, 1, 1)], crs=u_crs)
    with pytest.raises(ValueError, match="CRS"):
        attach_units(_samples([Point(0.5, 0.5)], crs=s_crs), units)
