"""Vista 3D da abertura do Atlantico Sul: grade de alturas, placa por celula e rotacoes.

Relevo e batimetria atuais (AWS Terrain Tiles, formato terrarium) numa grade de 0,05 grau; cada celula
recebe a placa do modelo (Merdith et al. 2021) pelos poligonos estaticos. A pagina move cada placa como
corpo rigido. Nada e inferido: celula sem placa ou sem altura fica nula.
"""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
BBOX = (-65.0, 40.0, -40.0, -20.0)  # lon_min, lon_max, lat_min, lat_max
STEP = 0.05
ZOOM = 5
NODATA = -32768
TERRAIN_URL = "https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png"
TERRAIN_CREDIT = ("AWS Terrain Tiles (Mapzen): SRTM, GEBCO, ETOPO1 e outras fontes abertas; "
                  "https://registry.opendata.aws/terrain-tiles/ . Licenca a confirmar antes de publicar.")


def grid_axes() -> tuple[np.ndarray, np.ndarray]:
    lon_min, lon_max, lat_min, lat_max = BBOX
    n_lon = int(round((lon_max - lon_min) / STEP)) + 1
    n_lat = int(round((lat_max - lat_min) / STEP)) + 1
    lons = lon_min + np.arange(n_lon) * STEP          # de oeste a leste
    lats = lat_max - np.arange(n_lat) * STEP          # de norte a sul
    return lons, lats


def decode_terrarium(rgb: np.ndarray) -> np.ndarray:
    """Altura em metros: R*256 + G + B/256 - 32768."""
    a = rgb.astype(np.float32)
    return a[..., 0] * 256.0 + a[..., 1] + a[..., 2] / 256.0 - 32768.0


def tile_xy(lon: float, lat: float, z: int) -> tuple[float, float]:
    """Coordenadas de tile fracionarias (Web Mercator)."""
    n = 2 ** z
    x = (lon + 180.0) / 360.0 * n
    r = math.radians(lat)
    y = (1.0 - math.log(math.tan(r) + 1.0 / math.cos(r)) / math.pi) / 2.0 * n
    return x, y


def fetch_mosaic(z: int, x0: int, x1: int, y0: int, y1: int, cache_dir: Path) -> np.ndarray:
    """Alturas (float32) dos tiles x0..x1, y0..y1 (inclusivos); PNGs ficam em cache_dir."""
    import io

    import requests
    from PIL import Image

    mosaic = np.full(((y1 - y0 + 1) * 256, (x1 - x0 + 1) * 256), np.nan, dtype=np.float32)
    for y in range(y0, y1 + 1):
        for x in range(x0, x1 + 1):
            f = cache_dir / str(z) / str(x) / f"{y}.png"
            if not f.exists():
                r = requests.get(TERRAIN_URL.format(z=z, x=x, y=y), timeout=60)
                r.raise_for_status()
                f.parent.mkdir(parents=True, exist_ok=True)
                f.write_bytes(r.content)
            img = np.asarray(Image.open(io.BytesIO(f.read_bytes())).convert("RGB"))
            mosaic[(y - y0) * 256:(y - y0 + 1) * 256, (x - x0) * 256:(x - x0 + 1) * 256] = decode_terrarium(img)
    return mosaic


def sample_heights(mosaic: np.ndarray, x0: int, y0: int, z: int, lons: np.ndarray, lats: np.ndarray) -> np.ndarray:
    """Vizinho mais proximo; NODATA fora do mosaico ou onde o pixel e nulo. Saida int16 [len(lats), len(lons)]."""
    h, w = mosaic.shape
    cols = np.array([math.floor((tile_xy(lon, lats[0], z)[0] - x0) * 256) for lon in lons])
    rows = np.array([math.floor((tile_xy(lons[0], lat, z)[1] - y0) * 256) for lat in lats])
    out = np.full((len(lats), len(lons)), NODATA, dtype=np.int16)
    ok_c = (cols >= 0) & (cols < w)
    ok_r = (rows >= 0) & (rows < h)
    sub = mosaic[np.ix_(rows[ok_r], cols[ok_c])]
    vals = np.where(np.isnan(sub), NODATA, np.rint(np.clip(np.nan_to_num(sub), -32767, 32767)))
    out[np.ix_(ok_r, ok_c)] = vals.astype(np.int16)
    return out


