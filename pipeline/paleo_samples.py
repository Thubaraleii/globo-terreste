"""Amostras na posicao de formacao: GEOROC com idade numerica medida, giradas pelo modelo de placas.

Regras (nada e inferido):
- idade = ponto medio de MIN. AGE e MAX. AGE (anos -> Ma); se so um dos dois existe, usa-se esse
  (age_basis='single'). Periodos em texto (ex.: CRETACEOUS) NAO viram numero.
- so entram amostras com idade ate 152,5 Ma e semi-intervalo (max-min)/2 <= 5 Ma (cabe num quadro de 5 Ma);
  as demais sao contadas e descartadas.
- cada amostra recebe a placa dos poligonos estaticos do modelo (pelo ponto atual) e e girada para a idade
  do quadro mais proximo (passos de 5 Ma). Sem placa: omitida.
- GEOROC e CC BY-SA 4.0 (atribuicao + mesma licenca); os quadros ficam locais (ver .gitignore) ate a
  licenca ser confirmada para publicacao.
"""
from __future__ import annotations

import csv
import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GPKG = ROOT / "data" / "out" / "geoworld.gpkg"
GEOROC_DIR = ROOT / "data" / "raw" / "georoc"
OUT_DIR = ROOT / "web" / "data" / "paleo"

MAX_AGE_MA = 152.5
MAX_HALF_RANGE_MA = 5.0
STEP = 5

_TAG = re.compile(r"\s*\[\d+\]\s*$")


def _num(v) -> float | None:
    try:
        return float(_TAG.sub("", str(v or "").strip()))
    except ValueError:
        return None


def age_from_bounds(min_yrs, max_yrs) -> dict | None:
    """Idade (Ma) a partir de MIN/MAX em anos; None se nao houver numero valido."""
    lo, hi = _num(min_yrs), _num(max_yrs)
    vals = [v for v in (lo, hi) if v is not None and v >= 0]
    if not vals:
        return None
    if len(vals) == 2:
        a, b = sorted(vals)
        return {"age_ma": (a + b) / 2 / 1e6, "age_unc_ma": (b - a) / 2 / 1e6, "age_basis": "range"}
    return {"age_ma": vals[0] / 1e6, "age_unc_ma": None, "age_basis": "single"}


def frame_age(age_ma: float) -> int:
    return int(round(age_ma / STEP) * STEP)


def usable(age: dict) -> bool:
    if age["age_ma"] > MAX_AGE_MA:
        return False
    unc = age["age_unc_ma"]
    return unc is None or unc <= MAX_HALF_RANGE_MA


def read_ages(georoc_dir: Path = GEOROC_DIR) -> dict[str, dict]:
    """UNIQUE_ID -> idade, lida da mesma linha do CSV que o pipeline usou para a amostra."""
    out: dict[str, dict] = {}
    for f in sorted(georoc_dir.glob("*.csv")):
        with open(f, encoding="cp1252", newline="") as fh:
            for row in csv.DictReader(fh):
                uid = (row.get("UNIQUE_ID") or "").strip()
                if not uid:
                    continue
                age = age_from_bounds(row.get("MIN. AGE (YRS.)"), row.get("MAX. AGE (YRS.)"))
                if age:
                    out[f"georoc:{uid}"] = age
    return out


def build(out_dir: Path = OUT_DIR) -> dict:
    import pygplates as g
    import pyogrio

    from pipeline import paleo

    ages = read_ages()
    df = pyogrio.read_dataframe(GPKG, layer="samples")
    df = df[df["id"].isin(ages.keys())].copy()
    stats = Counter()
    stats["com_idade_numerica"] = len(df)

    keep = []
    for _, r in df.iterrows():
        a = ages[r["id"]]
        if not usable(a):
            stats["descartadas_idade_larga_ou_antiga"] += 1
            continue
        keep.append((r, a))

    pts = [(r.geometry.x, r.geometry.y) for r, _ in keep]
    ids = paleo.plate_ids(pts)
    rm = g.RotationModel(str(paleo.ROT))
    rot_cache: dict[tuple[int, int], object] = {}
    frames: dict[int, list] = {}
    for (r, a), pid, (lon, lat) in zip(keep, ids, pts):
        if pid is None:
            stats["sem_placa"] += 1
            continue
        fa = frame_age(a["age_ma"])
        key = (pid, fa)
        if key not in rot_cache:
            rot_cache[key] = rm.get_rotation(float(fa), pid)
        la, lo = (rot_cache[key] * g.PointOnSphere(lat, lon)).to_lat_lon()
        frames.setdefault(fa, []).append({
            "type": "Feature",
            "properties": {
                "id": r["id"],
                "rock_name_original": r["rock_name_original"],
                "rock_class": r["rock_class"],
                "source_id": r["source_id"],
                "age_ma": round(a["age_ma"], 3),
                "age_unc_ma": None if a["age_unc_ma"] is None else round(a["age_unc_ma"], 3),
                "age_basis": a["age_basis"],
                "plate_id": pid,
                "present_lon": round(lon, 3),
                "present_lat": round(lat, 3),
            },
            "geometry": {"type": "Point", "coordinates": [round(lo, 3), round(la, 3)]},
        })

    out_dir.mkdir(parents=True, exist_ok=True)
    counts = {}
    for fa in paleo.ages():
        feats = frames.get(fa, [])
        counts[fa] = len(feats)
        (out_dir / f"samples_{fa}.geojson").write_text(
            json.dumps({"type": "FeatureCollection", "features": feats}, separators=(",", ":")), encoding="utf-8")
    stats["por_quadro"] = counts
    stats["total_giradas"] = sum(counts.values())
    return dict(stats)


if __name__ == "__main__":
    print(json.dumps(build(), ensure_ascii=False, indent=1))
