"""Vulcoes (Smithsonian GVP) e lista curada de hotspots.

Nenhuma linha de hotspot e criada pelo codigo: so entram linhas do CSV
curado, e cada uma exige `reference`.
"""
from pathlib import Path

import geopandas as gpd
import pandas as pd

from pipeline.common.geom import to_wgs84
from pipeline.common.model import CRS, SCHEMAS

# Propriedades do GeoJSON do WFS do GVP (camada
# GVP-VOTW:Smithsonian_VOTW_Holocene_Volcanoes), conferidas no arquivo baixado
# em 2026-11-03. original -> spec. `Last_Eruption_Year` e inteiro (negativo =
# antes da era comum) ou nulo; vira texto em `last_eruption` ("-8300").
GVP_COLUMNS = {
    "Volcano_Name": "name",
    "Country": "country",
    "Primary_Volcano_Type": "type",
    "Last_Eruption_Year": "last_eruption",
    "Latitude": "lat",
    "Longitude": "lon",
}

_COLS = SCHEMAS["volcanoes"]


def _blank_to_null(series: pd.Series) -> pd.Series:
    return series.astype("object").map(
        lambda v: None if pd.isna(v) or str(v).strip() == "" else v
    )


def _valid_coords(lon: pd.Series, lat: pd.Series) -> pd.Series:
    """True onde lon/lat sao finitos e dentro de +-180 / +-90 (NaN -> False)."""
    return lon.abs().le(180) & lat.abs().le(90)


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


def _year_text(v):
    """Ano como texto ("-8300"); inteiro guardado como float vira "1850", nao "1850.0"."""
    if v is None or (not isinstance(v, str) and pd.isna(v)):
        return None
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    if hasattr(v, "item"):  # escalares numpy
        v = v.item()
        if isinstance(v, float) and v.is_integer():
            v = int(v)
    return str(v)


def normalize_gvp(df: pd.DataFrame, source_id: str) -> gpd.GeoDataFrame:
    """Normaliza a lista GVP. Linhas sem coordenadas sao descartadas e a
    contagem fica em `gdf.attrs["dropped_no_coords"]`. Campos vazios ficam nulos."""
    renamed = df.rename(columns=GVP_COLUMNS)
    lon = pd.to_numeric(renamed["lon"], errors="coerce")
    lat = pd.to_numeric(renamed["lat"], errors="coerce")
    keep = _valid_coords(lon, lat)
    kept = renamed[keep].copy()
    kept["lon"], kept["lat"] = lon[keep], lat[keep]
    if "last_eruption" in kept.columns:
        kept["last_eruption"] = kept["last_eruption"].astype("object").map(_year_text)
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
    df["lon"] = pd.to_numeric(df["lon"], errors="coerce")
    df["lat"] = pd.to_numeric(df["lat"], errors="coerce")
    bad = ~_valid_coords(df["lon"], df["lat"])
    if bad.any():
        raise ValueError(
            f"hotspots com coordenadas invalidas: {df.loc[bad, 'name'].tolist()}"
        )
    return _build(df, "hotspot", source_id)
