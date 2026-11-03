"""Ranking das zonas tectonicas por momento sismico acumulado.

Distancias sao geodesicas na esfera (raio medio da Terra): cada aresta do
limite e um arco de circulo maximo e a distancia sismo-aresta e calculada
com vetores unitarios 3D. Isso nao depende de longitude, entao o
antimeridiano nao e caso especial (lon -179.9 fica a 0.2 grau de 179.9).
Erro em relacao ao elipsoide: < 0.5%.
"""
import geopandas as gpd
import numpy as np
import pandas as pd
import shapely

from pipeline.common.geom import to_wgs84
from pipeline.common.model import CRS, SCHEMAS

EARTH_RADIUS_KM = 6371.0088
_CHUNK = 500_000  # pares por bloco sismos x arestas


def seismic_moment(mw: float) -> float:
    """Momento sismico (N*m) a partir da magnitude de momento Mw."""
    return 10 ** (1.5 * mw + 9.1)


def _unit_vectors(lon, lat) -> np.ndarray:
    lon, lat = np.radians(lon), np.radians(lat)
    return np.column_stack(
        [np.cos(lat) * np.cos(lon), np.cos(lat) * np.sin(lon), np.sin(lat)]
    )


def _angle(u: np.ndarray, v: np.ndarray) -> np.ndarray:
    """Angulo (rad) entre vetores unitarios, estavel para angulos pequenos."""
    return np.arctan2(np.linalg.norm(np.cross(u, v), axis=-1), np.sum(u * v, axis=-1))


def _edges(geom) -> tuple[np.ndarray, np.ndarray]:
    """Extremidades (vetores unitarios) das arestas de cada parte da linha."""
    starts, ends = [], []
    for part in shapely.get_parts(geom):
        xy = shapely.get_coordinates(part)
        if len(xy) == 1:  # parte degenerada: um ponto vira aresta nula
            xy = np.vstack([xy, xy])
        v = _unit_vectors(xy[:, 0], xy[:, 1])
        starts.append(v[:-1])
        ends.append(v[1:])
    return np.vstack(starts), np.vstack(ends)


def _dist_to_edges(p: np.ndarray, a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Menor angulo de cada ponto p (m,3) ao conjunto de arcos a-b (e,3)."""
    n = np.cross(a, b)
    norm = np.linalg.norm(n, axis=1)
    ok = norm > 1e-15
    n[ok] /= norm[ok, None]
    P = p[:, None, :]
    s = p @ n.T  # (m,e) seno do angulo ao circulo maximo (com sinal)
    foot = P - s[..., None] * n[None]  # projecao no plano do circulo maximo
    # o pe da perpendicular esta dentro do arco se ficar entre a e b
    inside = (
        ok[None]
        & (np.einsum("mek,ek->me", np.cross(a[None], foot), n) >= 0)
        & (np.einsum("mek,ek->me", np.cross(foot, b[None]), n) >= 0)
    )
    cross_track = np.arcsin(np.clip(np.abs(s), 0, 1))
    ends = np.minimum(_angle(P, a[None]), _angle(P, b[None]))
    return np.where(inside, cross_track, ends).min(axis=1)


def _nearest_distances(p: np.ndarray, geom, max_angle: float) -> np.ndarray:
    """Angulo de cada ponto ao segmento; inf onde certamente > max_angle."""
    a, b = _edges(geom)
    out = np.full(len(p), np.inf)
    # pre-filtro por calota: todo ponto do segmento esta a <= radius do centro
    center = np.vstack([a, b]).sum(axis=0)
    cnorm = np.linalg.norm(center)
    if cnorm > 1e-9:
        center /= cnorm
        radius = max(_angle(a, center).max(), _angle(b, center).max())
        radius += _angle(a, b).max() / 2
        cand = np.flatnonzero(_angle(p, center[None]) <= radius + max_angle)
    else:
        cand = np.arange(len(p))
    step = max(1, _CHUNK // len(a))
    for i in range(0, len(cand), step):
        idx = cand[i:i + step]
        out[idx] = _dist_to_edges(p[idx], a, b)
    return out


def _valid_quakes(quakes: pd.DataFrame) -> pd.DataFrame:
    lat = pd.to_numeric(quakes["lat"], errors="coerce")
    lon = pd.to_numeric(quakes["lon"], errors="coerce")
    mw = pd.to_numeric(quakes["mw"], errors="coerce")
    keep = lat.abs().le(90) & lon.abs().le(180) & np.isfinite(mw)
    return pd.DataFrame(
        {"lat": lat[keep], "lon": lon[keep], "mw": mw[keep], "time": quakes["time"][keep]}
    )


def rank_zones(
    boundaries: gpd.GeoDataFrame,
    quakes: pd.DataFrame,
    source_id: str,
    buffer_km: float = 100,
    top_n: int = 30,
) -> gpd.GeoDataFrame:
    """Soma o momento sismico dos sismos atribuidos a cada segmento (o mais
    proximo, se dentro de `buffer_km`) e devolve os `top_n` maiores.

    Linhas de `quakes` com lat/lon/mw invalidos sao descartadas. Segmentos
    sem sismo nao entram. Empates em momento desempatam por `name`.
    period_start/period_end sao o min/max de `time` dos sismos validos.
    """
    segs = to_wgs84(boundaries).reset_index(drop=True)
    q = _valid_quakes(quakes)
    p = _unit_vectors(q["lon"].to_numpy(), q["lat"].to_numpy())
    max_angle = buffer_km / EARTH_RADIUS_KM

    best = np.full(len(p), np.inf)
    owner = np.full(len(p), -1)
    for i, geom in enumerate(segs.geometry):
        if geom is None or geom.is_empty or len(p) == 0:
            continue
        d = _nearest_distances(p, geom, max_angle)
        closer = d < best
        best[closer], owner[closer] = d[closer], i

    hit = best <= max_angle
    moment = pd.Series(seismic_moment(q["mw"].to_numpy()[hit])).groupby(owner[hit]).sum()

    out = segs.loc[moment.index, ["name", "geometry"]].copy()
    out["moment_total"] = moment.to_numpy(dtype="float64")
    out = out.sort_values(["moment_total", "name"], ascending=[False, True], kind="stable")
    out = out.head(top_n).reset_index(drop=True)
    out["rank"] = pd.Series(range(1, len(out) + 1), dtype="Int64")
    out["period_start"] = q["time"].min() if len(q) else None
    out["period_end"] = q["time"].max() if len(q) else None
    out["source_id"] = source_id
    return gpd.GeoDataFrame(out[SCHEMAS["tectonic_zones"]], geometry="geometry", crs=CRS)
