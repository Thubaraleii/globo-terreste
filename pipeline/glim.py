"""Normalizacao das unidades litologicas do GLiM para SCHEMAS["geo_units"].

Nada e inferido: `lith_original` guarda o codigo da fonte como veio;
codigo fora de `GLIM_CLASSES` gera `lith_class` nulo.
"""
import geopandas as gpd
import pandas as pd
import shapely

from pipeline.common.geom import repair_geometries, to_wgs84
from pipeline.common.model import SCHEMAS
from pipeline.samples import is_blank

# Conferido em 2026-11-03 no LiMW_GIS 2015.gdb (camada GLiM_export, campos
# IDENTITY_, Litho, xx). Coluna da fonte -> nome logico (`code` = classe
# litologica de primeiro nivel "xx"; `id` opcional = identificador proprio da
# fonte). IDENTITY_ NAO e unico (e tem nulos), entao nao e usado como id; o
# loader real (pipeline.realsources) passa o FID do arquivo como `id`.
GLIM_COLUMNS: dict[str, str] = {"xx": "code"}

# Codigos de primeiro nivel do GLiM (Hartmann & Moosdorf 2012). Os 16 codigos
# distintos de `xx` no arquivo real (2026-11-03) sao exatamente estes.
GLIM_CLASSES: dict[str, str] = {
    "su": "unconsolidated_sediments",
    "ss": "siliciclastic_sedimentary",
    "sc": "carbonate_sedimentary",
    "sm": "mixed_sedimentary",
    "py": "pyroclastics",
    "va": "acid_volcanic",
    "vi": "intermediate_volcanic",
    "vb": "basic_volcanic",
    "pa": "acid_plutonic",
    "pi": "intermediate_plutonic",
    "pb": "basic_plutonic",
    "mt": "metamorphics",
    "ev": "evaporites",
    "wb": "water_bodies",
    "ig": "ice_and_glaciers",
    "nd": "no_data",
}

_COLS = SCHEMAS["geo_units"]
_POLYGONAL = ("Polygon", "MultiPolygon")


def _source_col(columns: dict[str, str], logical: str, df) -> str | None:
    for src, name in columns.items():
        if name == logical and src in df.columns:
            return src
    return None


def _polygonal_part(geom):
    """Parte poligonal da geometria (ou None se nao houver)."""
    if geom is None or geom.is_empty:
        return None
    if geom.geom_type in _POLYGONAL:
        return geom
    polys = []
    for part in shapely.get_parts(geom):
        if part.geom_type == "Polygon":
            polys.append(part)
        elif part.geom_type in ("MultiPolygon", "GeometryCollection"):
            sub = _polygonal_part(part)
            if sub is not None:
                polys.extend(shapely.get_parts(sub))
    polys = [p for p in polys if not p.is_empty]
    if not polys:
        return None
    return polys[0] if len(polys) == 1 else shapely.MultiPolygon(polys)


def normalize_glim(
    gdf: gpd.GeoDataFrame, source_id: str, columns: dict[str, str] = GLIM_COLUMNS
) -> gpd.GeoDataFrame:
    """Converte unidades GLiM para o esquema `geo_units` em EPSG:4326.

    `unit_id` = id proprio da fonte (se mapeado e preenchido) ou
    f"{source_id}:{i}", i = posicao na entrada. Geometrias invalidas sao
    reparadas; linhas sem parte poligonal (inclusive nulas/vazias) saem.
    attrs: `repaired` (int) e `dropped_non_polygon` (int).
    """
    code_col = _source_col(columns, "code", gdf)
    if code_col is None:
        raise ValueError("coluna de codigo litologico ausente (ver GLIM_COLUMNS)")
    id_col = _source_col(columns, "id", gdf)

    raw_ids = gdf[id_col] if id_col else [None] * len(gdf)
    unit_ids = [
        f"{source_id}:{i}" if is_blank(v) else str(v).strip()
        for i, v in enumerate(raw_ids)
    ]
    originals = [None if is_blank(v) else str(v) for v in gdf[code_col]]
    classes = [None if v is None else GLIM_CLASSES.get(v.strip().lower()) for v in originals]

    base = gpd.GeoDataFrame({
        "unit_id": pd.Series(unit_ids, index=gdf.index, dtype="object"),
        "lith_original": pd.Series(originals, index=gdf.index, dtype="object"),
        "lith_class": pd.Series(classes, index=gdf.index, dtype="object"),
        "source_id": pd.Series([source_id] * len(gdf), index=gdf.index, dtype="object"),
    }, geometry=gdf.geometry.values, crs=gdf.crs, index=gdf.index)

    repaired_gdf, repaired = repair_geometries(to_wgs84(base))
    polygonal = [_polygonal_part(g) for g in repaired_gdf.geometry]
    out = repaired_gdf.copy()
    out.geometry = gpd.GeoSeries(polygonal, index=out.index, crs=out.crs)
    out = out[out.geometry.notna()]
    out = out[_COLS].reset_index(drop=True)
    out.attrs["repaired"] = repaired
    out.attrs["dropped_non_polygon"] = len(gdf) - len(out)
    return out
