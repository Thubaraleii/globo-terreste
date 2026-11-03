import geopandas as gpd
import pytest
from shapely.geometry import Point, Polygon

from pipeline.common.geom import repair_geometries, to_wgs84


def test_to_wgs84_reprojects_from_utm():
    gdf = gpd.GeoDataFrame({"id": ["a"]}, geometry=[Point(500000, 0)], crs="EPSG:32633")
    out = to_wgs84(gdf)
    assert out.crs == "EPSG:4326"
    assert out.geometry.iloc[0].x == pytest.approx(15.0, abs=1e-6)
    assert out.geometry.iloc[0].y == pytest.approx(0.0, abs=1e-6)


def test_to_wgs84_requires_crs():
    gdf = gpd.GeoDataFrame({"id": ["a"]}, geometry=[Point(0, 0)])
    with pytest.raises(ValueError):
        to_wgs84(gdf)


def test_repair_fixes_bowtie_polygon():
    bowtie = Polygon([(0, 0), (2, 2), (2, 0), (0, 2)])
    ok = Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])
    gdf = gpd.GeoDataFrame({"id": ["bad", "ok"]}, geometry=[bowtie, ok], crs="EPSG:4326")
    out, repaired = repair_geometries(gdf)
    assert repaired == 1
    assert out.geometry.is_valid.all()
    assert len(out) == 2


def test_repair_drops_empty_geometries():
    ok = Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])
    gdf = gpd.GeoDataFrame(
        {"id": ["empty", "ok"]}, geometry=[Polygon(), ok], crs="EPSG:4326"
    )
    out, repaired = repair_geometries(gdf)
    assert repaired == 0
    assert out["id"].tolist() == ["ok"]
