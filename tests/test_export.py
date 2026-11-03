"""Testes de export_web com dados SINTETICOS (sem rede, sem tippecanoe real)."""
import json
import shutil
import subprocess
from pathlib import Path

import geopandas as gpd
import pandas as pd
import pytest
from pyogrio import read_dataframe
from shapely.geometry import LineString, Point, box

from pipeline import export
from pipeline.common.model import CRS, create_geopackage, write_layer
from pipeline.export import ExportResult, export_web


def _gpkg(tmp_path, with_units=True, with_samples=True):
    g = tmp_path / "geoworld.gpkg"
    create_geopackage(g)
    write_layer(g, "volcanoes", gpd.GeoDataFrame(
        {"name": ["Etna", None], "kind": ["volcano", "volcano"], "source_id": ["gvp", "gvp"]},
        geometry=[Point(15.0, 37.75), Point(-10.5, 5.25)], crs=CRS,
    ))
    write_layer(g, "tectonic_zones", gpd.GeoDataFrame(
        {
            "rank": pd.array([1, None], dtype="Int64"),
            "name": ["zona A", None],
            "moment_total": [1.5e20, None],
            "source_id": ["tz", "tz"],
        },
        geometry=[LineString([(0, 0), (1, 1)]), box(2, 2, 3, 3)], crs=CRS,
    ))
    if with_units:
        write_layer(g, "geo_units", gpd.GeoDataFrame(
            {"unit_id": ["u1"], "lith_class": ["granite"], "source_id": ["glim"]},
            geometry=[box(0, 0, 1, 1)], crs=CRS,
        ))
    if with_samples:
        write_layer(g, "samples", gpd.GeoDataFrame(
            {"id": ["s1"], "rock_name_original": ["basalt"], "source_id": ["s"]},
            geometry=[Point(0.5, 0.5)], crs=CRS,
        ))
    return g


def _read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _version_ok(cmd, text=b"tippecanoe v2.53.0\n"):
    """Resposta de `tippecanoe --version` (o tippecanoe escreve a versao no stderr)."""
    return subprocess.CompletedProcess(cmd, 0, b"", text)


class FakeRunner:
    """Registra os comandos e cria o arquivo de saida (-o) como o tippecanoe.
    `--version` vai para `version_calls` e responde `version`."""

    def __init__(self, version=b"tippecanoe v2.53.0\n", fail_layer=None, stderr=b""):
        self.calls = []
        self.version_calls = []
        self.version = version
        self.fail_layer = fail_layer
        self.stderr = stderr

    def __call__(self, cmd, **kwargs):
        if "--version" in cmd:
            self.version_calls.append((list(cmd), kwargs))
            if isinstance(self.version, BaseException):
                raise self.version
            return _version_ok(cmd, self.version)
        self.calls.append((list(cmd), kwargs))
        if self.fail_layer and cmd[cmd.index("-l") + 1] == self.fail_layer:
            raise subprocess.CalledProcessError(1, cmd, output=b"", stderr=self.stderr)
        Path(cmd[cmd.index("-o") + 1]).write_bytes(b"PMTiles")
        return subprocess.CompletedProcess(cmd, 0, b"", b"")


def test_export_writes_geojson_for_small_layers(tmp_path):
    out = tmp_path / "web"
    res = export_web(_gpkg(tmp_path), out, tippecanoe=None)
    assert isinstance(res, ExportResult)
    v = _read(out / "volcanoes.geojson")
    t = _read(out / "tectonic_zones.geojson")
    assert v["type"] == "FeatureCollection" and len(v["features"]) == 2
    assert v["features"][0]["geometry"] == {"type": "Point", "coordinates": [15.0, 37.75]}
    assert v["features"][0]["properties"]["name"] == "Etna"
    assert set(v["features"][0]["properties"]) == {
        "name", "kind", "type", "last_eruption", "country", "reference", "source_id",
    }
    assert [f["geometry"]["type"] for f in t["features"]] == ["LineString", "Polygon"]
    assert t["features"][0]["properties"]["rank"] == 1
    assert isinstance(t["features"][0]["properties"]["rank"], int)
    assert {out / "volcanoes.geojson", out / "tectonic_zones.geojson"} <= set(res.files)


