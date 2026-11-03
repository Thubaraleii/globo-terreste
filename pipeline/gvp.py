"""Vulcoes (Smithsonian GVP) e lista curada de hotspots.

Nenhuma linha de hotspot e criada pelo codigo: so entram linhas do CSV
curado, e cada uma exige `reference`.
"""
from pathlib import Path

import geopandas as gpd
import pandas as pd

from pipeline.common.geom import to_wgs84
from pipeline.common.model import CRS, SCHEMAS

# PROVISORIO: cabecalhos modelados na exportacao Holocene do GVP; confirmar
# contra o arquivo real quando ele for inspecionado. original -> spec.
GVP_COLUMNS = {
    "Volcano Name": "name",
    "Country": "country",
    "Primary Volcano Type": "type",
    "Last Known Eruption": "last_eruption",
    "Latitude": "lat",
    "Longitude": "lon",
}

_COLS = SCHEMAS["volcanoes"]


def _blank_to_null(series: pd.Series) -> pd.Series:
    return series.astype("object").map(
        lambda v: None if pd.isna(v) or str(v).strip() == "" else v
    )


def _build(df: pd.DataFrame, kind: str, source_id: str) -> gpd.GeoDataFrame:
    """df tem name, lon, lat (numericos) e opcionais do esquema."""
    out = pd.DataFrame(index=df.index)
    for col in _COLS:
        if col == "geometry":
            continue
        out[col] = _blank_to_null(df[col]) if col in df.columns else pd.Series(
            [None] * len(df), index=df.index, dtype="object"
        )
    out["kind"] = kind
    out["source_id"] = source_id
    geom = gpd.points_from_xy(df["lon"].astype(float), df["lat"].astype(float))
    gdf = to_wgs84(gpd.GeoDataFrame(out, geometry=geom, crs=CRS))
    return gdf[_COLS].reset_index(drop=True)


def normalize_gvp(df: pd.DataFrame, source_id: str) -> gpd.GeoDataFrame:
    """Normaliza a lista GVP. Linhas sem coordenadas sao descartadas e a
    contagem fica em `gdf.attrs["dropped_no_coords"]`. Campos vazios ficam nulos."""
    renamed = df.rename(columns=GVP_COLUMNS)
    lon = pd.to_numeric(renamed["lon"], errors="coerce")
    lat = pd.to_numeric(renamed["lat"], errors="coerce")
    keep = lon.notna() & lat.notna()
    kept = renamed[keep].copy()
    kept["lon"], kept["lat"] = lon[keep], lat[keep]
    gdf = _build(kept, "volcano", source_id)
    gdf.attrs["dropped_no_coords"] = int((~keep).sum())
    return gdf


def load_hotspots(csv: Path, source_id: str) -> gpd.GeoDataFrame:
    """Carrega hotspots curados (name,lon,lat,reference). `reference` e
    obrigatoria em toda linha; CSV so com cabecalho devolve quadro vazio."""
    df = pd.read_csv(csv, dtype=str, keep_default_na=False)
    ref = df["reference"].str.strip()
    if (ref == "").any():
        raise ValueError(f"hotspots sem reference: {df.loc[ref == '', 'name'].tolist()}")
    df["lon"] = pd.to_numeric(df["lon"])
    df["lat"] = pd.to_numeric(df["lat"])
    return _build(df, "hotspot", source_id)
