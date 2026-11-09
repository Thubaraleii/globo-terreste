"""Lineamentos estruturais girados pelo modelo de placas (para ligar os dois lados do Atlantico).

Entrada: arquivos GeoJSON em data/curated/lineaments/ fornecidos pelo pesquisador (ou baixados de uma
fonte citavel). NADA e desenhado ou inferido aqui. Cada feicao precisa de:
  - geometria LineString ou MultiLineString (WGS84, lon/lat);
  - properties.name (texto) e properties.source (citacao/URL da fonte; sem fonte a feicao e recusada).
Opcionais: properties.kind (ex.: 'shear_zone', 'dyke_swarm'), properties.age_ma_reported.

Regra de placa: cada feicao e girada como um corpo rigido pela placa do seu ponto medio (poligonos
estaticos do modelo). Se as pontas caem em placas diferentes, a feicao e marcada
(properties.plates_differ=true) e continua sendo girada pela placa do ponto medio.

Saida: web/data/paleo/lineaments_<idade>.geojson (0-150 Ma, de 5 em 5).
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IN_DIR = ROOT / "data" / "curated" / "lineaments"
OUT_DIR = ROOT / "web" / "data" / "paleo"


def _lines(geom: dict) -> list[list[list[float]]]:
    if geom.get("type") == "LineString":
        return [geom["coordinates"]]
    if geom.get("type") == "MultiLineString":
        return geom["coordinates"]
    return []


def validate(feature: dict) -> str | None:
    """Motivo da recusa, ou None se a feicao e valida."""
    props = feature.get("properties") or {}
    if not isinstance(props.get("name"), str) or not props["name"].strip():
        return "sem properties.name"
    if not isinstance(props.get("source"), str) or not props["source"].strip():
        return "sem properties.source (fonte obrigatoria)"
    lines = _lines(feature.get("geometry") or {})
    if not lines or any(len(l) < 2 for l in lines):
        return "geometria nao e LineString/MultiLineString valida"
    for l in lines:
        for c in l:
            if not (-180 <= c[0] <= 180 and -90 <= c[1] <= 90):
                return "coordenada fora de lon/lat"
    return None


def load(in_dir: Path = IN_DIR) -> tuple[list[dict], list[tuple[str, str]]]:
    feats, rejected = [], []
    for f in sorted(in_dir.glob("*.geojson")):
        data = json.loads(f.read_text(encoding="utf-8"))
        for i, ft in enumerate(data.get("features", [])):
            why = validate(ft)
            if why:
                rejected.append((f"{f.name}#{i}", why))
            else:
                feats.append(ft)
    return feats, rejected


def build(in_dir: Path = IN_DIR, out_dir: Path = OUT_DIR, max_ma: int = 150, step: int = 5) -> dict:
    import pygplates as g

    from pipeline import paleo

    feats, rejected = load(in_dir)
    if not feats:
        return {"lineamentos": 0, "recusados": rejected}
    mids, ends = [], []
    for ft in feats:
        coords = [c for l in _lines(ft["geometry"]) for c in l]
        mids.append(tuple(coords[len(coords) // 2][:2]))
        ends.append((tuple(coords[0][:2]), tuple(coords[-1][:2])))
    mid_ids = paleo.plate_ids(mids)
    a_ids = paleo.plate_ids([e[0] for e in ends])
    b_ids = paleo.plate_ids([e[1] for e in ends])
    rm = g.RotationModel(str(paleo.ROT))

    out_dir.mkdir(parents=True, exist_ok=True)
    no_plate = 0
    for age in paleo.ages(max_ma, step):
        out = []
        for ft, pid, pa, pb in zip(feats, mid_ids, a_ids, b_ids):
            if pid is None:
                continue
            rot = rm.get_rotation(float(age), pid)
            lines = []
            for line in _lines(ft["geometry"]):
                pts = [(rot * g.PointOnSphere(c[1], c[0])).to_lat_lon() for c in line]
                lines.append([[round(lo, 3), round(la, 3)] for la, lo in pts])
            props = dict(ft["properties"])
            props.update({"paleo_age_ma": age, "plate_id": pid, "plates_differ": len({pa, pb, pid}) > 1})
            out.append({"type": "Feature", "properties": props,
                        "geometry": {"type": "MultiLineString", "coordinates": lines}})
        (out_dir / f"lineaments_{age}.geojson").write_text(
            json.dumps({"type": "FeatureCollection", "features": out}, separators=(",", ":")), encoding="utf-8")
    no_plate = sum(i is None for i in mid_ids)
    return {"lineamentos": len(feats), "sem_placa": no_plate, "recusados": rejected}


if __name__ == "__main__":
    print(json.dumps(build(), ensure_ascii=False, indent=1))
