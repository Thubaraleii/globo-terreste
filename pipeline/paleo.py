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


STATIC = MODEL_DIR / "StaticPolygons" / "shapes_static_polygons_Merdith_etal.gpml"


def plate_ids(points_lonlat: list[tuple[float, float]]) -> list[int | None]:
    """Placa (plateID do modelo) sob cada ponto atual, pelos poligonos estaticos; None se nenhum."""
    import pygplates as g

    static = g.FeatureCollection(str(STATIC))
    out: list[int | None] = []
    # indice simples: lista de (poligono, plateID); 1 mil pontos x ~700 poligonos e aceitavel
    polys = []
    for f in static:
        pid = f.get_reconstruction_plate_id()
        for geom in f.get_geometries():
            if isinstance(geom, g.PolygonOnSphere):
                polys.append((geom, pid))
    for lon, lat in points_lonlat:
        pt = g.PointOnSphere(lat, lon)
        found = None
        for poly, pid in polys:
            if poly.is_point_in_polygon(pt):
                found = pid
                break
        out.append(found)
    return out


def reconstruct_points(fc: dict, ids: list[int | None], rotation_model, age: float) -> dict:
    """Leva cada ponto para a posicao que a sua placa tinha na idade. Sem placa: o ponto e omitido."""
    import pygplates as g

    cache: dict[int, object] = {}
    feats = []
    for f, pid in zip(fc["features"], ids):
        if pid is None:
            continue
        lon, lat = f["geometry"]["coordinates"][:2]
        if pid not in cache:
            cache[pid] = rotation_model.get_rotation(float(age), pid)
        p = cache[pid] * g.PointOnSphere(lat, lon)
        la, lo = p.to_lat_lon()
        feats.append({
            "type": "Feature",
            "properties": {**f["properties"], "paleo_age_ma": age, "plate_id": pid},
            "geometry": {"type": "Point", "coordinates": [round(lo, 3), round(la, 3)]},
        })
    return {"type": "FeatureCollection", "features": feats}


def build_volcanoes(max_ma: int = 150, step: int = 5, out_dir: Path = OUT_DIR) -> dict:
    import pygplates as g

    src = ROOT / "web" / "data" / "volcanoes.geojson"
    fc = json.loads(src.read_text(encoding="utf-8"))
    pts = [tuple(f["geometry"]["coordinates"][:2]) for f in fc["features"]]
    ids = plate_ids(pts)
    rm = g.RotationModel(str(ROT))
    out_dir.mkdir(parents=True, exist_ok=True)
    for a in ages(max_ma, step):
        rec = reconstruct_points(fc, ids, rm, a)
        (out_dir / f"volcanoes_{a}.geojson").write_text(json.dumps(rec, separators=(",", ":")), encoding="utf-8")
    return {"total": len(ids), "sem_placa": sum(i is None for i in ids)}


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
    stats = build_volcanoes()
    idx_path = OUT_DIR / "index.json"
    idx = json.loads(idx_path.read_text(encoding="utf-8"))
    idx["volcanoes"] = stats  # indica que ha quadros volcanoes_<idade>.geojson
    idx_path.write_text(json.dumps(idx, indent=2), encoding="utf-8")
    print(stats)
