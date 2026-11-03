"""Esquema canonico do GeoPackage (spec secao 5) e helpers de escrita.

Todas as camadas geometricas usam EPSG:4326 e a coluna `geometry`.
`sources` e uma tabela sem geometria. Tipos de geometria: samples e
volcanoes sao Point; geo_units e tectonic_zones aceitam tipos mistos
(Polygon/MultiPolygon; Line/MultiLine/Polygon), entao a camada e criada
com tipo "Unknown" (permissivo).
"""
from pathlib import Path

import geopandas as gpd
import pandas as pd
from pyogrio import write_dataframe

CRS = "EPSG:4326"

SCHEMAS: dict[str, list[str]] = {
    "sources": [
        "source_id", "institution", "source_url", "license",
        "attribution", "acquisition_date", "original_scale",
    ],
    "samples": [
        "id", "rock_name_original", "rock_class", "coord_source",
        "coord_uncertainty_m", "unit_id", "dup_group", "source_id", "geometry",
    ],
    "geo_units": ["unit_id", "lith_original", "lith_class", "source_id", "geometry"],
    "volcanoes": [
        "name", "kind", "type", "last_eruption", "country",
        "reference", "source_id", "geometry",
    ],
    "tectonic_zones": [
        "rank", "name", "moment_total", "period_start", "period_end",
        "source_id", "geometry",
    ],
}

# None = sem geometria; "Unknown" = tipo aberto.
GEOMETRY_TYPES: dict[str, str | None] = {
    "sources": None,
    "samples": "Point",
    "geo_units": "Unknown",
    "volcanoes": "Point",
    "tectonic_zones": "Unknown",
}

_NUMERIC = {
    "coord_uncertainty_m": "float64",
    "moment_total": "float64",
    "rank": "Int64",
}


def _empty_frame(name: str):
    cols = [c for c in SCHEMAS[name] if c != "geometry"]
    data = {c: pd.Series(dtype=_NUMERIC.get(c, "object")) for c in cols}
    if GEOMETRY_TYPES[name] is None:
        return pd.DataFrame(data)
    return gpd.GeoDataFrame(data, geometry=gpd.GeoSeries([], crs=CRS))


def create_geopackage(path: Path) -> None:
    """Cria (sobrescrevendo) o GeoPackage com as cinco camadas vazias."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    for name in SCHEMAS:
        write_dataframe(
            _empty_frame(name), path, layer=name, driver="GPKG",
            geometry_type=GEOMETRY_TYPES[name], append=path.exists(),
        )


def write_layer(gpkg: Path, name: str, gdf) -> None:
    """Acrescenta linhas a uma camada. Colunas ausentes viram nulo;
    coluna fora do esquema levanta ValueError."""
    if name not in SCHEMAS:
        raise ValueError(f"camada desconhecida: {name}")
    schema = SCHEMAS[name]
    unknown = [c for c in gdf.columns if c not in schema]
    if unknown:
        raise ValueError(f"colunas fora do esquema de {name}: {unknown}")
    df = gdf.copy()
    for col in schema:
        if col not in df.columns:
            df[col] = pd.Series([None] * len(df), index=df.index, dtype=_NUMERIC.get(col, "object"))
    df = df[schema]
    if GEOMETRY_TYPES[name] is not None:
        if gdf.crs is None:
            raise ValueError(f"{name}: CRS ausente; nao presumimos EPSG:4326")
        df = gpd.GeoDataFrame(df, geometry="geometry", crs=gdf.crs)
        if df.crs != CRS:
            df = df.to_crs(CRS)
    write_dataframe(
        df, Path(gpkg), layer=name, driver="GPKG",
        geometry_type=GEOMETRY_TYPES[name], append=True,
    )
