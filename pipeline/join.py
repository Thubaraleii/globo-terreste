"""Ligacao amostra -> unidade geologica (ponto dentro do poligono).

Usa o indice espacial (STRtree) das unidades; predicado `intersects`
para que pontos na borda contem. Empates (borda compartilhada ou
unidades sobrepostas) vao para o menor `unit_id` em ordem de string.
Sem unidade, ou geometria nula/vazia: `unit_id` nulo.
"""
import geopandas as gpd
import numpy as np
import pandas as pd


def attach_units(samples: gpd.GeoDataFrame, units: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Copia de `samples` com `unit_id` preenchido; linhas, ordem, indice,
    demais colunas e CRS preservados."""
    if samples.crs is None or units.crs is None:
        raise ValueError("CRS ausente em amostras ou unidades; nao presumimos EPSG:4326")
    if samples.crs != units.crs:
        raise ValueError(f"CRS diferentes: amostras {samples.crs} x unidades {units.crs}")

    geoms = samples.geometry.values
    usable = np.flatnonzero(~(geoms.isna() | geoms.is_empty))
    result = np.full(len(samples), None, dtype=object)

    if len(usable) and len(units):
        hit_s, hit_u = units.sindex.query(geoms[usable], predicate="intersects")
        pairs = pd.DataFrame({
            "pos": usable[hit_s],
            "unit_id": units["unit_id"].to_numpy(dtype=object)[hit_u],
        }).dropna(subset=["unit_id"])
        best = pairs.groupby("pos")["unit_id"].min()
        result[best.index.to_numpy()] = best.to_numpy(dtype=object)

    out = samples.copy()
    out["unit_id"] = pd.Series(result, index=out.index, dtype="object")
    return out
