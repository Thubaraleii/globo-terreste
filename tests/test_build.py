"""Testes do orquestrador incremental com fontes INJETADAS (sinteticas)."""
import json
from collections import Counter
from pathlib import Path

import geopandas as gpd
import numpy as np
import pytest
from pyogrio import read_dataframe
from shapely.geometry import Point, box

from pipeline import build as build_mod
from pipeline.build import Source, build
from pipeline.common.model import CRS


def _write_raw(raw_dir, name, rows):
    raw_dir.mkdir(parents=True, exist_ok=True)
    (raw_dir / name).write_text(json.dumps(rows), encoding="utf-8")


class Loader:
    """Le um JSON sintetico [{..., "lon":, "lat":}] e conta as chamadas."""

    def __init__(self, layer):
        self.layer = layer
        self.calls = 0
        self.kwargs = []

    def __call__(self, path, **kwargs):
        self.calls += 1
        self.kwargs.append(kwargs)
        rows = json.loads(path.read_text(encoding="utf-8"))
        if self.layer == "geo_units":
            geoms = [box(*r.pop("bbox")) for r in rows]
        else:
            geoms = [Point(r.pop("lon"), r.pop("lat")) for r in rows]
        return gpd.GeoDataFrame(rows, geometry=geoms, crs=CRS)


# meta minima valida (attribution e o unico campo obrigatorio que aceita None)
META = {"institution": "Inst", "source_url": "https://example.org/x", "license": "L",
        "attribution": None, "acquisition_date": "2026-11-03"}


def Src(*args, **kwargs):
    """Source com META valida por padrao."""
    kwargs.setdefault("meta", dict(META))
    return Source(*args, **kwargs)


def _volcano_source(raw_dir, rows=None):
    _write_raw(raw_dir, "gvp.json", rows or [{"name": "Etna", "lon": 15.0, "lat": 37.75}])
    return Src("gvp", "gvp.json", "volcanoes", Loader("volcanoes"),
               meta={"institution": "Smithsonian", "license": "CC-BY",
                     "source_url": "https://example.org/gvp", "attribution": None,
                     "acquisition_date": "2026-11-03"})


def test_build_writes_gpkg_sources_table_and_report(tmp_path):
    raw, out = tmp_path / "raw", tmp_path / "out"
    src = _volcano_source(raw)
    rep = build(raw, out, [src])
    assert rep.statuses == {"gvp": "processed"}
    assert rep.counts["volcanoes"] == 1 and rep.counts["samples"] == 0
    v = read_dataframe(out / "geoworld.gpkg", layer="volcanoes")
    assert list(v["name"]) == ["Etna"] and list(v["source_id"]) == ["gvp"]
    s = read_dataframe(out / "geoworld.gpkg", layer="sources")
    assert list(s["source_id"]) == ["gvp"]
    assert s["institution"].iloc[0] == "Smithsonian"
    assert s["license"].iloc[0] == "CC-BY"
    assert s["source_url"].iloc[0] == "https://example.org/gvp"
    assert s["attribution"].isna().all() and s["original_scale"].isna().all()
    assert (out / "volcanoes.geojson").exists()
    assert any("tippecanoe" in w for w in rep.warnings)


def test_build_skips_source_whose_hash_is_unchanged(tmp_path):
    raw, out = tmp_path / "raw", tmp_path / "out"
    src = _volcano_source(raw)
    build(raw, out, [src])
    rep = build(raw, out, [src])
    assert src.load.calls == 1
    assert rep.statuses == {"gvp": "skipped"}
    # dados anteriores mantidos
    v = read_dataframe(out / "geoworld.gpkg", layer="volcanoes")
    assert list(v["name"]) == ["Etna"]
    assert rep.counts["volcanoes"] == 1


def test_build_reprocesses_source_when_hash_changes(tmp_path):
    raw, out = tmp_path / "raw", tmp_path / "out"
    src = _volcano_source(raw)
    build(raw, out, [src])
    _write_raw(raw, "gvp.json", [{"name": "Vesuvius", "lon": 14.43, "lat": 40.82}])
    rep = build(raw, out, [src])
    assert src.load.calls == 2
    assert rep.statuses == {"gvp": "processed"}
    v = read_dataframe(out / "geoworld.gpkg", layer="volcanoes")
    assert list(v["name"]) == ["Vesuvius"]
    state = json.loads((out / "build_state.json").read_text(encoding="utf-8"))
    assert set(state) == {"gvp"}


def test_build_reprocesses_when_cache_is_missing(tmp_path):
    raw, out = tmp_path / "raw", tmp_path / "out"
    src = _volcano_source(raw)
    build(raw, out, [src])
    for f in (out / "_cache").iterdir():
        f.unlink()
    rep = build(raw, out, [src])
    assert rep.statuses == {"gvp": "processed"} and src.load.calls == 2


