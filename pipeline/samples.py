"""Normalizacao de amostras (GEOROC, PetDB/EarthChem, ...) para SCHEMAS["samples"].

`colmap` e fornecido por quem chama: liga colunas da fonte aos nomes
logicos `id, rock_name, lat, lon, locality, country` (os dois ultimos
opcionais). Nada e inferido: rocha sem mapeamento sai e e contada,
coordenada invalida sai e e contada, nome original e mantido como veio.
"""
from collections import Counter
from dataclasses import dataclass

import geopandas as gpd
import pandas as pd

from pipeline.common.geom import to_wgs84
from pipeline.common.model import CRS, SCHEMAS
from pipeline.rockmap import classify_rock, normalize_rock_name

EMPTY_NAME = "<vazio>"
PENDING_EXTRA = ["locality", "country"]
_COLS = SCHEMAS["samples"]


@dataclass
class NormalizeResult:
    located: gpd.GeoDataFrame
    pending: pd.DataFrame
    dropped_invalid: int
    unmapped: Counter


def is_blank(v) -> bool:
    return v is None or (not isinstance(v, str) and pd.isna(v)) or str(v).strip() == ""


def valid_coords(lat: pd.Series, lon: pd.Series) -> pd.Series:
    """Finitas, |lat|<=90, |lon|<=180 e nao exatamente (0,0). NaN -> False."""
    return lat.abs().le(90) & lon.abs().le(180) & ~(lat.eq(0) & lon.eq(0))


def _logical(df: pd.DataFrame, colmap: dict[str, str], name: str) -> pd.Series:
    for src, logical in colmap.items():
        if logical == name and src in df.columns:
            return df[src].astype("object")
    return pd.Series([None] * len(df), index=df.index, dtype="object")


def _text_or_null(series: pd.Series) -> pd.Series:
    values = [None if is_blank(v) else str(v).strip() for v in series]
    return pd.Series(values, index=series.index, dtype="object")


def _base_frame(df, ids, names, classes, source_id) -> pd.DataFrame:
    n = len(df)
    return pd.DataFrame({
        "id": ids,
        "rock_name_original": names,
        "rock_class": classes,
        "coord_source": pd.Series([None] * n, index=df.index, dtype="object"),
        "coord_uncertainty_m": pd.Series([float("nan")] * n, index=df.index, dtype="float64"),
        "unit_id": pd.Series([None] * n, index=df.index, dtype="object"),
        "dup_group": pd.Series([None] * n, index=df.index, dtype="object"),
        "source_id": pd.Series([source_id] * n, index=df.index, dtype="object"),
    }, index=df.index)


def normalize_samples(
    df: pd.DataFrame, source_id: str, colmap: dict[str, str], mapping: dict[str, str]
) -> NormalizeResult:
    """Separa amostras maficas/ultramaficas em localizadas e pendentes.

    - rocha sem classe no mapeamento: excluida, contada em `unmapped`
      (pelo nome normalizado, ou "<vazio>");
    - coordenadas validas: `located` (coord_source='reported', incerteza nula);
    - lat e lon ambas ausentes e `locality` preenchida: `pending`;
    - demais coordenadas invalidas: contadas em `dropped_invalid`.
    """
    raw_ids = _logical(df, colmap, "id")
    ids = pd.Series(
        [f"{source_id}:{i}" if is_blank(v) else str(v).strip() for i, v in enumerate(raw_ids)],
        index=df.index, dtype="object",
    )
    names = _logical(df, colmap, "rock_name")
    classes = names.map(lambda s: classify_rock(s, mapping)).astype("object")
    mapped = classes.notna()
    unmapped = Counter(
        normalize_rock_name(s) or EMPTY_NAME for s in names[~mapped]
    )

    raw_lat, raw_lon = _logical(df, colmap, "lat"), _logical(df, colmap, "lon")
    lat = pd.to_numeric(raw_lat.map(lambda v: None if is_blank(v) else v), errors="coerce")
    lon = pd.to_numeric(raw_lon.map(lambda v: None if is_blank(v) else v), errors="coerce")
    locality = _text_or_null(_logical(df, colmap, "locality"))
    country = _text_or_null(_logical(df, colmap, "country"))

    valid = valid_coords(lat, lon)
    no_coords = raw_lat.map(is_blank) & raw_lon.map(is_blank)
    to_pending = mapped & ~valid & no_coords & locality.notna()
    located_mask = mapped & valid
    dropped = int((mapped & ~valid & ~to_pending).sum())

    base = _base_frame(df, ids, names, classes, source_id)

    loc = base[located_mask].copy()
    loc["coord_source"] = "reported"
    geom = gpd.points_from_xy(lon[located_mask].astype(float), lat[located_mask].astype(float))
    located = to_wgs84(gpd.GeoDataFrame(loc, geometry=geom, crs=CRS))
    located = located[_COLS].reset_index(drop=True)

    pending = base[to_pending].copy()
    pending["locality"] = locality[to_pending]
    pending["country"] = country[to_pending]
    pending = pending.reset_index(drop=True)

    return NormalizeResult(located, pending, dropped, unmapped)
