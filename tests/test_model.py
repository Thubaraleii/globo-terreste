import geopandas as gpd
import pandas as pd
import pyogrio
import pytest
from shapely.geometry import Point

from pipeline.common.model import SCHEMAS, create_geopackage, write_layer


def test_create_geopackage_has_all_layers(tmp_path):
    gpkg = tmp_path / "t.gpkg"
    create_geopackage(gpkg)
    layers = {name for name, _ in pyogrio.list_layers(gpkg)}
    assert layers == set(SCHEMAS)
    for name, cols in SCHEMAS.items():
        gdf = gpd.read_file(gpkg, layer=name)
        assert list(gdf.columns) == cols


def test_write_layer_fills_missing_columns_with_null(tmp_path):
    gpkg = tmp_path / "t.gpkg"
    create_geopackage(gpkg)
    gdf = gpd.GeoDataFrame(
        {"id": ["a"], "rock_name_original": ["basalt"]},
        geometry=[Point(1, 2)],
        crs="EPSG:4326",
    )
    write_layer(gpkg, "samples", gdf)
    out = gpd.read_file(gpkg, layer="samples")
    assert list(out.columns) == SCHEMAS["samples"]
    assert len(out) == 1
    assert out["rock_class"].isna().all()
    assert out["coord_uncertainty_m"].isna().all()


def test_write_layer_rejects_unknown_column(tmp_path):
    gpkg = tmp_path / "t.gpkg"
    create_geopackage(gpkg)
    gdf = gpd.GeoDataFrame({"id": ["a"], "bogus": [1]}, geometry=[Point(0, 0)], crs="EPSG:4326")
    with pytest.raises(ValueError):
        write_layer(gpkg, "samples", gdf)


def test_write_layer_requires_crs(tmp_path):
    gpkg = tmp_path / "t.gpkg"
    create_geopackage(gpkg)
    gdf = gpd.GeoDataFrame({"id": ["a"]}, geometry=[Point(0, 0)])
    with pytest.raises(ValueError):
        write_layer(gpkg, "samples", gdf)


def test_dup_group_is_text(tmp_path):
    gpkg = tmp_path / "t.gpkg"
    create_geopackage(gpkg)
    gdf = gpd.GeoDataFrame(
        {"id": ["a", "b"], "dup_group": ["ab12cd", None]},
        geometry=[Point(0, 0), Point(1, 1)],
        crs="EPSG:4326",
    )
    write_layer(gpkg, "samples", gdf)
    out = gpd.read_file(gpkg, layer="samples")
    assert out["dup_group"].tolist()[0] == "ab12cd"
    assert pd.isna(out["dup_group"].tolist()[1])
    info = pyogrio.read_info(gpkg, layer="samples")
    assert dict(zip(info["fields"], info["dtypes"]))["dup_group"] == "object"