def test_failed_cache_write_leaves_no_cache_and_next_run_reprocesses(tmp_path):
    raw, out = tmp_path / "raw", tmp_path / "out"
    src = _volcano_source(raw)
    build(raw, out, [src])
    (out / "_cache" / "gvp.gpkg").unlink()  # hash inalterado, cache sumiu
    good = src.load

    def bad(path, **kwargs):
        gdf = good(path, **kwargs)
        gdf["fora_do_esquema"] = 1
        return gdf

    src.load = bad
    with pytest.raises(ValueError, match="fora_do_esquema"):
        build(raw, out, [src])
    assert list((out / "_cache").iterdir()) == []
    src.load = good
    rep = build(raw, out, [src])
    assert rep.statuses == {"gvp": "processed"}
    assert rep.counts["volcanoes"] == 1


def test_unreadable_cache_is_reprocessed(tmp_path):
    raw, out = tmp_path / "raw", tmp_path / "out"
    src = _volcano_source(raw)
    build(raw, out, [src])
    (out / "_cache" / "gvp.gpkg").write_bytes(b"lixo")
    rep = build(raw, out, [src])
    assert rep.statuses == {"gvp": "processed"} and rep.counts["volcanoes"] == 1


def test_changed_layer_is_reprocessed(tmp_path):
    raw, out = tmp_path / "raw", tmp_path / "out"
    _write_raw(raw, "pts.json", [{"lon": 1.0, "lat": 2.0}])
    build(raw, out, [Src("pts", "pts.json", "volcanoes", Loader("volcanoes"))])
    moved = Src("pts", "pts.json", "samples", Loader("samples"))
    rep = build(raw, out, [moved])
    assert rep.statuses == {"pts": "processed"} and moved.load.calls == 1
    assert rep.counts["samples"] == 1 and rep.counts["volcanoes"] == 0
    state = json.loads((out / "build_state.json").read_text(encoding="utf-8"))
    assert state["pts"]["layer"] == "samples"


def test_old_format_state_is_reprocessed(tmp_path):
    raw, out = tmp_path / "raw", tmp_path / "out"
    src = _volcano_source(raw)
    build(raw, out, [src])
    state_path = out / "build_state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state_path.write_text(json.dumps({"gvp": state["gvp"]["sha256"]}), encoding="utf-8")
    rep = build(raw, out, [src])
    assert rep.statuses == {"gvp": "processed"} and src.load.calls == 2


def test_force_reprocesses_everything(tmp_path):
    raw, out = tmp_path / "raw", tmp_path / "out"
    src = _volcano_source(raw)
    build(raw, out, [src])
    rep = build(raw, out, [src], force=True)
    assert rep.statuses == {"gvp": "processed"} and src.load.calls == 2


def test_cli_force_flag_is_passed(tmp_path, monkeypatch):
    seen = {}
    monkeypatch.setattr(build_mod, "SOURCES", [object()])
    monkeypatch.setattr(build_mod, "build", lambda *a, **kw: seen.update(kw) or
                        build_mod.BuildReport({}, {}, [], []))
    assert build_mod.main(["--raw", "r", "--out", "o", "--force"]) == 0
    assert seen["force"] is True


def test_network_source_with_missing_raw_is_skipped_network(tmp_path):
    net = Src("geo", "ainda_nao_baixado.json", "samples", Loader("samples"),
                 needs_network=True)
    rep = build(tmp_path / "raw", tmp_path / "out", [net])
    assert rep.statuses == {"geo": "skipped_network"}


def test_missing_raw_file_raises(tmp_path):
    src = Src("x", "nao_existe.json", "volcanoes", Loader("volcanoes"))
    with pytest.raises(FileNotFoundError, match="nao_existe.json"):
        build(tmp_path / "raw", tmp_path / "out", [src])


def test_post_steps_link_duplicates_and_units(tmp_path):
    raw, out = tmp_path / "raw", tmp_path / "out"
    _write_raw(raw, "units.json", [{"unit_id": "u1", "lith_class": "basalt", "bbox": [0, 0, 1, 1]}])
    _write_raw(raw, "a.json", [
        {"id": "a1", "rock_name_original": "Basalt", "lon": 0.5, "lat": 0.5},
        {"id": "a2", "rock_name_original": "Granite", "lon": 5.0, "lat": 5.0},
    ])
    _write_raw(raw, "b.json", [{"id": "b1", "rock_name_original": "basalt", "lon": 0.5, "lat": 0.5}])
    sources = [
        Src("glim", "units.json", "geo_units", Loader("geo_units")),
        Src("src_a", "a.json", "samples", Loader("samples")),
        Src("src_b", "b.json", "samples", Loader("samples")),
    ]
    rep = build(raw, out, sources)
    s = read_dataframe(out / "geoworld.gpkg", layer="samples").set_index("id")
    assert s.loc["a1", "dup_group"] is not None
    assert s.loc["a1", "dup_group"] == s.loc["b1", "dup_group"]
    assert s["dup_group"].isna()["a2"]
    assert s.loc["a1", "unit_id"] == "u1" and s.loc["b1", "unit_id"] == "u1"
    assert s["unit_id"].isna()["a2"]
    assert dict(s["source_id"]) == {"a1": "src_a", "a2": "src_a", "b1": "src_b"}
    assert rep.counts["samples"] == 3 and rep.counts["geo_units"] == 1


