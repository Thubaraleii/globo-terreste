"""Ligacao de duplicatas entre fontes (preenche `dup_group`).

Nada e removido nem inferido: registros de fontes diferentes com a mesma
coordenada arredondada e o mesmo nome de rocha normalizado recebem o mesmo
`dup_group`; os demais ficam nulos.
"""
import hashlib

import geopandas as gpd
import pandas as pd

from pipeline.rockmap import normalize_rock_name


def _coord(v: float, precision: int) -> float:
    return round(float(v), precision) + 0.0  # +0.0 transforma -0.0 em 0.0


def _group_id(key: tuple) -> str:
    return hashlib.sha256(repr(key).encode("utf-8")).hexdigest()[:12]


def assign_dup_groups(samples: gpd.GeoDataFrame, precision: int = 4) -> gpd.GeoDataFrame:
    """Devolve copia com `dup_group` recalculado; linhas e ordem preservadas.

    Chave: (lon, lat arredondados, nome de rocha normalizado). So forma grupo
    a chave presente em >= 2 `source_id` distintos. Geometria nula ou nome
    vazio nunca entram em grupo.
    """
    out = samples.copy()
    keys = []
    for geom, name in zip(out.geometry, out["rock_name_original"]):
        rock = normalize_rock_name(name)
        if geom is None or geom.is_empty or rock is None:
            keys.append(None)
        else:
            keys.append((_coord(geom.x, precision), _coord(geom.y, precision), rock))

    sources: dict[tuple, set] = {}
    for key, src in zip(keys, out["source_id"]):
        if key is not None:
            sources.setdefault(key, set()).add(src)

    groups = [
        _group_id(k) if k is not None and len(sources[k]) >= 2 else None for k in keys
    ]
    out["dup_group"] = pd.Series(groups, index=out.index, dtype="object")
    return out
