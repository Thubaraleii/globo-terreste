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
    """ID de placa por celula (uint16; 0 = sem placa). A primeira placa que contem a celula vence."""
    import shapely

    xx, yy = np.meshgrid(lons, lats)
    out = np.zeros(xx.shape, dtype=np.uint16)
    for pid, poly in polys:
        free = out == 0
        if not free.any():
            break
        inside = shapely.contains_xy(poly, xx, yy) & free
        out[inside] = pid
    return out


def choose_fixed(plates: np.ndarray, lons: np.ndarray) -> int:
    """Placa fixa: a mais frequente entre as colunas com lon >= 0 (lado africano)."""
    east = plates[:, lons >= 0]
    ids = east[east != 0]
    if ids.size == 0:
        raise ValueError("nenhuma placa nas colunas com lon >= 0: nao ha placa africana na grade")
    vals, counts = np.unique(ids, return_counts=True)
    return int(vals[np.argmax(counts)])
