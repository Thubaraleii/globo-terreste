import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
from shapely.geometry import LineString

from pipeline.common.model import SCHEMAS
from pipeline.tectonics import rank_zones, seismic_moment

# 1 grau de latitude ~ 111.2 km; segmentos e sismos sinteticos no equador.


def _boundaries(rows):
    names, geoms = zip(*rows)
    return gpd.GeoDataFrame({"name": list(names)}, geometry=list(geoms), crs="EPSG:4326")


def _quakes(rows):
    return pd.DataFrame(rows, columns=["lat", "lon", "mw", "time"])


def test_seismic_moment_mw7():
    # 10 ** (1.5 * 7 + 9.1) = 10 ** 19.6
    assert seismic_moment(7.0) == pytest.approx(3.981e19, rel=1e-3)


def test_segment_with_two_m7_outranks_one_m7():
    b = _boundaries([
        ("A", LineString([(0, -1), (0, 1)])),
        ("B", LineString([(50, -1), (50, 1)])),
    ])
    q = _quakes([
        (0.0, 50.1, 7.0, "2001-01-01"),
        (0.0, 0.1, 7.0, "2000-01-01"),
        (0.5, -0.1, 7.0, "2010-01-01"),
    ])
    out = rank_zones(b, q, "usgs-pb2002")
    assert list(out.columns) == SCHEMAS["tectonic_zones"]
    assert out.crs == "EPSG:4326"
    assert list(out["name"]) == ["A", "B"]
    assert list(out["rank"]) == [1, 2]
    assert out["moment_total"].iloc[0] == pytest.approx(2 * seismic_moment(7.0))
    assert out["moment_total"].iloc[1] == pytest.approx(seismic_moment(7.0))
    assert (out["period_start"] == "2000-01-01").all()
    assert (out["period_end"] == "2010-01-01").all()
    assert (out["source_id"] == "usgs-pb2002").all()
    assert out.geometry.iloc[0].equals(b.geometry.iloc[0])


def test_quake_beyond_buffer_ignored():
    b = _boundaries([("A", LineString([(0, -1), (0, 1)]))])
    # ~1.5 grau (~167 km) a leste: fora de 100 km; ~0.5 grau (~56 km): dentro.
    q = _quakes([(0.0, 1.5, 8.0, "2000"), (0.0, 0.5, 6.0, "2001")])
    out = rank_zones(b, q, "src", buffer_km=100)
    assert out["moment_total"].iloc[0] == pytest.approx(seismic_moment(6.0))
    # sem nenhum sismo dentro do buffer, o segmento nao e ranqueado
    assert len(rank_zones(b, q.iloc[:1], "src", buffer_km=100)) == 0


def test_each_quake_counted_for_nearest_segment_only():
    b = _boundaries([
        ("A", LineString([(0, -1), (0, 1)])),
        ("B", LineString([(1, -1), (1, 1)])),
    ])
    # a 0.3 grau de A e 0.7 grau de B: ambos dentro de 100 km, conta so para A
    q = _quakes([(0.0, 0.3, 7.0, "2000"), (0.0, 0.8, 5.0, "2000")])
    out = rank_zones(b, q, "src", buffer_km=100).set_index("name")
    assert out.loc["A", "moment_total"] == pytest.approx(seismic_moment(7.0))
    assert out.loc["B", "moment_total"] == pytest.approx(seismic_moment(5.0))
    total = out["moment_total"].sum()
    assert total == pytest.approx(seismic_moment(7.0) + seismic_moment(5.0))


def test_top_n_limits_output_and_ranks_from_1():
    rows, quakes = [], []
    for i in range(5):
        lon = i * 10
        rows.append((f"Z{i}", LineString([(lon, -1), (lon, 1)])))
        quakes.append((0.0, lon + 0.1, 5.0 + i, "2000"))
    out = rank_zones(_boundaries(rows), _quakes(quakes), "src", top_n=3)
    assert list(out["rank"]) == [1, 2, 3]
    assert list(out["name"]) == ["Z4", "Z3", "Z2"]


def test_quake_near_antimeridian_assigned_to_segment_across_180():
    b = _boundaries([
        ("Leste", LineString([(179.9, -1), (179.9, 1)])),
        ("Longe", LineString([(178.0, -1), (178.0, 1)])),
    ])
    # lon -179.9 fica a 0.2 grau (~22 km) de 179.9 pelo antimeridiano
    q = _quakes([(0.0, -179.9, 7.0, "2000")])
    out = rank_zones(b, q, "src", buffer_km=50)
    assert list(out["name"]) == ["Leste"]
    assert out["moment_total"].iloc[0] == pytest.approx(seismic_moment(7.0))


def test_ties_break_by_name_and_invalid_quakes_excluded():
    b = _boundaries([
        ("Beta", LineString([(10, -1), (10, 1)])),
        ("Alfa", LineString([(0, -1), (0, 1)])),
    ])
    q = _quakes([
        (0.0, 10.1, 6.0, "2005"),
        (0.0, 0.1, 6.0, "2003"),
        (np.nan, 0.1, 9.0, "1990"),
        (95.0, 0.1, 9.0, "1991"),
        (0.0, 200.0, 9.0, "1992"),
        (0.0, 0.1, np.nan, "1993"),
    ])
    out = rank_zones(b, q, "src")
    assert list(out["name"]) == ["Alfa", "Beta"]
    assert list(out["rank"]) == [1, 2]
    assert (out["period_start"] == "2003").all()
    assert (out["period_end"] == "2005").all()


def test_rank_zones_requires_crs():
    b = gpd.GeoDataFrame({"name": ["A"]}, geometry=[LineString([(0, 0), (0, 1)])])
    with pytest.raises(ValueError):
        rank_zones(b, _quakes([(0.0, 0.0, 6.0, "2000")]), "src")


def test_assignment_stats_in_attrs():
    b = _boundaries([("A", LineString([(0, -1), (0, 1)]))])
    q = _quakes([(0.0, 0.5, 6.0, "2000"), (0.0, 1.5, 7.0, "2001"), (0.0, 40.0, 7.0, "2002")])
    out = rank_zones(b, q, "src", buffer_km=100)
    assert out.attrs["quakes_assigned"] == 1
    assert out.attrs["quakes_unassigned"] == 2
    expected = 100 * seismic_moment(6.0) / (seismic_moment(6.0) + 2 * seismic_moment(7.0))
    assert out.attrs["moment_assigned_pct"] == pytest.approx(expected)
    assert out.attrs["buffer_km"] == 100


def test_default_buffer_is_250_km_for_megathrusts():
    from pipeline.tectonics import DEFAULT_BUFFER_KM
    assert DEFAULT_BUFFER_KM == 250
    b = _boundaries([("A", LineString([(0, -1), (0, 1)]))])
    q = _quakes([(0.0, 2.0, 8.0, "2000")])  # ~222 km: fora de 100 km, dentro de 250 km
    assert len(rank_zones(b, q, "src")) == 1
    assert len(rank_zones(b, q, "src", buffer_km=100)) == 0
