"""Integracao com os arquivos REAIS em data/raw/ (opcional).

Cada teste e pulado quando o arquivo bruto nao existe (data/raw/ e ignorado
pelo git, entao num clone novo tudo e pulado). So afirma fatos estruturais
(contagem > 0, colunas do esquema, CRS): nenhum valor real e copiado para o
repositorio. O GLiM le so as primeiras linhas, para nao carregar o arquivo
inteiro.
"""
from pathlib import Path

import pytest
from pyogrio import read_info

from pipeline import realsources as rs
from pipeline.common.model import CRS, SCHEMAS
from pipeline.glim import normalize_glim

RAW = Path(__file__).resolve().parent.parent / "data" / "raw"


def _need(*rel: str) -> list[Path]:
    paths = [RAW / r for r in rel]
    missing = [str(p) for p in paths if not p.exists()]
    if missing:
        pytest.skip(f"arquivo bruto ausente: {missing}")
    return paths


def test_real_gvp():
    (path,) = _need(rs.GVP_FILE)
    out = rs.load_gvp(path)
    assert len(out) > 0
    assert list(out.columns) == SCHEMAS["volcanoes"]
    assert out.crs == CRS
    assert out["name"].notna().all()


def test_real_tectonics():
    (path, _) = _need(rs.USGS_FILE, rs.PB2002_FILE)
    out = rs.load_tectonics(path)
    assert 0 < len(out) <= rs.TOP_ZONES
    assert list(out.columns) == SCHEMAS["tectonic_zones"]
    assert out.crs == CRS
    assert list(out["rank"]) == list(range(1, len(out) + 1))
    assert out.attrs["quakes_used"] > 0


def test_real_georoc_smallest_file():
    name = "2026-09-2JETOA_ORTHOPYROXENITE.csv"
    (path,) = _need(f"{rs.GEOROC_DIR}/{name}")
    out = rs.load_georoc(path)
    assert len(out) > 0
    assert list(out.columns) == SCHEMAS["samples"]
    assert out.crs == CRS
    assert set(out["rock_class"]) <= {"mafic", "ultramafic"}
    assert out["id"].is_unique


def test_real_glim_structure_and_first_units():
    (path,) = _need(rs.GLIM_FILE)
    info = read_info(rs._vsizip(path), layer=rs.GLIM_LAYER)
    assert info["features"] > 0
    assert "xx" in list(info["fields"])
    assert "Eckert_IV" in info["crs"]
    raw = rs.read_glim(path, max_features=50)
    assert 0 < len(raw) <= 50
    assert set(raw["xx"]) <= {"vb", "pb"}
    out = normalize_glim(raw, "glim", columns={"xx": "code", "unit_fid": "id"})
    assert list(out.columns) == SCHEMAS["geo_units"]
    assert out.crs == CRS
    assert out["unit_id"].str.startswith("glim:fid:").all()
