import os
import subprocess
import sys

import geopandas as gpd
import pandas as pd

from pipeline.common.model import CRS
from pipeline.dedupe import assign_dup_groups


def _samples(rows):
    """rows: (id, rock, lon, lat, source_id); lon/lat None -> geometria nula."""
    geom = gpd.GeoSeries(
        [None if lon is None else gpd.points_from_xy([lon], [lat])[0] for _, _, lon, lat, _ in rows],
        crs=CRS,
    )
    df = pd.DataFrame({
        "id": [r[0] for r in rows],
        "rock_name_original": [r[1] for r in rows],
        "rock_class": ["mafic"] * len(rows),
        "coord_source": ["reported"] * len(rows),
        "coord_uncertainty_m": [float("nan")] * len(rows),
        "unit_id": pd.Series([None] * len(rows), dtype="object"),
        "dup_group": pd.Series(["old"] * len(rows), dtype="object"),
        "source_id": [r[4] for r in rows],
    })
    return gpd.GeoDataFrame(df, geometry=geom, crs=CRS)


def test_same_rock_same_place_two_sources_share_group():
    out = assign_dup_groups(_samples([
        ("a", "Basalt", 10.00001, 20.00001, "s1"),
        ("b", " basalt ", 10.00002, 20.00002, "s2"),
        ("c", "Basalt", 30.0, 40.0, "s1"),
    ]))
    assert out.loc[0, "dup_group"] == out.loc[1, "dup_group"]
    assert isinstance(out.loc[0, "dup_group"], str) and out.loc[0, "dup_group"]
    assert out.loc[2, "dup_group"] is None


def test_same_source_same_place_not_grouped():
    out = assign_dup_groups(_samples([
        ("a", "Basalt", 10.0, 20.0, "s1"),
        ("b", "Basalt", 10.0, 20.0, "s1"),
    ]))
    assert out["dup_group"].isna().all()


def test_different_rock_same_place_not_grouped():
    out = assign_dup_groups(_samples([
        ("a", "Basalt", 10.0, 20.0, "s1"),
        ("b", "Gabbro", 10.0, 20.0, "s2"),
    ]))
    assert out["dup_group"].isna().all()


def test_no_rows_removed():
    s = _samples([
        ("a", "Basalt", 10.0, 20.0, "s1"),
        ("b", "Basalt", 10.0, 20.0, "s2"),
        ("c", None, 10.0, 20.0, "s3"),
        ("d", "Basalt", None, None, "s3"),
    ])
    s.index = [7, 3, 5, 1]
    before = s.copy()
    out = assign_dup_groups(s)
    assert list(out.index) == [7, 3, 5, 1]
    assert list(out["id"]) == ["a", "b", "c", "d"]
    assert out.crs == s.crs
    assert out.loc[[5, 1], "dup_group"].isna().all()
    assert out.loc[7, "dup_group"] is not None
    assert out.loc[7, "dup_group"] == out.loc[3, "dup_group"]
    pd.testing.assert_frame_equal(s, before)  # entrada intacta
    assert list(out.columns) == list(s.columns)


def test_group_id_is_stable_across_runs():
    code = (
        "from tests.test_dedupe import _samples\n"
        "from pipeline.dedupe import assign_dup_groups\n"
        "o = assign_dup_groups(_samples([('a','Basalt',10.0,20.0,'s1'),('b','Basalt',10.0,20.0,'s2')]))\n"
        "print(o.loc[0,'dup_group'])\n"
    )
    runs = set()
    for seed in (1, 2, 3):
        env = {**os.environ, "PYTHONHASHSEED": str(seed)}
        res = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                             check=True, env=env)
        runs.add(res.stdout.strip())
    assert len(runs) == 1 and len(runs.pop()) == 12


def test_negative_zero_and_antimeridian_keys_are_consistent():
    out = assign_dup_groups(_samples([
        ("a", "Basalt", -0.00001, 5.0, "s1"),
        ("b", "Basalt", 0.00001, 5.0, "s2"),
        ("c", "Basalt", 179.99999, 5.0, "s1"),
        ("d", "Basalt", 180.0, 5.0, "s2"),
    ]))
    assert out.loc[0, "dup_group"] is not None
    assert out.loc[0, "dup_group"] == out.loc[1, "dup_group"]
    assert out.loc[2, "dup_group"] is not None
    assert out.loc[2, "dup_group"] == out.loc[3, "dup_group"]


def test_empty_frame():
    out = assign_dup_groups(_samples([]))
    assert len(out) == 0 and "dup_group" in out.columns
