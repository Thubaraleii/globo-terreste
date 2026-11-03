"""Fontes reais do primeiro recorte (arquivos baixados em 2026-11-03).

`registry()` devolve as `Source` usadas por padrao pelo CLI
(`python -m pipeline.build`). Cada loader recebe o caminho do arquivo bruto
registrado em `raw_file` e devolve o quadro ja no esquema da camada; as
contagens vao em `gdf.attrs` (viram `BuildReport.notes`).

Decisoes (ver README, "Fontes de dados"):
- GVP: GeoJSON do WFS; coordenadas de `Latitude`/`Longitude` (o membro `crs`
  do arquivo e o URN EPSG:4326, cuja ordem de eixos e lat/lon, mas as
  coordenadas vem lon/lat; usar as propriedades evita a ambiguidade).
- Tectonica: catalogo USGS M>=6 so com magnitudes de momento (familia Mw);
  limites PB2002 dissolvidos por `Name` (par de placas). O arquivo PB2002 e
  lido de `<raw>/pb2002/boundaries.json` mas NAO entra no hash do cache
  (o hash e so do CSV do USGS): se ele mudar, rode com `--force`.
- GLiM: lido direto do zip (/vsizip/), so `xx IN ('vb','pb')` (basicas
  vulcanicas e plutonicas) por memoria; `unit_id` = FID do arquivo.
- GEOROC: um `Source` por CSV (cp1252); so analises de rocha total ("WR"),
  uma linha por amostra (SAMPLE NAME + CITATIONS), caixa de coordenadas vira
  centro + incerteza; sem coordenada nao e geocodificada aqui. O mapeamento
  de rochas (`rock_mapping_v2.csv`) tambem nao entra no hash: mudou, `--force`.
"""
import json
import re
import warnings
from collections import Counter
from functools import partial
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely
from pyogrio import read_dataframe
from shapely.geometry import shape

from pipeline.build import Source
from pipeline.common.model import CRS
from pipeline.glim import normalize_glim
from pipeline.gvp import normalize_gvp
from pipeline.rockmap import load_mapping, normalize_rock_name
from pipeline.samples import EMPTY_NAME, normalize_samples
from pipeline.tectonics import DEFAULT_BUFFER_KM, rank_zones

ACQUISITION_DATE = "2026-11-03"
ROOT = Path(__file__).resolve().parent.parent
MAPPING_V2 = ROOT / "data" / "curated" / "rock_mapping_v2.csv"

GVP_FILE = "gvp/holocene_volcanoes.geojson"
USGS_FILE = "usgs/m6_1900_2026-11-03.csv"
PB2002_FILE = "pb2002/boundaries.json"
PB2002_PLATES_FILE = "pb2002/plates.json"
PB2002_PLATES_URL = ("https://raw.githubusercontent.com/fraxen/tectonicplates/master/GeoJSON/"
                     "PB2002_plates.json")
GLIM_FILE = "glim/LiMW_GIS_2015.gdb.zip"
GLIM_GDB = "LiMW_GIS 2015.gdb"   # pasta dentro do zip
GLIM_LAYER = "GLiM_export"
GLIM_WHERE = "xx IN ('vb','pb')"
GEOROC_DIR = "georoc"
GEOROC_FILES = tuple(f"2026-09-2JETOA_{n}.csv" for n in (
    "ALKALI_BASALT_part1", "ALKALI_BASALT_part2", "ANKARAMITE",
    *(f"BASALT_part{i}" for i in range(1, 10)),
    "BASANITE", "CALC-ALKALI_BASALT", "CLINOPYROXENITE", "DOLERITE", "DUNITE",
    "GABBRO_part1", "GABBRO_part2", "GABBRONORITE", "HARZBURGITE", "KOMATIITE",
    "LHERZOLITE", "NORITE", "ORTHOPYROXENITE", "PERIDOTITE", "PICROBASALT",
    "PYROXENITE", "SUBALKALI_BASALT", "THOLEIITIC_BASALT_part1",
    "THOLEIITIC_BASALT_part2", "TRACHYBASALT", "TRANSITIONAL_BASALT",
    "WEBSTERITE", "WEHRLITE",
))

USGS_URL = ("https://earthquake.usgs.gov/fdsnws/event/1/query?format=csv&starttime=1900-01-01"
            "&endtime=2026-11-03&minmagnitude=6&orderby=time-asc")
PB2002_REPO = "https://github.com/fraxen/tectonicplates"

