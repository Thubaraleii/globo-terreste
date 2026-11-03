"""Utilitarios de geometria: tudo sai do pipeline em WGS84."""
import geopandas as gpd
import shapely

CRS = "EPSG:4326"


def to_wgs84(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Reprojeta para EPSG:4326. CRS ausente e erro, nunca presumido."""
    if gdf.crs is None:
        raise ValueError("CRS ausente; nao presumimos EPSG:4326")
    return gdf.to_crs(CRS)


def repair_geometries(gdf: gpd.GeoDataFrame) -> tuple[gpd.GeoDataFrame, int]:
    """Corrige geometrias invalidas com make_valid e descarta as vazias.

    Devolve (gdf, quantas geometrias invalidas foram reparadas).
    """
    geoms = gdf.geometry
    invalid = ~geoms.is_valid & ~geoms.is_empty & ~geoms.isna()
    out = gdf.copy()
    out.geometry = shapely.make_valid(geoms.values)
    out = out[~(out.geometry.isna() | out.geometry.is_empty)]
    return out, int(invalid.sum())