def test_empty_sample_source_is_assembled_cleanly(tmp_path):
    raw, out = tmp_path / "raw", tmp_path / "out"
    _write_raw(raw, "a.json", [{"id": "a1", "rock_name_original": "basalt", "lon": 0.5, "lat": 0.5}])
    _write_raw(raw, "e.json", [])
    sources = [
        Src("src_a", "a.json", "samples", Loader("samples")),
        Src("src_e", "e.json", "samples", Loader("samples")),
    ]
    rep = build(raw, out, sources)
    assert rep.counts["samples"] == 1
    s = read_dataframe(out / "geoworld.gpkg", layer="samples")
    assert s["unit_id"].isna().all() and s["dup_group"].isna().all()


def test_network_source_skipped_without_allow_network(tmp_path):
    raw, out = tmp_path / "raw", tmp_path / "out"
    _write_raw(raw, "geo.json", [{"id": "g1", "lon": 1.0, "lat": 1.0}])
    net = Src("geo", "geo.json", "samples", Loader("samples"), needs_network=True)
    rep = build(raw, out, [net])
    assert rep.statuses == {"geo": "skipped_network"}
    assert net.load.calls == 0
    assert rep.counts["samples"] == 0
    assert not json.loads((out / "build_state.json").read_text(encoding="utf-8"))


def test_network_flag_passed_only_to_network_sources(tmp_path):
    raw, out = tmp_path / "raw", tmp_path / "out"
    local = _volcano_source(raw)
    _write_raw(raw, "geo.json", [{"id": "g1", "lon": 1.0, "lat": 1.0}])
    net = Src("geo", "geo.json", "samples", Loader("samples"), needs_network=True)
    rep = build(raw, out, [local, net], allow_network=True)
    assert rep.statuses == {"gvp": "processed", "geo": "processed"}
    assert local.load.kwargs == [{}]
    assert net.load.kwargs == [{"allow_network": True}]
    assert rep.counts["samples"] == 1


def test_build_passes_tippecanoe_to_export(tmp_path, monkeypatch):
    seen = {}
    real = build_mod.export_web

    def fake(gpkg, out_dir, tippecanoe, **kw):
        seen["tippecanoe"] = tippecanoe
        return real(gpkg, out_dir, None)

    monkeypatch.setattr(build_mod, "export_web", fake)
    raw, out = tmp_path / "raw", tmp_path / "out"
    build(raw, out, [_volcano_source(raw)], tippecanoe="/x/tippecanoe")
    assert seen["tippecanoe"] == "/x/tippecanoe"


def test_default_registry_is_empty():
    assert build_mod.SOURCES == []


def test_cli_with_empty_registry_prints_message(tmp_path, capsys):
    code = build_mod.main(["--raw", str(tmp_path / "raw"), "--out", str(tmp_path / "out")])
    assert code == 0
    assert "nenhuma fonte" in capsys.readouterr().out.lower()
    assert not (tmp_path / "out" / "geoworld.gpkg").exists()


# --- meta obrigatoria -------------------------------------------------------

@pytest.mark.parametrize("drop", ["institution", "source_url", "license",
                                  "attribution", "acquisition_date"])
def test_source_meta_missing_required_key_raises(drop):
    meta = {k: v for k, v in META.items() if k != drop}
    with pytest.raises(ValueError, match=rf"fonte_x.*{drop}"):
        Source("fonte_x", "f.json", "volcanoes", Loader("volcanoes"), meta=meta)


def test_source_meta_none_only_allowed_for_attribution_and_scale():
    Source("ok", "f.json", "volcanoes", Loader("volcanoes"),
           meta={**META, "attribution": None, "original_scale": None})
    with pytest.raises(ValueError, match=r"ruim.*license"):
        Source("ruim", "f.json", "volcanoes", Loader("volcanoes"), meta={**META, "license": None})
    with pytest.raises(ValueError, match=r"vazia.*institution"):
        Source("vazia", "f.json", "volcanoes", Loader("volcanoes"),
               meta={**META, "institution": "  "})


