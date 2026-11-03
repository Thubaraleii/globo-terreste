from pathlib import Path

import pytest

from pipeline.rockmap import classify_rock, load_mapping, normalize_rock_name

CSV = Path(__file__).parent.parent / "data" / "curated" / "rock_mapping_v1.csv"


@pytest.fixture
def mapping():
    return load_mapping(CSV)


def test_basalt_is_mafic(mapping):
    assert classify_rock("Basalt", mapping) == "mafic"


def test_dunite_is_ultramafic(mapping):
    assert classify_rock("dunite", mapping) == "ultramafic"


def test_accent_case_spaces_normalized(mapping):
    assert normalize_rock_name("  Diabásio ") == "diabasio"
    assert classify_rock("  Diabásio ", mapping) == "mafic"


def test_compound_name_not_in_table_is_null(mapping):
    assert classify_rock("Olivine basalt, altered", mapping) is None


def test_granite_and_none_and_empty_are_null(mapping):
    assert classify_rock("Granite", mapping) is None
    assert classify_rock(None, mapping) is None
    assert classify_rock("", mapping) is None
    assert classify_rock("   ", mapping) is None


def test_load_mapping_rejects_class_other_than_mafic_or_ultramafic(tmp_path):
    p = tmp_path / "m.csv"
    p.write_text("name,class\ngranito,felsic\n", encoding="utf-8")
    with pytest.raises(ValueError, match="granito"):
        load_mapping(p)


def test_load_mapping_rejects_conflicting_duplicates(tmp_path):
    p = tmp_path / "m.csv"
    p.write_text("name,class\nBasalto,mafic\nbasalto,ultramafic\n", encoding="utf-8")
    with pytest.raises(ValueError, match="basalto"):
        load_mapping(p)
