"""Falhas do Mapa Geologico da Africa 1:10.000.000 (CGMW-BRGM, 3a edicao, 2016) no formato de lineamentos.

Fonte: WFS do BRGM (OneGeology) http://mapsref.brgm.fr/wxs/1GG/IGC35_CGMW_BRGM_Africa_Geology, camada
AFR_CGMW_BRGM_10M_Faults (2.644 linhas; classes: Fault, Thrust fault, Normal fault e as 'Inferred ...').
Termos do servico: uso pessoal, de ensino, de pesquisa ou nao comercial; copyright CGMW/BRGM; nao revender.
Baixar: curl "<WFS>?service=WFS&version=2.0.0&request=GetFeature&typenames=AFR_CGMW_BRGM_10M_Faults"
        -o data/raw/brgm_africa/faults.gml
Saida: data/curated/lineaments/brgm_africa_faults_10m.geojson (git-ignored; licenca restringe a nao comercial).
Nao ha classe 'zona de cisalhamento' nesta camada: sao falhas, como o mapa as classifica.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "data" / "raw" / "brgm_africa" / "faults.gml"
OUT = ROOT / "data" / "curated" / "lineaments" / "brgm_africa_faults_10m.geojson"
CITATION = ("Geological Map of Africa at 1:10 M scale, CGMW-BRGM 2016 (3rd edition), camada de falhas "
            "(AFR_CGMW_BRGM_10M_Faults). http://mapsref.brgm.fr/wxs/1GG/IGC35_CGMW_BRGM_Africa_Geology")


def convert() -> list[dict]:
    import pyogrio

    df = pyogrio.read_dataframe(SRC)
    feats = []
    for _, r in df.iterrows():
        geom = r.geometry
        if geom is None or geom.is_empty:
            continue
        feats.append({
            "type": "Feature",
            "properties": {
                "name": f"{r['DESCR']} (CGMW-BRGM)",
                "kind": str(r["DESCR"]),
                "length_km": None,
                "source": CITATION,
            },
            "geometry": json.loads(json.dumps(geom.__geo_interface__)),
        })
    return feats


if __name__ == "__main__":
    feats = convert()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"type": "FeatureCollection", "features": feats}, separators=(",", ":")), encoding="utf-8")
    print(len(feats))
