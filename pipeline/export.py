"""Exportacao do GeoPackage para a web (globo estatico).

- `volcanoes` e `tectonic_zones` (camadas pequenas) viram GeoJSON
  (`volcanoes.geojson`, `tectonic_zones.geojson`); nulo continua `null`.
  Em `tectonic_zones.geojson`, `moment_total` vira texto ("3.981e+19") e
  ganha `moment_log10` (ver `_moment_props`).
- A tabela `sources` vira `sources.json` (array JSON, uma linha por fonte).
- `geo_units` e `samples` viram PMTiles (`geo_units.pmtiles`,
  `samples.pmtiles`) via tippecanoe, chamado sem shell, com as flags de
  `TIPPECANOE_FLAGS`. Sem tippecanoe, os PMTiles sao pulados com aviso (nunca
  falha por isso). Falha do tippecanoe vira RuntimeError com o stderr dele.
  Versao do tippecanoe ilegivel ou < 2.17 gera aviso.
- `keep_intermediate`: guarda os GeoJSON de entrada do tippecanoe nessa pasta
  (mesmo sem tippecanoe), para gerar os PMTiles a mao.
- Qualquer arquivo produzido acima de 95 MB gera aviso (limite de 100 MB
  por arquivo do GitHub Pages).
"""
import json
import math
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd
from pyogrio import read_dataframe
from shapely.geometry import mapping

from pipeline.common.model import _NUMERIC, SCHEMAS

GEOJSON_LAYERS = ("volcanoes", "tectonic_zones")
PMTILES_LAYERS = ("geo_units", "samples")
MAX_BYTES = 95 * 1024 * 1024
MIN_TIPPECANOE = (2, 17, 0)
# Flags por camada (alem de -o <arquivo>.pmtiles e -l <camada>).
TIPPECANOE_FLAGS = {
    "samples": ["-zg", "-r1", "--drop-densest-as-needed", "--extend-zooms-if-still-dropping"],
    "geo_units": ["-zg", "--coalesce-densest-as-needed", "--extend-zooms-if-still-dropping"],
}
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


def _with_unit_lith_class(samples, units):
    """Copia de `samples` com `unit_lith_class` (lith_class da unidade pelo
    `unit_id`; nulo sem unidade, unidade ausente ou lith_class nulo). So para
    exportar: alimenta o filtro "amostras desta litologia" da web."""
    lookup = (
        units.dropna(subset=["unit_id"])
        .drop_duplicates(subset="unit_id")  # unit_id repetido: vale a 1a linha (deliberado)
        .set_index("unit_id")["lith_class"]
    )
    out = samples.copy()
    out["unit_lith_class"] = out["unit_id"].map(lookup).astype(object)
    return out


def _with_sample_count(units, samples):
    """Copia de `units` com `sample_count` (int, nunca nulo): quantas amostras
    tem aquele `unit_id`. So para exportar: o painel da unidade precisa da
    contagem exata, que o navegador nao calcula a partir dos tiles."""
    counts = samples["unit_id"].dropna().value_counts()
    out = units.copy()
    out["sample_count"] = out["unit_id"].map(counts).fillna(0).astype("int64")
    return out


def _moment_props(v) -> dict:
    """`moment_total` (N*m) para a web: texto em notacao cientifica com 4
    algarismos significativos e `moment_log10` (3 casas). Nulo se o valor for
    nulo, nao finito ou <= 0. Motivo: o worker do MapLibre grava numeros
    inteiros das propriedades GeoJSON como varint, e valores >= 2^64 (momentos
    sismicos reais passam de 1e19) quebram a camada."""
    try:
        x = float(v)
    except (TypeError, ValueError):
        x = math.nan
    if not math.isfinite(x) or x <= 0:
        return {"moment_total": None, "moment_log10": None}
    return {"moment_total": f"{x:.3e}", "moment_log10": round(math.log10(x), 3)}


def _with_moment_strings(zones):
    """Copia de `zones` com `moment_total` como texto e `moment_log10` (so para
    exportar; o GeoPackage continua com o float)."""
    out = zones.copy()
    props = [_moment_props(v) for v in out["moment_total"]]
    out["moment_total"] = pd.Series([p["moment_total"] for p in props], index=out.index, dtype=object)
    pos = out.columns.get_loc("moment_total") + 1
    out.insert(pos, "moment_log10",
               pd.Series([p["moment_log10"] for p in props], index=out.index, dtype=object))
    return out


def _write_geojson(gdf, path: Path) -> None:
    text = json.dumps(_feature_collection(gdf), ensure_ascii=False, allow_nan=False)
    Path(path).write_text(text, encoding="utf-8")


def _text(v) -> str:
    if v is None:
        return ""
    return v.decode("utf-8", errors="replace") if isinstance(v, bytes) else str(v)


def _parse_version(text: str) -> tuple[int, int, int] | None:
    m = re.search(r"(\d+)\.(\d+)(?:\.(\d+))?", text or "")
    if not m:
        return None
    return int(m[1]), int(m[2]), int(m[3] or 0)


