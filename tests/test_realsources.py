"""Loaders das fontes reais com entradas SINTETICAS no formato dos arquivos
baixados (nenhum dado real entra no repositorio)."""
import json
import math
import zipfile
from pathlib import Path

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import LineString, MultiLineString, box

from pipeline import realsources as rs
from pipeline.build import Source
from pipeline.common.model import CRS, SCHEMAS

EARTH_RADIUS_M = 6371008.8


# --- GVP --------------------------------------------------------------------

def _gvp_geojson(path: Path) -> Path:
    def feat(name, lat, lon, year):
        return {"type": "Feature", "geometry": {"type": "Point", "coordinates": [lon, lat]},
                "properties": {"Volcano_Number": 1, "Volcano_Name": name, "Country": "Pais X",
                               "Primary_Volcano_Type": "Shield", "Last_Eruption_Year": year,
                               "Latitude": lat, "Longitude": lon, "Region": "R"}}
    fc = {"type": "FeatureCollection",
          "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::4326"}},
          "features": [feat("Alfa", 50.17, 6.85, -8300), feat("Beta", -10.0, 120.5, None)]}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(fc), encoding="utf-8")
    return path


def test_load_gvp_reads_wfs_geojson_properties(tmp_path):
    out = rs.load_gvp(_gvp_geojson(tmp_path / "gvp" / "v.geojson"))
    assert list(out.columns) == SCHEMAS["volcanoes"]
    assert out.crs == CRS
    alfa = out[out["name"] == "Alfa"].iloc[0]
    assert alfa["last_eruption"] == "-8300"
    assert alfa["type"] == "Shield" and alfa["country"] == "Pais X"
    # coordenadas vem de Latitude/Longitude (x = lon, y = lat)
    assert (alfa.geometry.x, alfa.geometry.y) == pytest.approx((6.85, 50.17))
    assert pd.isna(out[out["name"] == "Beta"].iloc[0]["last_eruption"])
    assert out.attrs["dropped_no_coords"] == 0


# --- tectonica --------------------------------------------------------------

def _catalog(path: Path, rows) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows, columns=["time", "latitude", "longitude", "depth", "mag", "magType"]
                 ).to_csv(path, index=False)
    return path


def _boundaries(path: Path) -> Path:
    def feat(name, coords, typ=""):
        a, b = name[:2], name[3:]
        return {"type": "Feature", "geometry": {"type": "LineString", "coordinates": coords},
                "properties": {"LAYER": "plate boundary", "Name": name, "Source": "x",
                               "PlateA": a, "PlateB": b, "Type": typ}}
    fc = {"type": "FeatureCollection", "features": [
        feat("PA-NA", [[-150, 0], [-140, 0]]),
        feat("PA-NA", [[-140, 0], [-130, 0]]),
        feat("AF-AN", [[10, -50], [20, -50]], "subduction"),
    ]}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(fc), encoding="utf-8")
    return path


def test_mw_filter_keeps_moment_magnitudes_case_insensitive_and_counts_others():
    q = pd.DataFrame({"magType": ["mw", "mww", "Mw", "mwc", "mwb", "mwr", "ms", "mb", "mB", None],
                      "mag": [6.0] * 10})
    kept, excluded = rs.filter_moment_magnitudes(q)
    assert len(kept) == 6
    assert excluded == {"ms": 1, "mb": 1, "mB": 1, "<vazio>": 1}


def test_dissolve_boundaries_one_row_per_name():
    gdf = gpd.GeoDataFrame({"Name": ["PA-NA", "PA-NA", "AF-AN"]}, geometry=[
        LineString([(0, 0), (1, 0)]), LineString([(1, 0), (2, 0)]), LineString([(5, 5), (6, 5)]),
    ], crs=CRS)
    out = rs.dissolve_boundaries(gdf)
    assert sorted(out["name"]) == ["AF-AN", "PA-NA"]
    pa = out[out["name"] == "PA-NA"].geometry.iloc[0]
    assert pa.length == pytest.approx(2.0)
    assert out.crs == CRS


def test_dissolve_keeps_disjoint_parts_as_multilinestring():
    gdf = gpd.GeoDataFrame({"Name": ["PA-NA", "PA-NA"]}, geometry=[
        LineString([(179, 0), (180, 0)]), LineString([(-180, 0), (-179, 0)]),
    ], crs=CRS)
    geom = rs.dissolve_boundaries(gdf).geometry.iloc[0]
    assert isinstance(geom, MultiLineString)
    assert len(geom.geoms) == 2


