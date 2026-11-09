"""Paleogeografia: linhas de costa reconstruidas (Merdith et al. 2021, v1.2.4, CC BY 4.0).

Le o modelo baixado em data/raw/paleo/merdith, reconstroi as linhas de costa para cada idade
e grava um GeoJSON por idade em web/data/paleo/coast_<idade>.geojson (+ index.json).
Nada e inferido: a geometria vem do modelo; so aplicamos as rotacoes dele.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODEL_DIR = ROOT / "data" / "raw" / "paleo" / "merdith"
ROT = MODEL_DIR / "Rotations" / "1000_0_rotfile_Merdith_etal.rot"
COAST = MODEL_DIR / "Coastlines" / "shapes_coastlines_Merdith_et_al_v2.gpmlz"
OUT_DIR = ROOT / "web" / "data" / "paleo"

MODEL = {
    "id": "merdith2021",
    "name": "Merdith et al. 2021 (v1.2.4)",
    "licence": "CC BY 4.0",
    "citation": "Merdith, A.S. et al. (2021) Extending full-plate tectonic models into deep time: "
                "Linking the Neoproterozoic and the Phanerozoic. Earth-Science Reviews 214, 103477.",
    "doi": "10.5281/zenodo.13635864",
}


def ages(max_ma: int = 150, step: int = 5) -> list[int]:
    return list(range(0, max_ma + 1, step))


def _ring(points) -> list[list[float]]:
    # pygplates entrega PointOnSphere/LatLonPoint; GeoJSON usa [lon, lat]
    ring = [[round(p.get_longitude(), 3), round(p.get_latitude(), 3)] for p in points]
    if ring and ring[0] != ring[-1]:
        ring.append(ring[0])
    return ring


def reconstruct_age(rotation_model, age: float) -> dict:
    import pygplates as g

    recon: list = []
    g.reconstruct(str(COAST), rotation_model, recon, float(age))
    wrapper = g.DateLineWrapper()
    feats = []
    for rg in recon:
        feature = rg.get_feature()
        geom = rg.get_reconstructed_geometry()
        if not isinstance(geom, g.PolygonOnSphere):
            continue
        for poly in wrapper.wrap(geom):
            pts = poly.get_exterior_points()
            if len(pts) < 3:
                continue
            feats.append({
                "type": "Feature",
                "properties": {"name": feature.get_name() or None, "age_ma": age},
                "geometry": {"type": "Polygon", "coordinates": [_ring(pts)]},
            })
    return {"type": "FeatureCollection", "features": feats}


def build(max_ma: int = 150, step: int = 5, out_dir: Path = OUT_DIR) -> list[int]:
    import pygplates as g

    for p in (ROT, COAST):
        if not p.exists():
            raise FileNotFoundError(f"{p} nao encontrado: baixe e extraia o modelo (ver README, Paleomapas).")
    out_dir.mkdir(parents=True, exist_ok=True)
    rm = g.RotationModel(str(ROT))
    done = ages(max_ma, step)
    for a in done:
        fc = reconstruct_age(rm, a)
        (out_dir / f"coast_{a}.geojson").write_text(json.dumps(fc, separators=(",", ":")), encoding="utf-8")
    (out_dir / "index.json").write_text(
        json.dumps({"model": MODEL, "ages_ma": done, "layer": "coastlines"}, indent=2), encoding="utf-8"
    )
    return done


if __name__ == "__main__":
    print(build())