def _version_warning(tippecanoe: str, run) -> str | None:
    """Roda `tippecanoe --version` pelo mesmo runner. Versao ilegivel ou abaixo de
    2.17 gera AVISO (nao erro): a saida .pmtiles exige um tippecanoe recente."""
    try:
        proc = run([tippecanoe, "--version"], check=False, capture_output=True)
        found = _parse_version(_text(proc.stdout) + " " + _text(proc.stderr))
    except (OSError, subprocess.SubprocessError):
        found = None
    if found is not None and found >= MIN_TIPPECANOE:
        return None
    seen = ".".join(map(str, found)) if found else "nao identificada"
    return (f"versao do tippecanoe {seen}: a saida PMTiles exige um tippecanoe recente "
            "(>= 2.17, nao verificado aqui); os PMTiles podem falhar")


def _write_tile_inputs(gpkg: Path, folder: Path, result: ExportResult) -> dict[str, Path]:
    """Escreve em `folder` o GeoJSON de entrada do tippecanoe de cada camada
    nao vazia (com `sample_count` / `unit_lith_class`); camada vazia gera aviso."""
    folder.mkdir(parents=True, exist_ok=True)
    written = {}
    for layer in PMTILES_LAYERS:
        gdf = read_dataframe(gpkg, layer=layer)
        if len(gdf) == 0:
            result.warnings.append(f"camada {layer} vazia: {layer}.pmtiles nao gerado")
            continue
        if layer == "geo_units":
            # so atributos: contar nao exige decodificar geometrias
            samples = read_dataframe(gpkg, layer="samples", columns=["unit_id"],
                                     read_geometry=False)
            gdf = _with_sample_count(gdf, samples)
        if layer == "samples":
            # so atributos: nao decodificar milhoes de poligonos do GLiM
            units = read_dataframe(gpkg, layer="geo_units",
                                   columns=["unit_id", "lith_class"],
                                   read_geometry=False)
            gdf = _with_unit_lith_class(gdf, units)
        source = folder / f"{layer}.geojson"
        _write_geojson(gdf, source)
        del gdf
        written[layer] = source
    return written


def export_web(gpkg: Path, out_dir: Path, tippecanoe: str | None,
               run=subprocess.run, keep_intermediate: Path | None = None) -> ExportResult:
    """Escreve os arquivos da web em `out_dir`; `run` e injetavel nos testes.
    `keep_intermediate`: pasta onde ficam os GeoJSON de entrada do tippecanoe
    (escritos mesmo sem tippecanoe, para rodar o tippecanoe a mao, ex. no WSL)."""
    gpkg, out_dir = Path(gpkg), Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    result = ExportResult()

    for layer in GEOJSON_LAYERS:
        target = out_dir / f"{layer}.geojson"
        gdf = read_dataframe(gpkg, layer=layer)
        if layer == "tectonic_zones":
            gdf = _with_moment_strings(gdf)
        _write_geojson(gdf, target)
        result.files.append(target)

    # Tabela `sources` (sem geometria) para o painel de detalhes da web.
    cols = SCHEMAS["sources"]
    table = read_dataframe(gpkg, layer="sources", columns=cols)[cols]
    rows = [{c: _value(v, c) for c, v in zip(cols, row)}
            for row in table.itertuples(index=False, name=None)]
    target = out_dir / "sources.json"
    target.write_text(json.dumps(rows, ensure_ascii=False, allow_nan=False, indent=2),
                      encoding="utf-8")
    result.files.append(target)

    if tippecanoe is None:
        warning = ("tippecanoe nao encontrado: PMTiles de "
                   + ", ".join(PMTILES_LAYERS) + " nao gerados")
        stale = [out_dir / f"{layer}.pmtiles" for layer in PMTILES_LAYERS]
        stale = [p for p in stale if p.exists()]
        for p in stale:
            p.unlink()
        if stale:
            warning += "; obsoletos removidos: " + ", ".join(p.name for p in stale)
        result.warnings.append(warning)
        if keep_intermediate is not None:
            written = _write_tile_inputs(gpkg, Path(keep_intermediate), result)
            if written:
                result.warnings.append(
                    f"entradas do tippecanoe mantidas em {keep_intermediate}: "
                    + ", ".join(p.name for p in written.values())
                    + " (rode o tippecanoe a mao para gerar os PMTiles)")
    else:
        old = _version_warning(tippecanoe, run)
        if old:
            result.warnings.append(old)
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(keep_intermediate) if keep_intermediate is not None else Path(tmp)
            for layer in PMTILES_LAYERS:
                target = out_dir / f"{layer}.pmtiles"
                if target.exists():
                    # tippecanoe nao sobrescreve sem --force; e um arquivo
                    # antigo de camada agora vazia nao deve ser publicado
                    target.unlink()
            for layer, source in _write_tile_inputs(gpkg, folder, result).items():
                target = out_dir / f"{layer}.pmtiles"
                cmd = [tippecanoe, "-o", str(target), *TIPPECANOE_FLAGS[layer],
                       "-l", layer, str(source)]
                try:
                    run(cmd, check=True, capture_output=True)
                except subprocess.CalledProcessError as e:
                    raise RuntimeError(
                        f"tippecanoe falhou ao gerar {target.name} (codigo {e.returncode}): "
                        + _text(e.stderr).strip()
                    ) from e
                result.files.append(target)

    for path in result.files:
        size = file_size(path)
        if size > MAX_BYTES:
            result.warnings.append(
                f"{path.name} tem {size / 1024 / 1024:.1f} MB (acima de 95 MB; "
                "limite do GitHub Pages e 100 MB por arquivo)"
            )
    return result