def test_load_tectonics_ranks_dissolved_pairs_with_mw_only(tmp_path):
    raw = tmp_path / "raw"
    _boundaries(raw / "pb2002" / "boundaries.json")
    csv = _catalog(raw / "usgs" / "cat.csv", [
        ["2000-01-01T00:00:00.000Z", 0.1, -145, 10, 8.0, "mww"],
        ["2001-01-01T00:00:00.000Z", 0.1, -135, 10, 7.0, "mw"],
        ["2002-01-01T00:00:00.000Z", -50.1, 15, 10, 7.5, "Mw"],
        ["1950-01-01T00:00:00.000Z", 0.1, -145, 10, 9.5, "ms"],   # fora: nao e Mw
        ["1960-01-01T00:00:00.000Z", -50.1, 15, 10, 9.0, "mb"],    # fora
    ])
    out = rs.load_tectonics(csv)
    assert list(out.columns) == SCHEMAS["tectonic_zones"]
    assert out.crs == CRS
    assert list(out["name"]) == ["PA-NA", "AF-AN"]   # 10^(1.5*8) + 10^(1.5*7) > 10^(1.5*7.5)
    assert list(out["rank"]) == [1, 2]
    assert out["period_start"].iloc[0] == "2000-01-01T00:00:00.000Z"   # sismos ms/mb nao entram
    assert out.attrs["quakes_used"] == 3
    assert out.attrs["quakes_excluded_magtype"] == {"ms": 1, "mb": 1}
    assert out.attrs["boundary_segments"] == 3
    assert out.attrs["boundary_pairs"] == 2


# --- GLiM -------------------------------------------------------------------

def _glim_zip(tmp_path: Path) -> Path:
    gdb = tmp_path / "build" / "LiMW_GIS 2015.gdb"
    gdb.parent.mkdir(parents=True)
    src = gpd.GeoDataFrame({
        "IDENTITY_": [7, 7, None],
        "Litho": ["vbpyxx", "pbxxxx", "suxxxx"],
        "xx": ["vb", "pb", "su"],
    }, geometry=[box(0, 0, 1e5, 1e5), box(2e5, 0, 3e5, 1e5), box(4e5, 0, 5e5, 1e5)],
        crs="ESRI:54012")
    src.to_file(gdb, layer="GLiM_export", driver="OpenFileGDB")
    zpath = tmp_path / "glim" / "LiMW_GIS_2015.gdb.zip"
    zpath.parent.mkdir()
    with zipfile.ZipFile(zpath, "w") as z:
        for f in gdb.iterdir():
            z.write(f, f"LiMW_GIS 2015.gdb/{f.name}")
    return zpath


def test_load_glim_reads_zip_restricted_to_basic_igneous(tmp_path):
    out = rs.load_glim(_glim_zip(tmp_path))
    assert list(out.columns) == SCHEMAS["geo_units"]
    assert out.crs == CRS
    assert sorted(out["lith_original"]) == ["pb", "vb"]
    assert sorted(out["lith_class"]) == ["basic_plutonic", "basic_volcanic"]
    # id estavel: FID do arquivo (nao IDENTITY_, que nao e unico)
    assert sorted(out["unit_id"]) == ["glim:fid:1", "glim:fid:2"]
    assert out.attrs["where"] == "xx IN ('vb','pb')"
    assert out.attrs["units_read"] == 2


# --- GEOROC -----------------------------------------------------------------

GEOROC_HEADER = ["CITATIONS", "TECTONIC SETTING", "LOCATION", "LOCATION COMMENT",
                 "LATITUDE MIN", "LATITUDE MAX", "LONGITUDE MIN", "LONGITUDE MAX",
                 "LAND OR SEA", "SAMPLE NAME", "ROCK NAME", "ROCK TYPE", "MATERIAL",
                 "UNIQUE_ID", "SIO2(WT%)"]


def _georoc_csv(path: Path) -> Path:
    def row(cit, sample, rock, mat, uid, lat0, lat1, lon0, lon1, loc="ILHA RÉUNION"):
        return [cit, "OCEAN ISLAND", loc, "", lat0, lat1, lon0, lon1, "SAE",
                sample, rock, "VOL", mat, uid, "47.1"]
    rows = [
        row("[12]", "s_A [12]", "ALKALI BASALT [12]", "WR [12]", "101", "-21.2", "-21.2", "55.7", "55.7"),
        row("[12]", "s_A [12]", "ALKALI BASALT [12]", "WR [12]", "102", "-21.2", "-21.2", "55.7", "55.7"),
        row("[12]", "s_A [12]", "ALKALI BASALT [12]", "GL [12]", "103", "-21.2", "-21.2", "55.7", "55.7"),
        # caixa com MIN > MAX (como no arquivo real): centro + incerteza
        row("[13]", "s_B [13]", "BASALT [13]", "WR [13]", "201", "10.5", "10", "20", "20.5"),
        # caixa > 1 grau: descartada
        row("[13]", "s_C [13]", "BASALT [13]", "WR [13]", "301", "40", "42", "20", "20"),
        # sem coordenadas: pendente (nao geocodificada neste run)
        row("[14]", "s_D [14]", "BASALT [14]", "WR [14]", "401", "", "", "", ""),
        # nome sem classe
        row("[15]", "s_E [15]", "BASALTIC-ANDESITE [15]", "WR [15]", "501", "1", "1", "2", "2"),
        # mesmo nome de amostra, outra citacao: outra amostra
        row("[16]", "s_A [16]", "DUNITE, XENOLITH [16] / DUNITE", "WR [16]", "601", "5", "5", "6", "6"),
        row("[17]", "s_F [17]", "DUNITE [17]", "WR [17] / MIN", "701", "5", "5", "6", "6"),
    ]
    footer = [["Abbreviations: WR: WHOLE ROCK; GL: VOLCANIC GLASS;"] + [""] * 14,
              ["References:"] + [""] * 14,
              ["[12] AUTOR A.: TITULO  J. 1 [1990] 1-2"] + [""] * 14]
    df = pd.DataFrame(rows + footer, columns=GEOROC_HEADER)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(df.to_csv(index=False).encode("cp1252"))
    return path


