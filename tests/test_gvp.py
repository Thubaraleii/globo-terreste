from pathlib import Path

import pandas as pd
import pytest

from pipeline.common.model import SCHEMAS
from pipeline.gvp import load_hotspots, normalize_gvp

FIXTURE = Path(__file__).parent / "fixtures" / "gvp_sample.csv"


@pytest.fixture
def gvp():
    return normalize_gvp(pd.read_csv(FIXTURE, dtype=str), "gvp")


def test_normalize_gvp_keeps_original_name_and_coords(gvp):
    assert list(gvp.columns) == SCHEMAS["volcanoes"]
    assert gvp.crs == "EPSG:4326"
    row = gvp[gvp["name"] == "Vulcao Sintetico Alfa"].iloc[0]
    assert row["country"] == "Pais Ficticio A"
    assert row["type"] == "Stratovolcano"
    assert row["kind"] == "volcano"
    assert row["source_id"] == "gvp"
    assert pd.isna(row["reference"])
    assert row.geometry.x == pytest.approx(20.25)
    assert row.geometry.y == pytest.approx(10.5)


def test_normalize_gvp_empty_last_eruption_is_null(gvp):
    row = gvp[gvp["name"] == "Vulcao Sintetico Beta"].iloc[0]
    assert pd.isna(row["last_eruption"])


def test_normalize_gvp_drops_rows_without_coords_and_reports(gvp):
    assert len(gvp) == 3
    assert "Vulcao Sintetico Gama" not in set(gvp["name"])
    assert gvp.attrs["dropped_no_coords"] == 1


def test_load_hotspots_requires_reference(tmp_path):
    csv = tmp_path / "h.csv"
    csv.write_text("name,lon,lat,reference\nPonto X,10,20,\n", encoding="utf-8")
    with pytest.raises(ValueError):
        load_hotspots(csv, "curated")


def test_load_hotspots_valid_row(tmp_path):
    csv = tmp_path / "h.csv"
    csv.write_text("name,lon,lat,reference\nPonto X,10,20,Autor 2000\n", encoding="utf-8")
    out = load_hotspots(csv, "curated")
    assert list(out.columns) == SCHEMAS["volcanoes"]
    assert out.iloc[0]["kind"] == "hotspot"
    assert out.iloc[0]["reference"] == "Autor 2000"
    assert out.iloc[0].geometry.x == pytest.approx(10)


def test_load_hotspots_empty_file_returns_empty_frame(tmp_path):
    csv = tmp_path / "h.csv"
    csv.write_text("name,lon,lat,reference\n", encoding="utf-8")
    out = load_hotspots(csv, "curated")
    assert len(out) == 0
    assert list(out.columns) == SCHEMAS["volcanoes"]
    assert out.crs == "EPSG:4326"


def test_shipped_hotspot_list_has_no_rows():
    shipped = Path(__file__).parent.parent / "data" / "curated" / "hotspots.csv"
    assert len(load_hotspots(shipped, "curated")) == 0
