"""Baixa as estruturas do SIG Geologia, Tectonica e Recursos Minerais do Brasil (SGB/CPRM, 2004, 1:1.000.000).

Fonte: https://geoportal.sgb.gov.br/server/rest/services/geologia/Estruturas_GIS_Brasil_2004/MapServer/0
(camada de linhas; 32.323 feicoes). Licenca NAO declarada no servico (copyrightText vazio): uso local
de pesquisa, com citacao do SGB/CPRM; ver README antes de publicar.

Saida: data/raw/sgb_estruturas/estruturas_brasil_2004.geojson (git-ignored) + .meta.json (URL, data, contagem).
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import requests

BASE = "https://geoportal.sgb.gov.br/server/rest/services/geologia/Estruturas_GIS_Brasil_2004/MapServer/0/query"
OUT = Path(__file__).resolve().parents[1] / "data" / "raw" / "sgb_estruturas"
PAGE = 2000


def fetch() -> dict:
    """O servico nao pagina (resultOffset) e limita a 2000 por resposta: busca por faixas de FID."""
    count = requests.get(BASE, params={"where": "1=1", "returnCountOnly": "true", "f": "json"}, timeout=120).json()["count"]
    maxfid = requests.get(BASE, params={
        "where": "1=1", "returnIdsOnly": "true", "f": "json"}, timeout=120).json()["objectIds"]
    maxfid = max(maxfid)
    feats: list[dict] = []
    step = 1500
    for lo in range(0, maxfid + 1, step):
        r = requests.get(BASE, params={
            "where": f"FID >= {lo} AND FID < {lo + step}", "outFields": "*", "returnGeometry": "true",
            "outSR": 4326, "geometryPrecision": 4, "f": "geojson",
        }, timeout=120)
        r.raise_for_status()
        body = r.json()
        if "error" in body:
            raise RuntimeError(body["error"])
        feats += body.get("features", [])
    if len(feats) != count:
        raise RuntimeError(f"baixou {len(feats)} feicoes, o servico declara {count}")
    return {"type": "FeatureCollection", "features": feats}


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    fc = fetch()
    (OUT / "estruturas_brasil_2004.geojson").write_text(json.dumps(fc, separators=(",", ":")), encoding="utf-8")
    (OUT / "estruturas_brasil_2004.meta.json").write_text(json.dumps({
        "url": BASE, "downloaded": date.today().isoformat(), "features": len(fc["features"]),
        "citation": "SGB/CPRM. Geologia, Tectonica e Recursos Minerais do Brasil, SIG, 2004 (estruturas, 1:1.000.000).",
        "licence": "nao declarada no servico",
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    print(len(fc["features"]))