def test_geojson_nulls_stay_null(tmp_path):
    out = tmp_path / "web"
    export_web(_gpkg(tmp_path), out, tippecanoe=None)
    text = (out / "tectonic_zones.geojson").read_text(encoding="utf-8")
    assert "NaN" not in text
    props = _read(out / "tectonic_zones.geojson")["features"][1]["properties"]
    assert props["rank"] is None
    assert props["name"] is None
    assert props["moment_total"] is None
    assert props["period_start"] is None
    vprops = _read(out / "volcanoes.geojson")["features"][1]["properties"]
    assert vprops["name"] is None and vprops["country"] is None


def _zones_gpkg(tmp_path, moments):
    g = tmp_path / "zones.gpkg"
    create_geopackage(g)
    n = len(moments)
    write_layer(g, "tectonic_zones", gpd.GeoDataFrame(
        {
            "rank": pd.array(list(range(1, n + 1)), dtype="Int64"),
            "name": [f"z{i}" for i in range(n)],
            "moment_total": moments,
            "source_id": ["tz"] * n,
        },
        geometry=[LineString([(i, 0), (i, 1)]) for i in range(n)], crs=CRS,
    ))
    return g


def test_moment_total_exported_as_string_and_log10(tmp_path):
    out = tmp_path / "web"
    g = _zones_gpkg(tmp_path, [3.98e19, 1.2e23, None, 0.0, 1e21])
    export_web(g, out, tippecanoe=None)
    props = [f["properties"] for f in _read(out / "tectonic_zones.geojson")["features"]]
    assert [p["moment_total"] for p in props] == ["3.980e+19", "1.200e+23", None, None, "1.000e+21"]
    assert [p["moment_log10"] for p in props] == [19.6, 23.079, None, None, 21.0]
    assert isinstance(props[0]["moment_total"], str)
    # inteiro "redondo" tambem e escrito (pequeno, seguro para o MapLibre)
    assert "moment_log10" in props[4] and props[4]["moment_log10"] == 21
    text = (out / "tectonic_zones.geojson").read_text(encoding="utf-8")
    assert '"moment_log10": 21.0' in text


def test_moment_values_non_positive_or_non_finite_are_null():
    for bad in [None, 0.0, -5.0, float("nan"), float("inf"), float("-inf")]:
        assert export._moment_props(bad) == {"moment_total": None, "moment_log10": None}


def test_gpkg_tectonic_zones_unchanged_by_export(tmp_path):
    g = _zones_gpkg(tmp_path, [3.98e19, None])
    export_web(g, tmp_path / "web", tippecanoe=None)
    t = read_dataframe(g, layer="tectonic_zones")
    assert "moment_log10" not in t.columns
    assert t["moment_total"].dtype == "float64"
    assert t["moment_total"].iloc[0] == 3.98e19
    assert pd.isna(t["moment_total"].iloc[1])


def test_empty_layer_gives_valid_empty_feature_collection(tmp_path):
    g = tmp_path / "empty.gpkg"
    create_geopackage(g)
    out = tmp_path / "web"
    export_web(g, out, tippecanoe=None)
    assert _read(out / "volcanoes.geojson") == {"type": "FeatureCollection", "features": []}
    assert _read(out / "tectonic_zones.geojson") == {"type": "FeatureCollection", "features": []}


def test_export_without_tippecanoe_warns_and_skips_pmtiles(tmp_path):
    out = tmp_path / "web"
    res = export_web(_gpkg(tmp_path), out, tippecanoe=None)
    assert not (out / "geo_units.pmtiles").exists()
    assert not (out / "samples.pmtiles").exists()
    assert not [p for p in res.files if p.suffix == ".pmtiles"]
    assert any("tippecanoe" in w for w in res.warnings)


def test_stale_pmtiles_removed_when_tippecanoe_absent(tmp_path):
    out = tmp_path / "web"
    out.mkdir()
    for layer in ("geo_units", "samples"):
        (out / f"{layer}.pmtiles").write_bytes(b"antigo")
    res = export_web(_gpkg(tmp_path), out, tippecanoe=None)
    assert not (out / "geo_units.pmtiles").exists()
    assert not (out / "samples.pmtiles").exists()
    assert any("removid" in w and "geo_units.pmtiles" in w for w in res.warnings)


