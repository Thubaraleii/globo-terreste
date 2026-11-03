"""Geocodificacao de amostras pendentes (sem coordenada, com localidade).

O backend real (ex.: Nominatim) e plugado como `geocoder` pelo build e so
roda com autorizacao do usuario. Aqui: consulta, cache e descarte. Sem
resultado, resultado fora de faixa ou erro -> linha descartada, nunca
adivinhada.
"""
import json
from pathlib import Path
from typing import Callable

import geopandas as gpd
import pandas as pd

from pipeline.common.geom import to_wgs84
from pipeline.common.model import CRS, SCHEMAS
from pipeline.samples import is_blank, valid_coords

Geocoder = Callable[[str], tuple[float, float, float] | None]
_COLS = SCHEMAS["samples"]


def build_query(locality, country) -> str:
    """`"{locality}, {country}"`; sem pais, so a localidade."""
    loc = str(locality).strip()
    return loc if is_blank(country) else f"{loc}, {str(country).strip()}"


def _load_cache(cache: Path) -> dict:
    if cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))
    return {}


def _save_cache(cache: Path, data: dict) -> None:
    cache.parent.mkdir(parents=True, exist_ok=True)
    tmp = cache.with_name(cache.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
    tmp.replace(cache)


def geocode_pending(pending: pd.DataFrame, geocoder: Geocoder, cache: Path) -> gpd.GeoDataFrame:
    """Geocodifica `pending` (saida de normalize_samples).

    Cada consulta distinta chama o geocoder no maximo uma vez entre rodadas
    (resultados, inclusive None, ficam no JSON `cache`; erros nao sao
    cacheados e sao tentados de novo na proxima rodada, mas nao na mesma).
    Contagens de linhas descartadas em `gdf.attrs`: `dropped_no_result`
    (None ou fora de faixa) e `geocoder_errors` (excecao do geocoder).
    """
    cache = Path(cache)
    store = _load_cache(cache)
    failed: set[str] = set()
    keep, lats, lons, uncs = [], [], [], []
    dropped_no_result = errors = 0

    for idx, row in pending.iterrows():
        query = build_query(row["locality"], row.get("country"))
        if query in failed:
            errors += 1
            continue
        if query not in store:
            try:
                result = geocoder(query)
            except Exception:
                failed.add(query)
                errors += 1
                continue
            store[query] = None if result is None else [float(x) for x in result]
        result = store[query]
        if result is None:
            dropped_no_result += 1
            continue
        lat, lon, unc = result
        if not valid_coords(pd.Series([lat]), pd.Series([lon])).iloc[0]:
            dropped_no_result += 1
            continue
        keep.append(idx)
        lats.append(lat)
        lons.append(lon)
        uncs.append(unc)

    _save_cache(cache, store)

    out = pending.loc[keep, [c for c in _COLS if c != "geometry"]].copy()
    out["coord_source"] = pd.Series(["geocoded"] * len(out), index=out.index, dtype="object")
    out["coord_uncertainty_m"] = pd.Series(uncs, index=out.index, dtype="float64")
    gdf = gpd.GeoDataFrame(out, geometry=gpd.points_from_xy(lons, lats), crs=CRS)
    gdf = to_wgs84(gdf)[_COLS].reset_index(drop=True)
    gdf.attrs["dropped_no_result"] = dropped_no_result
    gdf.attrs["geocoder_errors"] = errors
    return gdf
