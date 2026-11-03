"""Exportacao do GeoPackage para a web (globo estatico).

- `volcanoes` e `tectonic_zones` (camadas pequenas) viram GeoJSON
  (`volcanoes.geojson`, `tectonic_zones.geojson`); nulo continua `null`.
- `geo_units` e `samples` viram PMTiles (`geo_units.pmtiles`,
  `samples.pmtiles`) via tippecanoe, chamado sem shell. Sem tippecanoe,
  os PMTiles sao pulados com aviso (nunca falha por isso).
- Qualquer arquivo produzido acima de 95 MB gera aviso (limite de 100 MB
  por arquivo do GitHub Pages).
"""
import json
import math
import os
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd
from pyogrio import read_dataframe
from shapely.geometry import mapping

from pipeline.common.model import _NUMERIC

GEOJSON_LAYERS = ("volcanoes", "tectonic_zones")
PMTILES_LAYERS = ("geo_units", "samples")
MAX_BYTES = 95 * 1024 * 1024
_INT_COLUMNS = {c for c, t in _NUMERIC.items() if t == "Int64"}


@dataclass
class ExportResult:
    files: list[Path] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def file_size(path: Path) -> int:
    """Tamanho em bytes (isolado para os testes simularem arquivos grandes)."""
    return os.path.getsize(path)


def _value(v, column: str):
    if v is None:
        return None
    if isinstance(v, float) and math.isnan(v):
        return None
    if pd.api.types.is_scalar(v) and pd.isna(v):
        return None
    if hasattr(v, "item"):  # escalares numpy
        v = v.item()
    if column in _INT_COLUMNS and isinstance(v, float) and v.is_integer():
        return int(v)
    return v


def _feature_collection(gdf) -> dict:
    props = [c for c in gdf.columns if c != gdf.geometry.name]
    features = []
    for row, geom in zip(gdf[props].itertuples(index=False, name=None), gdf.geometry):
        features.append({
            "type": "Feature",
            "geometry": None if geom is None or geom.is_empty else mapping(geom),
            "properties": {c: _value(v, c) for c, v in zip(props, row)},
        })
    return {"type": "FeatureCollection", "features": features}


def _write_geojson(gdf, path: Path) -> None:
    text = json.dumps(_feature_collection(gdf), ensure_ascii=False, allow_nan=False)
    Path(path).write_text(text, encoding="utf-8")


def export_web(gpkg: Path, out_dir: Path, tippecanoe: str | None,
               run=subprocess.run) -> ExportResult:
    """Escreve os arquivos da web em `out_dir`; `run` e injetavel nos testes."""
    gpkg, out_dir = Path(gpkg), Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    result = ExportResult()

    for layer in GEOJSON_LAYERS:
        target = out_dir / f"{layer}.geojson"
        _write_geojson(read_dataframe(gpkg, layer=layer), target)
        result.files.append(target)

    if tippecanoe is None:
        result.warnings.append(
            "tippecanoe nao encontrado: PMTiles de "
            + ", ".join(PMTILES_LAYERS) + " nao gerados"
        )
    else:
        with tempfile.TemporaryDirectory() as tmp:
            for layer in PMTILES_LAYERS:
                gdf = read_dataframe(gpkg, layer=layer)
                target = out_dir / f"{layer}.pmtiles"
                if target.exists():
                    # tippecanoe nao sobrescreve sem --force; e um arquivo
                    # antigo de camada agora vazia nao deve ser publicado
                    target.unlink()
                if len(gdf) == 0:
                    result.warnings.append(f"camada {layer} vazia: {layer}.pmtiles nao gerado")
                    continue
                source = Path(tmp) / f"{layer}.geojson"
                _write_geojson(gdf, source)
                run(
                    [tippecanoe, "-o", str(target), "-zg", "--drop-densest-as-needed",
                     "-l", layer, str(source)],
                    check=True, capture_output=True,
                )
                result.files.append(target)

    for path in result.files:
        size = file_size(path)
        if size > MAX_BYTES:
            result.warnings.append(
                f"{path.name} tem {size / 1024 / 1024:.1f} MB (acima de 95 MB; "
                "limite do GitHub Pages e 100 MB por arquivo)"
            )
    return result