def test_tippecanoe_command_built_without_shell(tmp_path):
    out = tmp_path / "web"
    run = FakeRunner()
    res = export_web(_gpkg(tmp_path), out, tippecanoe="/opt/bin/tippecanoe", run=run)
    assert len(run.calls) == 2
    flags = {
        "geo_units": ["-zg", "--coalesce-densest-as-needed", "--extend-zooms-if-still-dropping"],
        "samples": ["-zg", "-r1", "--drop-densest-as-needed", "--extend-zooms-if-still-dropping"],
    }
    for (cmd, kwargs), layer in zip(run.calls, ["geo_units", "samples"]):
        assert cmd[:-1] == [
            "/opt/bin/tippecanoe", "-o", str(out / f"{layer}.pmtiles"),
            *flags[layer], "-l", layer,
        ]
        assert cmd[-1].endswith(f"{layer}.geojson")
        assert kwargs.get("shell", False) is False
        assert kwargs["check"] is True and kwargs["capture_output"] is True
    assert out / "geo_units.pmtiles" in res.files
    assert out / "samples.pmtiles" in res.files
    assert res.warnings == []
    # a versao e conferida uma vez, pelo mesmo runner, sem shell
    assert [c for c, _ in run.version_calls] == [["/opt/bin/tippecanoe", "--version"]]
    assert run.version_calls[0][1].get("shell", False) is False


def test_tippecanoe_failure_surfaces_stderr(tmp_path):
    run = FakeRunner(fail_layer="samples", stderr="erro: memória insuficiente\n".encode())
    with pytest.raises(RuntimeError) as exc:
        export_web(_gpkg(tmp_path), tmp_path / "web", tippecanoe="tippecanoe", run=run)
    msg = str(exc.value)
    assert "samples" in msg and "erro: memória insuficiente" in msg
    assert isinstance(exc.value.__cause__, subprocess.CalledProcessError)


@pytest.mark.parametrize("version", [
    b"tippecanoe v2.16.0\n", b"tippecanoe v1.36.0\n", b"???\n", b"",
    FileNotFoundError("sem binario"), subprocess.CalledProcessError(1, ["t"]),
])
def test_old_or_unparseable_tippecanoe_version_warns(tmp_path, version):
    run = FakeRunner(version=version)
    res = export_web(_gpkg(tmp_path), tmp_path / "web", tippecanoe="tippecanoe", run=run)
    warn = [w for w in res.warnings if "2.17" in w]
    assert len(warn) == 1 and "PMTiles" in warn[0]
    assert len(run.calls) == 2  # aviso, nao erro


@pytest.mark.parametrize("version", [b"tippecanoe v2.17.0\n", b"v2.53.0", b"tippecanoe v3.0\n"])
def test_recent_tippecanoe_version_does_not_warn(tmp_path, version):
    run = FakeRunner(version=version)
    res = export_web(_gpkg(tmp_path), tmp_path / "web", tippecanoe="tippecanoe", run=run)
    assert res.warnings == []


def test_parse_tippecanoe_version():
    assert export._parse_version("tippecanoe v2.53.0") == (2, 53, 0)
    assert export._parse_version("2.17") == (2, 17, 0)
    assert export._parse_version("nada") is None


def test_keep_intermediate_without_tippecanoe_writes_inputs(tmp_path):
    keep = tmp_path / "inter"
    out = tmp_path / "web"
    res = export_web(_gpkg(tmp_path), out, tippecanoe=None, keep_intermediate=keep)
    units = _read(keep / "geo_units.geojson")
    samples = _read(keep / "samples.geojson")
    assert units["features"][0]["properties"]["sample_count"] == 0  # amostra sem unit_id
    assert "unit_lith_class" in samples["features"][0]["properties"]
    assert not (out / "geo_units.pmtiles").exists()
    assert any("tippecanoe" in w for w in res.warnings)
    assert any(str(keep) in w for w in res.warnings)


def test_keep_intermediate_with_tippecanoe_keeps_the_input_files(tmp_path):
    keep = tmp_path / "inter"
    run = FakeRunner()
    export_web(_gpkg(tmp_path), tmp_path / "web", tippecanoe="tippecanoe", run=run,
               keep_intermediate=keep)
    assert [c[-1] for c, _ in run.calls] == [str(keep / "geo_units.geojson"),
                                            str(keep / "samples.geojson")]
    assert (keep / "geo_units.geojson").exists() and (keep / "samples.geojson").exists()