def plate_raster(polys, lons: np.ndarray, lats: np.ndarray) -> np.ndarray:
    """ID de placa por celula (uint32: o modelo tem IDs acima de 65535; 0 = sem placa). A primeira placa vence."""
    import shapely

    xx, yy = np.meshgrid(lons, lats)
    out = np.zeros(xx.shape, dtype=np.uint32)
    for pid, poly in polys:
        free = out == 0
        if not free.any():
            break
        inside = shapely.contains_xy(poly, xx, yy) & free
        out[inside] = pid
    return out


DEEP_CUTOFF_M = -2500  # abaixo disso a celula fica sem placa (escolha de exibicao, ver mask_deep)


def mask_deep(plates: np.ndarray, heights: np.ndarray, cutoff: int = DEEP_CUTOFF_M) -> np.ndarray:
    """Tira a placa das celulas fundas ou sem altura. Os poligonos estaticos cobrem tambem o fundo oceanico,
    e a crosta oceanica atual nao existia nas idades antigas: girar esse fundo como bloco rigido faria as
    duas margens se sobreporem sobre o oceano. Fica so a plataforma e o talude superior (>= cutoff).
    Corte de exibicao, nao interpretacao geologica; gravado em grid.json."""
    out = plates.copy()
    out[(heights < cutoff) | (heights == NODATA)] = 0
    return out


def choose_fixed(plates: np.ndarray, lons: np.ndarray) -> int:
    """Placa fixa: a mais frequente entre as colunas com lon >= 0 (lado africano)."""
    east = plates[:, lons >= 0]
    ids = east[east != 0]
    if ids.size == 0:
        raise ValueError("nenhuma placa nas colunas com lon >= 0: nao ha placa africana na grade")
    vals, counts = np.unique(ids, return_counts=True)
    return int(vals[np.argmax(counts)])


OUT_DIR = ROOT / "web" / "data" / "rift3d"
CACHE_DIR = ROOT / "data" / "raw" / "rift3d" / "terrain"
PALEO_DIR = ROOT / "web" / "data" / "paleo"


def static_polygons_in_bbox() -> list[tuple[int, object]]:
    """Poligonos estaticos do modelo que cruzam BBOX, em (lon, lat). Invalidos sao ignorados."""
    import pygplates as g
    from shapely.geometry import Polygon, box

    from pipeline import paleo

    area = box(BBOX[0], BBOX[2], BBOX[1], BBOX[3])
    out = []
    for f in g.FeatureCollection(str(paleo.STATIC)):
        pid = f.get_reconstruction_plate_id()
        for geom in f.get_geometries():
            if not isinstance(geom, g.PolygonOnSphere):
                continue
            poly = Polygon([(lon, lat) for lat, lon in geom.to_lat_lon_list()])
            if poly.is_valid and poly.intersects(area):
                out.append((pid, poly))
    return out


def rotation_table(rm, plate_ids: list[int], fixed: int, ages: list[int]) -> dict[str, list[dict]]:
    """Polo e angulo de cada placa em cada idade, relativos a placa fixa (mantida na posicao atual)."""
    table: dict[str, list[dict]] = {}
    for pid in plate_ids:
        rows = []
        for age in ages:
            # sem isso o pygplates trata placa ausente do .rot como identidade (gira com a placa fixa): inventado
            rot = rm.get_rotation(float(age), pid, 0.0, fixed_plate_id=fixed, use_identity_for_missing_plate_ids=False)
            if rot is None:
                rows = []
                break
            if rot.represents_identity_rotation():
                lat, lon, ang = 0.0, 0.0, 0.0
            else:
                lat, lon, ang = rot.get_lat_lon_euler_pole_and_angle_degrees()
            rows.append({"age": age, "pole_lat": round(lat, 6), "pole_lon": round(lon, 6), "angle_deg": round(ang, 6)})
        if rows:
            table[str(pid)] = rows
    return table