def test_source_without_meta_raises_naming_all_missing_keys():
    with pytest.raises(ValueError) as exc:
        Source("sem_meta", "f.json", "volcanoes", Loader("volcanoes"))
    msg = str(exc.value)
    assert "sem_meta" in msg
    for k in ("institution", "source_url", "license", "attribution", "acquisition_date"):
        assert k in msg


# --- contagens dos normalizadores ------------------------------------------

class AttrsLoader(Loader):
    """Loader que devolve contagens em gdf.attrs, como os normalizadores."""

    def __init__(self, layer, attrs):
        super().__init__(layer)
        self.attrs = attrs

    def __call__(self, path, **kwargs):
        gdf = super().__call__(path, **kwargs)
        gdf.attrs.update(self.attrs)
        return gdf


def test_report_notes_carry_loader_attrs_and_survive_cache(tmp_path):
    raw, out = tmp_path / "raw", tmp_path / "out"
    _write_raw(raw, "gvp.json", [{"name": "Etna", "lon": 15.0, "lat": 37.75}])
    src = Src("gvp", "gvp.json", "volcanoes",
              AttrsLoader("volcanoes", {"dropped_no_coords": np.int64(3),
                                        "unmapped": Counter({"xx": 2})}))
    rep = build(raw, out, [src])
    assert rep.notes == {"gvp": {"dropped_no_coords": 3, "unmapped": {"xx": 2}}}
    assert type(rep.notes["gvp"]["dropped_no_coords"]) is int
    again = build(raw, out, [src])
    assert again.statuses == {"gvp": "skipped"} and src.load.calls == 1
    assert again.notes == rep.notes


def test_report_notes_empty_without_attrs_and_for_skipped_network(tmp_path):
    raw, out = tmp_path / "raw", tmp_path / "out"
    net = Src("geo", "nada.json", "samples", Loader("samples"), needs_network=True)
    rep = build(raw, out, [_volcano_source(raw), net])
    assert rep.notes == {"gvp": {}}


def test_cli_prints_notes(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(build_mod, "SOURCES", [object()])
    monkeypatch.setattr(build_mod, "build", lambda *a, **kw: build_mod.BuildReport(
        {"gvp": "processed"}, {"volcanoes": 1}, [], [],
        notes={"gvp": {"dropped_no_coords": 4}}))
    assert build_mod.main(["--raw", "r", "--out", "o"]) == 0
    text = capsys.readouterr().out
    assert "gvp: processed" in text and "dropped_no_coords: 4" in text


def test_cli_keep_intermediate_is_passed(tmp_path, monkeypatch):
    seen = {}
    monkeypatch.setattr(build_mod, "SOURCES", [object()])
    monkeypatch.setattr(build_mod, "build", lambda *a, **kw: seen.update(kw) or
                        build_mod.BuildReport({}, {}, [], []))
    build_mod.main(["--raw", "r", "--out", "o", "--keep-intermediate", "tiles_in"])
    assert seen["keep_intermediate"] == Path("tiles_in")
    build_mod.main(["--raw", "r", "--out", "o"])
    assert seen["keep_intermediate"] is None


def test_build_passes_keep_intermediate_to_export(tmp_path, monkeypatch):
    seen = {}
    real = build_mod.export_web

    def fake(gpkg, out_dir, tippecanoe, **kw):
        seen.update(kw)
        return real(gpkg, out_dir, None)

    monkeypatch.setattr(build_mod, "export_web", fake)
    raw, out = tmp_path / "raw", tmp_path / "out"
    build(raw, out, [_volcano_source(raw)], keep_intermediate=tmp_path / "k")
    assert seen["keep_intermediate"] == tmp_path / "k"


def test_assembly_does_not_reread_the_final_gpkg(tmp_path, monkeypatch):
    """Contagens vem de read_info e as unidades do quadro ja montado: o
    geoworld.gpkg nao e relido com read_dataframe."""
    raw, out = tmp_path / "raw", tmp_path / "out"
    _write_raw(raw, "units.json", [{"unit_id": "u1", "lith_class": "basalt", "bbox": [0, 0, 1, 1]}])
    _write_raw(raw, "a.json", [{"id": "a1", "rock_name_original": "Basalt", "lon": 0.5, "lat": 0.5}])
    reads = []
    real = build_mod.read_dataframe
    monkeypatch.setattr(build_mod, "read_dataframe",
                        lambda path, **kw: reads.append(Path(path).name) or real(path, **kw))
    rep = build(raw, out, [Src("glim", "units.json", "geo_units", Loader("geo_units")),
                           Src("src_a", "a.json", "samples", Loader("samples"))])
    assert "geoworld.gpkg" not in reads
    assert rep.counts == {"geo_units": 1, "volcanoes": 0, "tectonic_zones": 0, "samples": 1}
    s = read_dataframe(out / "geoworld.gpkg", layer="samples")
    assert list(s["unit_id"]) == ["u1"]