def test_tippecanoe_input_is_the_layer_as_geojson(tmp_path):
    seen = {}

    def run(cmd, **kwargs):
        if "--version" in cmd:
            return _version_ok(cmd)
        seen[cmd[cmd.index("-l") + 1]] = _read(Path(cmd[-1]))
        Path(cmd[cmd.index("-o") + 1]).write_bytes(b"")
        return subprocess.CompletedProcess(cmd, 0)

    export_web(_gpkg(tmp_path), tmp_path / "web", tippecanoe="tippecanoe", run=run)
    assert seen["samples"]["features"][0]["properties"]["id"] == "s1"
    assert seen["geo_units"]["features"][0]["properties"]["unit_id"] == "u1"


def test_samples_tiles_carry_unit_lith_class(tmp_path):
    g = tmp_path / "geoworld.gpkg"
    create_geopackage(g)
    write_layer(g, "geo_units", gpd.GeoDataFrame(
        {"unit_id": ["u1", "u2"], "lith_class": ["granite", None], "source_id": ["glim"] * 2},
        geometry=[box(0, 0, 1, 1), box(2, 0, 3, 1)], crs=CRS,
    ))
    write_layer(g, "samples", gpd.GeoDataFrame(
        {"id": ["s1", "s2", "s3", "s4"], "unit_id": ["u1", None, "u2", "u9"],
         "source_id": ["s"] * 4},
        geometry=[Point(0.5, 0.5), Point(9, 9), Point(2.5, 0.5), Point(8, 8)], crs=CRS,
    ))
    seen = {}

    def run(cmd, **kwargs):
        if "--version" in cmd:
            return _version_ok(cmd)
        seen[cmd[cmd.index("-l") + 1]] = _read(Path(cmd[-1]))
        Path(cmd[cmd.index("-o") + 1]).write_bytes(b"")
        return subprocess.CompletedProcess(cmd, 0)

    export_web(g, tmp_path / "web", tippecanoe="tippecanoe", run=run)
    props = {f["properties"]["id"]: f["properties"] for f in seen["samples"]["features"]}
    assert props["s1"]["unit_lith_class"] == "granite"
    assert props["s2"]["unit_lith_class"] is None   # unit_id nulo
    assert props["s3"]["unit_lith_class"] is None   # lith_class nulo
    assert props["s4"]["unit_lith_class"] is None   # unidade inexistente
    assert "unit_lith_class" not in seen["geo_units"]["features"][0]["properties"]
    # o gpkg nao muda
    assert "unit_lith_class" not in read_dataframe(g, layer="samples").columns


def _capture_run(seen):
    def run(cmd, **kwargs):
        if "--version" in cmd:
            return _version_ok(cmd)
        seen[cmd[cmd.index("-l") + 1]] = _read(Path(cmd[-1]))
        Path(cmd[cmd.index("-o") + 1]).write_bytes(b"")
        return subprocess.CompletedProcess(cmd, 0)
    return run


def test_geo_units_tiles_carry_sample_count(tmp_path):
    g = tmp_path / "geoworld.gpkg"
    create_geopackage(g)
    write_layer(g, "geo_units", gpd.GeoDataFrame(
        {"unit_id": ["u1", "u2"], "lith_class": ["granite", "basalt"], "source_id": ["glim"] * 2},
        geometry=[box(0, 0, 1, 1), box(2, 0, 3, 1)], crs=CRS,
    ))
    write_layer(g, "samples", gpd.GeoDataFrame(
        {"id": ["s1", "s2", "s3", "s4"], "unit_id": ["u1", "u1", None, "u9"],
         "source_id": ["s"] * 4},
        geometry=[Point(0.5, 0.5), Point(0.2, 0.2), Point(9, 9), Point(8, 8)], crs=CRS,
    ))
    seen = {}
    export_web(g, tmp_path / "web", tippecanoe="tippecanoe", run=_capture_run(seen))
    props = {f["properties"]["unit_id"]: f["properties"] for f in seen["geo_units"]["features"]}
    assert props["u1"]["sample_count"] == 2 and type(props["u1"]["sample_count"]) is int
    assert props["u2"]["sample_count"] == 0 and type(props["u2"]["sample_count"]) is int
    assert "sample_count" not in seen["samples"]["features"][0]["properties"]
    assert "sample_count" not in read_dataframe(g, layer="geo_units").columns
    assert seen["geo_units"]["features"][0]["geometry"]["type"] == "Polygon"


def test_sample_count_zero_when_samples_empty(tmp_path):
    seen = {}
    export_web(_gpkg(tmp_path, with_samples=False), tmp_path / "web",
               tippecanoe="tippecanoe", run=_capture_run(seen))
    counts = [f["properties"]["sample_count"] for f in seen["geo_units"]["features"]]
    assert counts == [0] and type(counts[0]) is int


