"""Seleciona falhas e zonas de cisalhamento principais do SIG de estruturas do SGB/CPRM (1:1.000.000)
e grava em data/curated/lineaments/ no formato de pipeline/paleo_lineaments.py.

Criterio de selecao (nosso, nao e interpretacao geologica):
  - TIPO_ESTRU contem 'falha' ou 'cisalhamento', sem 'fratura' e sem 'Lineamentos estruturais: tracos de
    superficies S' (foliacao);
  - comprimento geodesico do segmento >= MIN_KM (os segmentos do SIG sao fragmentados; so os longos entram).
Atributos do SGB preservados: tipo, regime tectonico, evento orogenico, provincia de origem.
Entrada: data/raw/sgb_estruturas/estruturas_brasil_2004.geojson (scripts/fetch_sgb_structures.py).
"""
from __future__ import annotations

import json
from pathlib import Path

from pyproj import Geod

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "data" / "raw" / "sgb_estruturas" / "estruturas_brasil_2004.geojson"
OUT = ROOT / "data" / "curated" / "lineaments" / "sgb_estruturas_br_2004_ge50km.geojson"
MIN_KM = 50.0
CITATION = ("SGB/CPRM. Geologia, Tectonica e Recursos Minerais do Brasil, SIG (estruturas), 2004, escala 1:1.000.000. "
            "https://geoportal.sgb.gov.br/server/rest/services/geologia/Estruturas_GIS_Brasil_2004/MapServer/0")
GEOD = Geod(ellps="WGS84")


def _km(geom: dict) -> float:
    lines = [geom["coordinates"]] if geom["type"] == "LineString" else geom["coordinates"]
    return sum(GEOD.line_length([p[0] for p in l], [p[1] for p in l]) for l in lines) / 1000


def _clean(v) -> str | None:
    v = (v or "").strip() if isinstance(v, str) else None
    return v or None


def select(features: list[dict], min_km: float = MIN_KM) -> list[dict]:
    out = []
    for f in features:
        geom = f.get("geometry")
        if not geom or geom["type"] not in ("LineString", "MultiLineString"):
            continue
        p = f["properties"]
        t = _clean(p.get("TIPO_ESTRU")) or ""
        low = t.lower()
        if "lineamentos estruturais" in low or not ("falha" in low or "cisalhamento" in low):
            continue
        if "fratura" in low:  # 'Falha ou fratura...' mistura fraturas rasas (muito densas na Amazonia)
            continue
        km = _km(geom)
        if km < min_km:
            continue
        out.append({
            "type": "Feature",
            "properties": {
                "name": _clean(p.get("NMESTRUTUR")) or t,
                "kind": t,
                "regime": _clean(p.get("REGIME_TEC")),
                "orogenic_event": _clean(p.get("EVENTO_ORO")),
                "province": _clean(p.get("ORIGEM")),
                "length_km": round(km, 1),
                "source": CITATION,
            },
            "geometry": geom,
        })
    return out


if __name__ == "__main__":
    fc = json.loads(SRC.read_text(encoding="utf-8"))
    sel = select(fc["features"])
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"type": "FeatureCollection", "features": sel}, separators=(",", ":")), encoding="utf-8")
    print(len(sel), "de", len(fc["features"]))
