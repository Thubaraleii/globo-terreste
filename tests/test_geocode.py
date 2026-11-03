import json

import pandas as pd
import pytest

from pipeline.common.model import CRS, SCHEMAS
from pipeline.geocode import geocode_pending


def _pending(rows):
    """rows: (id, locality, country)."""
    return pd.DataFrame({
        "id": [r[0] for r in rows],
        "rock_name_original": ["Basalt"] * len(rows),
        "rock_class": ["mafic"] * len(rows),
        "coord_source": [None] * len(rows),
        "coord_uncertainty_m": pd.Series([None] * len(rows), dtype="float64"),
        "unit_id": [None] * len(rows),
        "dup_group": [None] * len(rows),
        "source_id": ["src1"] * len(rows),
        "locality": [r[1] for r in rows],
        "country": [r[2] for r in rows],
    })


class Recorder:
    def __init__(self, answers):
        self.answers = answers
        self.calls = []

    def __call__(self, query):
        self.calls.append(query)
        ans = self.answers[query]
        if isinstance(ans, BaseException):
            raise ans
        return ans


def test_geocode_marks_source_and_uncertainty(tmp_path):
    geo = Recorder({"Serra Geral, Brazil": (-25.0, -50.0, 5000.0), "Bushveld": (-25.5, 29.0, 20000.0)})
    gdf = geocode_pending(_pending([("a", "Serra Geral", "Brazil"), ("b", "Bushveld", None)]),
                          geo, tmp_path / "cache.json")
    assert list(gdf.columns) == SCHEMAS["samples"]
    assert gdf.crs == CRS
    assert list(gdf["id"]) == ["a", "b"]
    assert list(gdf["coord_source"]) == ["geocoded", "geocoded"]
    assert list(gdf["coord_uncertainty_m"]) == [5000.0, 20000.0]
    assert (gdf.geometry.iloc[0].x, gdf.geometry.iloc[0].y) == (-50.0, -25.0)
    assert gdf.attrs["dropped_no_result"] == 0
    assert gdf.attrs["geocoder_errors"] == 0


def test_geocode_uses_cache_and_calls_geocoder_once_per_query(tmp_path):
    cache = tmp_path / "cache.json"
    geo = Recorder({"Serra Geral, Brazil": (-25.0, -50.0, 5000.0), "Nowhere": None})
    pend = _pending([("a", "Serra Geral", "Brazil"), ("b", "Serra Geral", "Brazil"), ("c", "Nowhere", "")])
    gdf = geocode_pending(pend, geo, cache)
    assert sorted(geo.calls) == ["Nowhere", "Serra Geral, Brazil"]
    assert list(gdf["id"]) == ["a", "b"]
    stored = json.loads(cache.read_text(encoding="utf-8"))
    assert stored["Nowhere"] is None
    # segunda rodada: nada novo e consultado, inclusive o None em cache
    geo2 = Recorder({})
    gdf2 = geocode_pending(pend, geo2, cache)
    assert geo2.calls == []
    assert list(gdf2["id"]) == ["a", "b"]
    assert gdf2.attrs["dropped_no_result"] == 1


def test_geocode_no_result_is_dropped_not_guessed(tmp_path):
    geo = Recorder({"Nowhere, Brazil": None, "Bad, X": (95.0, 10.0, 1.0), "Ok": (1.0, 2.0, 3.0)})
    gdf = geocode_pending(_pending([("a", "Nowhere", "Brazil"), ("b", "Bad", "X"), ("c", "Ok", None)]),
                          geo, tmp_path / "cache.json")
    assert list(gdf["id"]) == ["c"]
    assert gdf.attrs["dropped_no_result"] == 2
    assert gdf.attrs["geocoder_errors"] == 0


def test_geocoder_exception_does_not_abort_batch(tmp_path):
    cache = tmp_path / "cache.json"
    geo = Recorder({"Boom": RuntimeError("timeout"), "Ok": (1.0, 2.0, 3.0)})
    gdf = geocode_pending(_pending([("a", "Boom", None), ("b", "Ok", None)]), geo, cache)
    assert list(gdf["id"]) == ["b"]
    assert gdf.attrs["geocoder_errors"] == 1
    assert gdf.attrs["dropped_no_result"] == 0
    # erro nao e cacheado: proxima rodada tenta de novo
    assert "Boom" not in json.loads(cache.read_text(encoding="utf-8"))


def test_geocode_empty_pending(tmp_path):
    gdf = geocode_pending(_pending([]), Recorder({}), tmp_path / "cache.json")
    assert len(gdf) == 0
    assert list(gdf.columns) == SCHEMAS["samples"]
    assert gdf.crs == CRS


def test_malformed_geocoder_results_do_not_abort_batch(tmp_path):
    cache = tmp_path / "cache.json"
    geo = Recorder({
        "Two": (1.0, 2.0),
        "NoneUnc": (1.0, 2.0, None),
        "Str": "abc",
        "Ok": (1.0, 2.0, 3.0),
    })
    pend = _pending([("a", "Two", None), ("b", "NoneUnc", None), ("c", "Str", None), ("d", "Ok", None)])
    gdf = geocode_pending(pend, geo, cache)
    assert list(gdf["id"]) == ["d"]
    assert gdf.attrs["geocoder_errors"] == 3
    assert gdf.attrs["dropped_no_result"] == 0
    stored = json.loads(cache.read_text(encoding="utf-8"))
    assert stored == {"Ok": [1.0, 2.0, 3.0]}


def test_invalid_uncertainty_is_rejected(tmp_path):
    geo = Recorder({"Nan": (1.0, 2.0, float("nan")), "Neg": (1.0, 2.0, -5.0),
                    "Inf": (1.0, 2.0, float("inf")), "Ok": (1.0, 2.0, 0.0)})
    pend = _pending([("a", "Nan", None), ("b", "Neg", None), ("c", "Inf", None), ("d", "Ok", None)])
    gdf = geocode_pending(pend, geo, tmp_path / "cache.json")
    assert list(gdf["id"]) == ["d"]
    assert gdf.attrs["dropped_no_result"] == 3
    assert gdf.attrs["geocoder_errors"] == 0


def test_malformed_cache_entry_is_dropped_not_crashed(tmp_path):
    cache = tmp_path / "cache.json"
    cache.write_text(json.dumps({"Bad": [1.0], "Worse": "x", "Ok": [1.0, 2.0, 3.0]}), encoding="utf-8")
    geo = Recorder({})
    pend = _pending([("a", "Bad", None), ("b", "Worse", None), ("c", "Ok", None)])
    gdf = geocode_pending(pend, geo, cache)
    assert geo.calls == []
    assert list(gdf["id"]) == ["c"]
    assert gdf.attrs["geocoder_errors"] == 2
    assert gdf.attrs["dropped_no_result"] == 0


def test_cache_saved_when_run_is_interrupted(tmp_path):
    cache = tmp_path / "cache.json"
    geo = Recorder({"First": (1.0, 2.0, 3.0), "Second": KeyboardInterrupt()})
    pend = _pending([("a", "First", None), ("b", "Second", None)])
    with pytest.raises(KeyboardInterrupt):
        geocode_pending(pend, geo, cache)
    assert json.loads(cache.read_text(encoding="utf-8")) == {"First": [1.0, 2.0, 3.0]}