def test_export_writes_sources_json(tmp_path):
    g = _gpkg(tmp_path)
    write_layer(g, "sources", pd.DataFrame([
        {"source_id": "gvp", "institution": "Smithsonian", "source_url": "https://x/gvp",
         "license": "CC-BY-4.0", "attribution": "GVP", "acquisition_date": "2026-10-01",
         "original_scale": "1:1000000"},
        {"source_id": "glim", "institution": "Univ. Hamburg", "source_url": None,
         "license": None, "attribution": "GLiM", "acquisition_date": "2026-10-02",
         "original_scale": None},
    ]))
    out = tmp_path / "web"
    res = export_web(g, out, tippecanoe=None)
    assert out / "sources.json" in res.files
    text = (out / "sources.json").read_text(encoding="utf-8")
    assert "NaN" not in text
    data = json.loads(text)
    assert data == [
        {"source_id": "gvp", "institution": "Smithsonian", "source_url": "https://x/gvp",
         "license": "CC-BY-4.0", "attribution": "GVP", "acquisition_date": "2026-10-01",
         "original_scale": "1:1000000"},
        {"source_id": "glim", "institution": "Univ. Hamburg", "source_url": None,
         "license": None, "attribution": "GLiM", "acquisition_date": "2026-10-02",
         "original_scale": None},
    ]
    assert list(data[0]) == [
        "source_id", "institution", "source_url", "license",
        "attribution", "acquisition_date", "original_scale",
    ]


def test_empty_sources_table_gives_empty_array(tmp_path):
    out = tmp_path / "web"
    res = export_web(_gpkg(tmp_path), out, tippecanoe=None)
    assert out / "sources.json" in res.files
    assert json.loads((out / "sources.json").read_text(encoding="utf-8")) == []


def test_unit_lith_class_all_null_when_geo_units_empty(tmp_path):
    seen = {}

    def run(cmd, **kwargs):
        if "--version" in cmd:
            return _version_ok(cmd)
        seen[cmd[cmd.index("-l") + 1]] = _read(Path(cmd[-1]))
        Path(cmd[cmd.index("-o") + 1]).write_bytes(b"")
        return subprocess.CompletedProcess(cmd, 0)

    export_web(_gpkg(tmp_path, with_units=False), tmp_path / "web",
               tippecanoe="tippecanoe", run=run)
    props = [f["properties"] for f in seen["samples"]["features"]]
    assert props and all(p["unit_lith_class"] is None for p in props)


def test_empty_pmtiles_layer_is_skipped_with_warning(tmp_path):
    run = FakeRunner()
    res = export_web(_gpkg(tmp_path, with_samples=False), tmp_path / "web",
                     tippecanoe="tippecanoe", run=run)
    assert [c[0][c[0].index("-l") + 1] for c in run.calls] == ["geo_units"]
    assert any("samples" in w for w in res.warnings)


def test_export_warns_when_file_over_95mb(tmp_path, monkeypatch):
    out = tmp_path / "web"
    real = export.file_size
    big = out / "volcanoes.geojson"
    monkeypatch.setattr(
        export, "file_size", lambda p: 96 * 1024 * 1024 if p == big else real(p),
    )
    res = export_web(_gpkg(tmp_path), out, tippecanoe=None)
    over = [w for w in res.warnings if "95 MB" in w]
    assert len(over) == 1 and "volcanoes.geojson" in over[0]


def test_export_does_not_warn_at_exactly_95mb(tmp_path, monkeypatch):
    monkeypatch.setattr(export, "file_size", lambda p: 95 * 1024 * 1024)
    res = export_web(_gpkg(tmp_path), tmp_path / "web", tippecanoe=None)
    assert not [w for w in res.warnings if "95 MB" in w]


@pytest.mark.skipif(shutil.which("tippecanoe") is None, reason="tippecanoe nao instalado")
def test_real_tippecanoe_writes_pmtiles(tmp_path):
    out = tmp_path / "web"
    res = export_web(_gpkg(tmp_path), out, tippecanoe=shutil.which("tippecanoe"))
    assert (out / "geo_units.pmtiles").stat().st_size > 0
    assert (out / "samples.pmtiles").stat().st_size > 0
    assert res.warnings == []
