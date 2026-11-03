"""Geocodificacao de amostras pendentes (sem coordenada, com localidade).

O backend real (ex.: Nominatim) e plugado como `geocoder` pelo build e so
roda com autorizacao do usuario. Aqui: consulta, cache e descarte. Sem
resultado, resultado fora de faixa ou erro -> linha descartada, nunca
adivinhada.
"""
import json
import math
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


def _parse(result) -> list[float]:
    """`(lat, lon, uncertainty_m)` como 3 floats; formato invalido levanta."""
    if isinstance(result, (str, bytes)) or len(result) != 3:
        raise ValueError(f"resultado malformado: {result!r}")
    return [float(x) for x in result]


def _usable(lat: float, lon: float, unc: float) -> bool:
    """Coordenada valida e incerteza finita e >= 0."""
    ok_coords = valid_coords(pd.Series([lat]), pd.Series([lon])).iloc[0]
    return bool(ok_coords) and math.isfinite(unc) and unc >= 0


def geocode_pending(pending: pd.DataFrame, geocoder: Geocoder, cache: Path) -> gpd.GeoDataFrame:
    """Geocodifica `pending` (saida de normalize_samples).

    Cada consulta distinta chama o geocoder no maximo uma vez entre rodadas:
    resultados utilizaveis ficam no JSON `cache` como `[lat, lon, unc]`;
    None e resultados bem formados mas inutilizaveis (fora de faixa,
    incerteza NaN/inf/negativa) ficam como `null`. Excecoes e resultados
    malformados (nao sao 3 numeros) nao sao cacheados: sao tentados de novo
    na proxima rodada, mas nao na mesma. O cache e salvo mesmo se a rodada
    for interrompida (a excecao e relancada).

    Contagens de linhas descartadas em `gdf.attrs`:
    - `dropped_no_result`: None ou resultado inutilizavel;
    - `geocoder_errors`: excecao do geocoder, resultado ou entrada de cache
      malformados.
    """
    cache = Path(cache)
    store = _load_cache(cache)
    failed: set[str] = set()
    keep, lats, lons, uncs = [], [], [], []
    dropped_no_result = errors = 0

    try:
        for idx, row in pending.iterrows():
            query = build_query(row["locality"], row.get("country"))
            if query in failed:
                errors += 1
                continue
            if query not in store:
                try:
                    result = geocoder(query)
                    parsed = None if result is None else _parse(result)
                except Exception:
                    failed.add(query)
                    errors += 1
                    continue
                store[query] = parsed if parsed is not None and _usable(*parsed) else None
            entry = store[query]
            if entry is None:
                dropped_no_result += 1
                continue
            try:
                lat, lon, unc = _parse(entry)
            except (TypeError, ValueError):
                errors += 1
                continue
            if not _usable(lat, lon, unc):
                dropped_no_result += 1
                continue
            keep.append(idx)
            lats.append(lat)
            lons.append(lon)
            uncs.append(unc)
    finally:
        _save_cache(cache, store)

    out = pending.loc[keep, [c for c in _COLS if c != "geometry"]].copy()
    out["coord_source"] = pd.Series(["geocoded"] * len(out), index=out.index, dtype="object")
    out["coord_uncertainty_m"] = pd.Series(uncs, index=out.index, dtype="float64")
    gdf = gpd.GeoDataFrame(out, geometry=gpd.points_from_xy(lons, lats), crs=CRS)
    gdf = to_wgs84(gdf)[_COLS].reset_index(drop=True)
    gdf.attrs["dropped_no_result"] = dropped_no_result
    gdf.attrs["geocoder_errors"] = errors
    return gdf
