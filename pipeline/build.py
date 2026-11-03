"""Orquestrador incremental: fontes brutas -> geoworld.gpkg -> arquivos da web.

Para cada `Source` registrada, compara {SHA-256 de `raw_dir/raw_file`,
camada} com o registrado em `out_dir/build_state.json`. So reprocessa (chama
`load`) se a fonte for nova, se hash ou camada mudaram, se o cache falta ou
esta ilegivel, se o estado esta no formato antigo, ou com `force=True`
(`--force`, para quando o mapeamento de colunas de um loader muda).

Cache por fonte: `out_dir/_cache/<source_id>.gpkg`, um GeoPackage com o
esquema canonico completo (`create_geopackage`) em que so a camada da fonte
e preenchida via `write_layer`. Assim o cache passa pela mesma validacao de
esquema e CRS do produto final e fontes inalteradas sao remontadas sem
chamar `load` de novo. O cache e escrito num temporario e movido para o
lugar so apos sucesso; o estado (gravado atomicamente) so aponta para um
cache depois que ele esta no lugar.

Montagem (sempre refeita, a partir dos caches): `out_dir/geoworld.gpkg` com a
tabela `sources` (fontes que contribuem dados) e as camadas; depois as
pos-etapas das amostras (`assign_dup_groups` sobre todas as fontes de
amostras juntas, `attach_units` contra as `geo_units` montadas) e por fim
`export_web`.

Rede: fonte com `needs_network=True` so roda com `allow_network=True`
(CLI `--allow-network`) e recebe `load(path, allow_network=True)`; sem a
permissao fica `skipped_network` (dados antigos dela nao entram). Fontes
locais recebem apenas `load(path)`.
"""
import argparse
import json
import os
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import geopandas as gpd
import pandas as pd
from pyogrio import read_dataframe
from pyogrio.errors import DataLayerError, DataSourceError

from pipeline.common.manifest import _sha256
from pipeline.common.model import CRS, SCHEMAS, create_geopackage, write_layer
from pipeline.dedupe import assign_dup_groups
from pipeline.export import export_web
from pipeline.join import attach_units

LAYERS = ("geo_units", "volcanoes", "tectonic_zones", "samples")
META_FIELDS = [c for c in SCHEMAS["sources"] if c != "source_id"]


@dataclass
class Source:
    """Uma fonte bruta. `load` devolve um GeoDataFrame ja no esquema de
    `layer` (SCHEMAS[layer]; para `samples`, ja normalizado). `meta` pode ter
    institution, source_url, license, attribution, acquisition_date,
    original_scale (ausente -> nulo na tabela `sources`)."""
    source_id: str
    raw_file: str
    layer: str
    load: Callable[..., gpd.GeoDataFrame]
    meta: dict = field(default_factory=dict)
    needs_network: bool = False

    def __post_init__(self):
        if self.layer not in LAYERS:
            raise ValueError(f"{self.source_id}: camada invalida {self.layer!r}")
        unknown = set(self.meta) - set(META_FIELDS)
        if unknown:
            raise ValueError(f"{self.source_id}: campos de meta desconhecidos {sorted(unknown)}")


# Registro padrao: VAZIO de proposito. Ligar as fontes reais (nomes dos
# arquivos brutos, mapeamento de colunas, downloads) e parte da fase de
# aquisicao de dados; ate la o CLI apenas avisa que nao ha fontes.
SOURCES: list[Source] = []


@dataclass
class BuildReport:
    statuses: dict[str, str]          # source_id -> processed | skipped | skipped_network
    counts: dict[str, int]            # camada -> linhas no geoworld.gpkg
    files: list[Path]
    warnings: list[str]


def _load_state(path: Path) -> dict:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def _save_state(path: Path, state: dict) -> None:
    """Escrita atomica: arquivo temporario + os.replace."""
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def _read_cache(cache: Path, layer: str) -> gpd.GeoDataFrame | None:
    """Camada do cache, ou None se o arquivo falta ou nao e legivel."""
    if not cache.exists():
        return None
    try:
        return read_dataframe(cache, layer=layer)
    except (DataSourceError, DataLayerError):
        return None


def _write_cache(cache: Path, layer: str, gdf: gpd.GeoDataFrame) -> None:
    """Escreve num temporario e so o move para `cache` se `write_layer` der certo."""
    tmp = cache.with_name(cache.stem + ".tmp.gpkg")
    try:
        create_geopackage(tmp)
        write_layer(tmp, layer, gdf)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    os.replace(tmp, cache)