# magType da familia de magnitude de momento (comparacao sem caixa).
MW_FAMILY = frozenset({"mw", "mww", "mwc", "mwb", "mwr"})
TOP_ZONES = 30
# epicentros de megathrusts ficam a 100-200 km da linha da fossa (Chile 1960: 109 km,
# Tohoku 2011: 137 km, Alasca 1964: 196 km do PB2002); ver pipeline.tectonics
ZONE_BUFFER_KM = DEFAULT_BUFFER_KM
MAX_BOX_DEG = 1.0
UNMAPPED_TOP = 20
EARTH_RADIUS_M = 6371008.8


# --- GVP --------------------------------------------------------------------

def load_gvp(path: Path) -> gpd.GeoDataFrame:
    """GeoJSON do WFS do GVP -> camada volcanoes (via `normalize_gvp`)."""
    fc = json.loads(Path(path).read_text(encoding="utf-8"))
    props = pd.DataFrame([f["properties"] for f in fc["features"]])
    if "Last_Eruption_Year" in props.columns:
        props["Last_Eruption_Year"] = props["Last_Eruption_Year"].astype("Int64")
    return normalize_gvp(props, "gvp")


# --- tectonica --------------------------------------------------------------

def filter_moment_magnitudes(quakes: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """So linhas com magType da familia Mw; devolve tambem a contagem das
    excluidas por magType original (vazio -> "<vazio>")."""
    mt = quakes["magType"].astype("object")
    blank = mt.map(lambda v: v is None or (not isinstance(v, str) and pd.isna(v))
                   or str(v).strip() == "")
    key = mt.where(~blank, "").map(lambda v: str(v).strip().lower())
    keep = key.isin(MW_FAMILY) & ~blank
    excluded = Counter(EMPTY_NAME if b else str(v).strip() for v, b in zip(mt[~keep], blank[~keep]))
    return quakes[keep], dict(excluded)


def read_boundaries(path: Path) -> gpd.GeoDataFrame:
    """PB2002 (GeoJSON sem membro crs -> WGS84 lon/lat, RFC 7946)."""
    fc = json.loads(Path(path).read_text(encoding="utf-8"))
    props = pd.DataFrame([f["properties"] for f in fc["features"]])
    geoms = [shape(f["geometry"]) for f in fc["features"]]
    return gpd.GeoDataFrame(props, geometry=geoms, crs=CRS)


def dissolve_boundaries(segments: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Uma (Multi)LineString por `Name` (codigo do par de placas, ex. 'PA-NA').
    `plate_a`/`plate_b` = PlateA/PlateB do primeiro segmento (None se ausentes)."""
    rows = []
    for name, group in segments.groupby("Name", sort=True):
        parts = [p for g in group.geometry if g is not None and not g.is_empty
                 for p in shapely.get_parts(g)]
        merged = shapely.line_merge(shapely.MultiLineString(parts))
        row = {"name": name, "geometry": merged}
        for col, key in (("plate_a", "PlateA"), ("plate_b", "PlateB")):
            vals = group[key].dropna() if key in group.columns else []
            row[col] = vals.iloc[0] if len(vals) else None
        rows.append(row)
    return gpd.GeoDataFrame(rows, columns=["name", "plate_a", "plate_b", "geometry"],
                            geometry="geometry", crs=CRS)


def read_plate_names(path: Path) -> dict[str, str]:
    """Codigo da placa -> nome (plates.json do PB2002). Codigo ausente, vazio ou
    com nomes conflitantes fica de fora (o rotulo cai no codigo bruto)."""
    path = Path(path)
    if not path.exists():
        return {}
    fc = json.loads(path.read_text(encoding="utf-8"))
    seen: dict[str, set] = {}
    for f in fc["features"]:
        props = f.get("properties") or {}
        code, name = props.get("Code"), props.get("PlateName")
        if isinstance(code, str) and code.strip() and isinstance(name, str) and name.strip():
            seen.setdefault(code.strip(), set()).add(name.strip())
    return {c: next(iter(n)) for c, n in seen.items() if len(n) == 1}


def zone_label(name: str, plate_a, plate_b, plates: dict[str, str]) -> str:
    """'Pacific – Okhotsk (PA\\OK)': nomes das duas placas + o codigo `Name` do PB2002.
    Placa sem nome conhecido entra com o codigo bruto; sem codigo, so o `Name`."""
    def part(code):
        if not isinstance(code, str) or not code.strip():
            return None
        return plates.get(code.strip(), code.strip())
    a, b = part(plate_a), part(plate_b)
    if a is None or b is None:
        return name
    return f"{a} – {b} ({name})"


def load_tectonics(path: Path) -> gpd.GeoDataFrame:
    """Catalogo USGS (CSV FDSN) + PB2002 -> top 30 pares de placas por momento."""
    path = Path(path)
    segments = read_boundaries(path.parent.parent / PB2002_FILE)
    pairs = dissolve_boundaries(segments)
    plates = read_plate_names(path.parent.parent / PB2002_PLATES_FILE)
    pairs["name"] = [zone_label(n, a, b, plates)
                     for n, a, b in zip(pairs["name"], pairs["plate_a"], pairs["plate_b"])]
    pairs = pairs[["name", "geometry"]]
    cat = pd.read_csv(path, dtype=str, keep_default_na=False,
                      usecols=["time", "latitude", "longitude", "mag", "magType"])
    mw, excluded = filter_moment_magnitudes(cat)
    quakes = pd.DataFrame({"lat": mw["latitude"], "lon": mw["longitude"],
                           "mw": mw["mag"], "time": mw["time"]})
    zones = rank_zones(pairs, quakes, source_id="tectonics",
                       top_n=TOP_ZONES, buffer_km=ZONE_BUFFER_KM)
    zones.attrs.update({
        "quakes_read": len(cat),
        "quakes_used": len(mw),
        "quakes_excluded_magtype": excluded,
        "boundary_segments": len(segments),
        "boundary_pairs": len(pairs),
    })
    return zones


# --- GLiM -------------------------------------------------------------------

def _vsizip(path: Path) -> str:
    return f"/vsizip/{Path(path).resolve().as_posix()}/{GLIM_GDB}"


def read_glim(path: Path, where: str | None = GLIM_WHERE,
              max_features: int | None = None) -> gpd.GeoDataFrame:
    """Le a camada GLiM_export do zip, com filtro `where` aplicado pelo GDAL.
    Coluna `unit_fid` = "glim:fid:<FID>" (IDENTITY_ nao e unico na fonte)."""
    with warnings.catch_warnings():
        # aviso de desempenho do GDAL (poligonos com >100 partes); nao altera dados
        warnings.filterwarnings("ignore", message=r"organizePolygons\(\)", category=RuntimeWarning)
        gdf = read_dataframe(_vsizip(path), layer=GLIM_LAYER, where=where, columns=["xx"],
                             fid_as_index=True, max_features=max_features)
    gdf["unit_fid"] = [f"glim:fid:{int(i)}" for i in gdf.index]
    return gdf.reset_index(drop=True)


def load_glim(path: Path) -> gpd.GeoDataFrame:
    raw = read_glim(path)
    n = len(raw)
    out = normalize_glim(raw, "glim", columns={"xx": "code", "unit_fid": "id"})
    del raw
    out.attrs.update({"where": GLIM_WHERE, "units_read": n})
    return out


# --- GEOROC -----------------------------------------------------------------

GEOROC_COLUMNS = ["CITATIONS", "LATITUDE MIN", "LATITUDE MAX", "LONGITUDE MIN",
                  "LONGITUDE MAX", "SAMPLE NAME", "ROCK NAME", "MATERIAL", "UNIQUE_ID"]
_TRAILING_TAG = re.compile(r"\s*\[\d+\]\s*$")
_ANY_TAG = re.compile(r"\s*\[\d+\]")


def strip_citation_tag(value: str) -> str:
    """Remove so a etiqueta de citacao FINAL (' [123]'); o resto fica como veio."""
    return _TRAILING_TAG.sub("", value).strip()


def _wrap_lon(lon: np.ndarray) -> np.ndarray:
    return np.where(lon > 180, lon - 360, np.where(lon < -180, lon + 360, lon))


def _haversine_m(lat1, lon1, lat2, lon2) -> np.ndarray:
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dl = np.radians(lon2 - lon1)
    h = np.sin((p2 - p1) / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return EARTH_RADIUS_M * 2 * np.arcsin(np.sqrt(np.clip(h, 0, 1)))


def georoc_coordinates(df: pd.DataFrame) -> pd.DataFrame:
    """lat, lon, uncertainty_m, is_box, too_large, no_coords a partir de
    LATITUDE/LONGITUDE MIN/MAX. MIN e MAX sao tratados como dois cantos (no
    arquivo real MIN > MAX acontece); a diferenca de longitude considera o
    antimeridiano. Ponto (cantos iguais): incerteza nula. Caixa: centro e
    metade da diagonal (grande circulo). Caixa > 1 grau em lat ou lon:
    `too_large` (lat/lon ficam NaN)."""
    num = {c: pd.to_numeric(df[c], errors="coerce").to_numpy(dtype="float64")
           for c in ("LATITUDE MIN", "LATITUDE MAX", "LONGITUDE MIN", "LONGITUDE MAX")}
    lat_a = np.where(np.isnan(num["LATITUDE MIN"]), num["LATITUDE MAX"], num["LATITUDE MIN"])
    lat_b = np.where(np.isnan(num["LATITUDE MAX"]), lat_a, num["LATITUDE MAX"])
    lon_a = np.where(np.isnan(num["LONGITUDE MIN"]), num["LONGITUDE MAX"], num["LONGITUDE MIN"])
    lon_b = np.where(np.isnan(num["LONGITUDE MAX"]), lon_a, num["LONGITUDE MAX"])
    blank = df[["LATITUDE MIN", "LATITUDE MAX", "LONGITUDE MIN", "LONGITUDE MAX"]].apply(
        lambda s: s.astype("object").map(lambda v: v is None or str(v).strip() == ""
                                         or (not isinstance(v, str) and pd.isna(v))))
    no_coords = blank.all(axis=1).to_numpy()
    in_range = ((np.abs(lat_a) <= 90) & (np.abs(lat_b) <= 90)
                & (np.abs(lon_a) <= 180) & (np.abs(lon_b) <= 180))
    with np.errstate(invalid="ignore"):
        dlon = ((lon_b - lon_a + 180) % 360) - 180
        dlat = np.abs(lat_b - lat_a)
        is_box = in_range & ((dlat > 0) | (np.abs(dlon) > 0))
        too_large = in_range & ((dlat > MAX_BOX_DEG) | (np.abs(dlon) > MAX_BOX_DEG))
        lat = np.where(in_range & ~too_large, (lat_a + lat_b) / 2, lat_a)
        lon = np.where(in_range & ~too_large, _wrap_lon(lon_a + dlon / 2), lon_a)
        lat = np.where(too_large, np.nan, lat)
        lon = np.where(too_large, np.nan, lon)
        unc = np.where(is_box & ~too_large,
                       _haversine_m(lat_a, lon_a, lat_b, lon_a + dlon) / 2, np.nan)
    return pd.DataFrame({"lat": lat, "lon": lon, "uncertainty_m": unc, "is_box": is_box,
                         "too_large": too_large, "no_coords": no_coords}, index=df.index)


def load_georoc(path: Path, source_id: str | None = None,
                mapping: dict[str, str] | None = None) -> gpd.GeoDataFrame:
    """Um CSV "Rocks" do GEOROC 2.0 -> camada samples (via `normalize_samples`).

    Ordem: linhas de rodape (sem UNIQUE_ID: abreviacoes e referencias) saem;
    so MATERIAL 'WR' (rocha total) fica; uma linha por amostra (SAMPLE NAME +
    CITATIONS, a primeira do arquivo); coordenadas (ver `georoc_coordinates`);
    classe pelo mapeamento v2 (nome sem a etiqueta final de citacao).
    """
    path = Path(path)
    source_id = source_id or f"georoc:{path.stem}"
    mapping = load_mapping(MAPPING_V2) if mapping is None else mapping
    df = pd.read_csv(path, encoding="cp1252", dtype=str, keep_default_na=False,
                     low_memory=False, usecols=GEOROC_COLUMNS)
    df = df.astype("object")

    footer = df["UNIQUE_ID"].map(lambda v: str(v).strip() == "")
    data = df[~footer]
    material = data["MATERIAL"].map(strip_citation_tag)
    is_wr = material.eq("WR")
    dropped_material = Counter(_ANY_TAG.sub("", m).strip() or EMPTY_NAME
                               for m in material[~is_wr])
    wr = data[is_wr].copy()
    wr["_sample"] = wr["SAMPLE NAME"].map(strip_citation_tag)
    samples = wr.drop_duplicates(subset=["_sample", "CITATIONS"], keep="first")

    coords = georoc_coordinates(samples)
    names = samples["ROCK NAME"].map(lambda v: strip_citation_tag(v) or None)
    frame = pd.DataFrame({
        "id": samples["UNIQUE_ID"].map(lambda v: f"georoc:{str(v).strip()}"),
        "rock_name": names,
        "lat": coords["lat"], "lon": coords["lon"],
    }, index=samples.index)
    result = normalize_samples(frame, source_id,
                               {"id": "id", "rock_name": "rock_name", "lat": "lat", "lon": "lon"},
                               mapping)
    if len(result.pending):  # sem coluna de localidade nada vai para pendentes
        raise AssertionError("GEOROC: pendentes inesperados")

    mapped = names.map(lambda s: normalize_rock_name(s) in mapping if s else False)
    pending = int((mapped & coords["no_coords"]).sum())
    too_large = int((mapped & coords["too_large"]).sum())

    located = result.located
    unc = pd.Series(coords["uncertainty_m"].to_numpy(), index=frame["id"].to_numpy())
    located["coord_uncertainty_m"] = located["id"].map(unc).astype("float64")
    box_ids = set(frame["id"][coords["is_box"] & ~coords["too_large"]])

    located.attrs.update({
        "rows_read": int(len(data)),
        "footer_rows": int(footer.sum()),
        "dropped_material": dict(dropped_material),
        "dropped_duplicate_rows": int(len(wr) - len(samples)),
        "samples": int(len(samples)),
        "unmapped_total": int(sum(result.unmapped.values())),
        "unmapped_distinct": len(result.unmapped),
        "unmapped_top": dict(result.unmapped.most_common(UNMAPPED_TOP)),
        "pending_without_coords": pending,
        "dropped_box_too_large": too_large,
        "dropped_invalid_coords": int(result.dropped_invalid - pending - too_large),
        "box_centre": int(located["id"].isin(box_ids).sum()),
        "located": int(len(located)),
    })
    return located


# --- registro ---------------------------------------------------------------

GVP_META = {
    "institution": "Smithsonian Institution, Global Volcanism Program",
    "source_url": "https://volcano.si.edu/",
    "license": "Termos de uso próprios do GVP (ver volcano.si.edu); citação obrigatória",
    "attribution": "Global Volcanism Program, Volcanoes of the World, Smithsonian Institution "
                   "(dados do WFS baixados em 2026-11-03)",
    "acquisition_date": ACQUISITION_DATE,
    "original_scale": None,
}
TECTONICS_META = {
    "institution": "USGS (catálogo ComCat) e P. Bird (PB2002)",
    # o painel da web mostra um unico link; o repositorio do PB2002 vai na atribuicao
    "source_url": USGS_URL,
    "license": "USGS: domínio público (verificar termos); PB2002: Open Data Commons Attribution 1.0",
    "attribution": "Bird, P. (2003) An updated digital model of plate boundaries, G-cubed 4(3), "
                   "1027, doi:10.1029/2001GC000252; U.S. Geological Survey, Earthquake Catalog. "
                   f"PB2002 em GeoJSON (limites e nomes das placas, boundaries.json e plates.json): {PB2002_REPO}",
    "acquisition_date": ACQUISITION_DATE,
    "original_scale": None,
}
GLIM_META = {
    "institution": "Universität Hamburg (Hartmann & Moosdorf)",
    "source_url": "https://www.geo.uni-hamburg.de/en/geologie/forschung/aquatische-geochemie/glim.html",
    "license": "NÃO declarada na fonte — uso local; não publicar sem confirmar a licença",
    "attribution": "Hartmann, J. & Moosdorf, N. (2012) The new global lithological map database "
                   "GLiM, G-cubed 13, Q12004, doi:10.1029/2012GC004370",
    "acquisition_date": ACQUISITION_DATE,
    "original_scale": "~1:3.750.000 (média; 92 mapas regionais)",
}
GEOROC_META = {
    "institution": "GEOROC (Georg-August-Universität Göttingen)",
    "source_url": "https://georoc.eu/",
    "license": "CC BY-SA 4.0 (uso científico e educacional); citar o conjunto de dados "
               "(DOI 10.25625/2JETOA, v15) e as referências originais",
    "attribution": "GEOROC Rocks dataset DOI 10.25625/2JETOA, v15 (2026-09)",
    "acquisition_date": ACQUISITION_DATE,
    "original_scale": None,
}


def georoc_source_id(filename: str) -> str:
    return f"georoc:{Path(filename).stem}"


def registry() -> list[Source]:
    """Fontes reais na ordem de processamento (as grandes por ultimo)."""
    sources = [
        Source("gvp", GVP_FILE, "volcanoes", load_gvp, dict(GVP_META)),
        Source("tectonics", USGS_FILE, "tectonic_zones", load_tectonics, dict(TECTONICS_META)),
    ]
    for name in GEOROC_FILES:
        sid = georoc_source_id(name)
        sources.append(Source(sid, f"{GEOROC_DIR}/{name}", "samples",
                              partial(load_georoc, source_id=sid), dict(GEOROC_META)))
    sources.append(Source("glim", GLIM_FILE, "geo_units", load_glim, dict(GLIM_META)))
    return sources