def _frame_plate_ids(paleo_dir: Path) -> set[int]:
    import json

    found: set[int] = set()
    for name in ("lineaments_0.geojson", "volcanoes_0.geojson"):
        f = paleo_dir / name
        if f.exists():
            for ft in json.loads(f.read_text(encoding="utf-8")).get("features", []):
                pid = (ft.get("properties") or {}).get("plate_id")
                if isinstance(pid, int):
                    found.add(pid)
    return found


def build(out_dir: Path = OUT_DIR, cache_dir: Path = CACHE_DIR, rm=None, paleo_dir: Path = PALEO_DIR) -> dict:
    import json
    from datetime import date

    from pipeline import paleo

    if rm is None:
        import pygplates as g

        if not paleo.ROT.exists():
            raise FileNotFoundError(f"{paleo.ROT} nao encontrado: baixe e extraia o modelo (ver README, Paleomapas).")
        rm = g.RotationModel(str(paleo.ROT))
    lons, lats = grid_axes()
    x0, y0 = (math.floor(v) for v in (tile_xy(BBOX[0], BBOX[3], ZOOM)))
    x1, y1 = (math.floor(v) for v in (tile_xy(BBOX[1], BBOX[2], ZOOM)))
    mosaic = fetch_mosaic(ZOOM, x0, x1, y0, y1, cache_dir)
    heights = sample_heights(mosaic, x0, y0, ZOOM, lons, lats)
    plates = mask_deep(plate_raster(static_polygons_in_bbox(), lons, lats), heights)
    fixed = choose_fixed(plates, lons)
    grid_plates = sorted(int(p) for p in np.unique(plates) if p != 0)
    ages_ma = paleo.ages()
    wanted = sorted(set(grid_plates) | _frame_plate_ids(paleo_dir))
    table = rotation_table(rm, wanted, fixed, ages_ma)
    omitted = [p for p in wanted if str(p) not in table]  # placas que o modelo de rotacao nao conhece

    out_dir.mkdir(parents=True, exist_ok=True)
    h, w = heights.shape
    (out_dir / "grid.bin").write_bytes(heights.astype("<i2").tobytes() + plates.astype("<u4").tobytes())
    (out_dir / "grid.json").write_text(json.dumps({
        "bbox": {"lon_min": BBOX[0], "lon_max": BBOX[1], "lat_min": BBOX[2], "lat_max": BBOX[3]},
        "step_deg": STEP, "width": w, "height": h, "nodata": NODATA, "plates": grid_plates,
        "fixed_plate": fixed, "heights_offset": 0, "plates_offset": w * h * 2, "plates_dtype": "uint32", "deep_cutoff_m": DEEP_CUTOFF_M,
    }, indent=2), encoding="utf-8")
    (out_dir / "rotations.json").write_text(json.dumps(table, separators=(",", ":")), encoding="utf-8")
    (out_dir / "index.json").write_text(json.dumps({
        "model": paleo.MODEL, "terrain": TERRAIN_CREDIT, "ages_ma": ages_ma,
        "generated": date.today().isoformat(), "layer": "rift3d", "omitted_plates": omitted,
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    return {"width": w, "height": h, "fixed_plate": fixed, "plates": grid_plates,
            "tiles": (x1 - x0 + 1) * (y1 - y0 + 1), "cells_with_plate": int((plates != 0).sum()),
            "cells_with_height": int((heights != NODATA).sum())}


if __name__ == "__main__":
    print(build())