@pytest.fixture
def georoc(tmp_path):
    return rs.load_georoc(_georoc_csv(tmp_path / "georoc" / "2026-09-2JETOA_X.csv"),
                          source_id="georoc:x")


def test_georoc_file_is_cp1252():
    raw = "ILHA RÉUNION".encode("cp1252")
    with pytest.raises(UnicodeDecodeError):
        raw.decode("utf-8")


def test_georoc_schema_ids_and_names_without_citation_tag(georoc):
    assert list(georoc.columns) == SCHEMAS["samples"]
    assert georoc.crs == CRS
    assert sorted(georoc["id"]) == ["georoc:101", "georoc:201"]
    names = dict(zip(georoc["id"], georoc["rock_name_original"]))
    assert names["georoc:101"] == "ALKALI BASALT"


def test_georoc_point_is_reported_without_uncertainty(georoc):
    a = georoc[georoc["id"] == "georoc:101"].iloc[0]
    assert a["coord_source"] == "reported"
    assert pd.isna(a["coord_uncertainty_m"])
    assert (a.geometry.x, a.geometry.y) == pytest.approx((55.7, -21.2))
    assert a["rock_class"] == "mafic"


def test_georoc_box_uses_centre_and_half_diagonal(georoc):
    b = georoc[georoc["id"] == "georoc:201"].iloc[0]
    assert (b.geometry.x, b.geometry.y) == pytest.approx((20.25, 10.25))
    assert b["coord_source"] == "reported"
    p1, p2 = math.radians(10.0), math.radians(10.5)
    dl = math.radians(0.5)
    h = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    expected = EARTH_RADIUS_M * 2 * math.asin(math.sqrt(h)) / 2
    assert b["coord_uncertainty_m"] == pytest.approx(expected, rel=1e-6)


def test_georoc_counts(georoc):
    a = georoc.attrs
    assert a["footer_rows"] == 3
    assert a["dropped_material"] == {"GL": 1, "WR / MIN": 1}
    assert a["dropped_duplicate_rows"] == 1
    assert a["dropped_box_too_large"] == 1
    assert a["pending_without_coords"] == 1
    assert a["box_centre"] == 1
    assert a["unmapped_total"] == 2
    assert a["unmapped_top"] == {"basaltic-andesite": 1, "dunite, xenolith [16] / dunite": 1}
    # s_A [16] e outra amostra (outra citacao): so a etiqueta final sai do nome,
    # e o nome composto nao casa com o mapeamento
    assert a["located"] == 2


def test_georoc_box_across_antimeridian_is_not_a_wide_box(tmp_path):
    df = pd.DataFrame([["[1]", "", "X", "", "-17", "-17.4", "179.9", "-179.9", "SEA",
                        "s_Z [1]", "BASALT [1]", "VOL", "WR [1]", "9", ""]], columns=GEOROC_HEADER)
    path = tmp_path / "g.csv"
    path.write_bytes(df.to_csv(index=False).encode("cp1252"))
    out = rs.load_georoc(path, source_id="georoc:g")
    assert len(out) == 1
    x = out.geometry.iloc[0].x
    assert abs(abs(x) - 180) < 1e-6


# --- registro ---------------------------------------------------------------

def test_registry_has_one_source_per_raw_file():
    sources = rs.registry()
    assert all(isinstance(s, Source) for s in sources)
    ids = [s.source_id for s in sources]
    assert len(ids) == len(set(ids))
    by_id = {s.source_id: s for s in sources}
    assert by_id["gvp"].layer == "volcanoes"
    assert by_id["tectonics"].layer == "tectonic_zones"
    assert by_id["glim"].layer == "geo_units"
    georoc = [s for s in sources if s.source_id.startswith("georoc:")]
    assert len(georoc) == len(rs.GEOROC_FILES) == 35
    assert all(s.layer == "samples" and s.raw_file.startswith("georoc/") for s in georoc)
    assert all(s.meta["acquisition_date"] == "2026-11-03" for s in sources)
    assert by_id["glim"].meta["original_scale"]
    assert by_id["gvp"].meta.get("original_scale") is None