def build(raw_dir: Path, out_dir: Path, sources: list[Source],
          allow_network: bool = False, tippecanoe: str | None = None,
          force: bool = False) -> BuildReport:
    """`force=True` reprocessa todas as fontes (ex.: mapeamento do loader mudou)."""
    raw_dir, out_dir = Path(raw_dir), Path(out_dir)
    cache_dir = out_dir / "_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    state_path = out_dir / "build_state.json"
    # Estado: source_id -> {"sha256", "layer"}; formato antigo (so hash) e obsoleto.
    state = _load_state(state_path)
    statuses: dict[str, str] = {}
    frames: dict[str, list[gpd.GeoDataFrame]] = {layer: [] for layer in LAYERS}
    contributing: list[Source] = []

    for src in sources:
        sid = src.source_id
        raw = raw_dir / src.raw_file
        cache = cache_dir / f"{sid}.gpkg"
        digest = _sha256(raw) if raw.exists() else None
        key = {"sha256": digest, "layer": src.layer}
        frame = None
        if not force and digest is not None and state.get(sid) == key:
            frame = _read_cache(cache, src.layer)
        if frame is not None:
            statuses[sid] = "skipped"
        elif src.needs_network and not allow_network:
            statuses[sid] = "skipped_network"
            continue
        elif digest is None:
            raise FileNotFoundError(f"{sid}: arquivo bruto ausente {raw}")
        else:
            gdf = src.load(raw, allow_network=True) if src.needs_network else src.load(raw)
            gdf = gdf.copy()
            gdf["source_id"] = sid
            # o estado so volta a apontar para o cache depois que ele esta no lugar
            state.pop(sid, None)
            _save_state(state_path, state)
            _write_cache(cache, src.layer, gdf)
            state[sid] = key
            _save_state(state_path, state)
            frame = read_dataframe(cache, layer=src.layer)
            statuses[sid] = "processed"
        frames[src.layer].append(frame)
        contributing.append(src)

    gpkg = out_dir / "geoworld.gpkg"
    create_geopackage(gpkg)
    if contributing:
        write_layer(gpkg, "sources", pd.DataFrame(
            [{"source_id": s.source_id, **{k: s.meta.get(k) for k in META_FIELDS}}
             for s in contributing],
            columns=SCHEMAS["sources"],
        ))
    for layer in ("geo_units", "volcanoes", "tectonic_zones"):
        for gdf in frames[layer]:
            write_layer(gpkg, layer, gdf)
    if frames["samples"]:
        samples = gpd.GeoDataFrame(
            pd.concat(frames["samples"], ignore_index=True), geometry="geometry", crs=CRS,
        )
        samples = assign_dup_groups(samples)
        samples = attach_units(samples, read_dataframe(gpkg, layer="geo_units"))
        write_layer(gpkg, "samples", samples)

    registered = {s.source_id for s in sources}
    _save_state(state_path, {k: v for k, v in state.items() if k in registered})
    counts = {layer: len(read_dataframe(gpkg, layer=layer)) for layer in LAYERS}
    exported = export_web(gpkg, out_dir, tippecanoe)
    return BuildReport(statuses, counts, exported.files, exported.warnings)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m pipeline.build")
    parser.add_argument("--raw", type=Path, default=Path("data/raw"))
    parser.add_argument("--out", type=Path, default=Path("data/out"))
    parser.add_argument("--allow-network", action="store_true",
                        help="permite etapas de rede (download, geocodificacao)")
    parser.add_argument("--force", action="store_true",
                        help="reprocessa todas as fontes, ignorando o cache")
    parser.add_argument("--tippecanoe", default=shutil.which("tippecanoe"),
                        help="caminho do tippecanoe (padrao: o do PATH)")
    args = parser.parse_args(argv)

    if not SOURCES:
        print("Nenhuma fonte registrada em pipeline.build.SOURCES; nada a fazer. "
              "A ligacao das fontes reais e parte da fase de aquisicao de dados.")
        return 0

    rep = build(args.raw, args.out, SOURCES, allow_network=args.allow_network,
                tippecanoe=args.tippecanoe, force=args.force)
    for source_id, status in rep.statuses.items():
        print(f"{source_id}: {status}")
    for layer, n in rep.counts.items():
        print(f"{layer}: {n} linhas")
    for path in rep.files:
        print(f"arquivo: {path}")
    for w in rep.warnings:
        print(f"AVISO: {w}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
