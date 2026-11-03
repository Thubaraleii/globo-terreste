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


# --- mapeamento v2 (proposto; nomes do GEOROC) -------------------------------

CSV_V2 = CSV.with_name("rock_mapping_v2.csv")

V2_MAFIC = ["alkali basalt", "tholeiitic basalt", "transitional basalt", "subalkali basalt",
            "calc-alkali basalt", "picrobasalt", "trachybasalt", "basanite", "ankaramite",
            "gabbronorite", "norite"]
V2_ULTRAMAFIC = ["harzburgite", "lherzolite", "wehrlite", "websterite",
                 "clinopyroxenite", "orthopyroxenite"]


def test_v2_keeps_every_v1_row():
    v1, v2 = load_mapping(CSV), load_mapping(CSV_V2)
    assert {k: v2.get(k) for k in v1} == v1


def test_v2_adds_georoc_names_and_nothing_else():
    v1, v2 = load_mapping(CSV), load_mapping(CSV_V2)
    added = {k: v for k, v in v2.items() if k not in v1}
    assert added == {**{n: "mafic" for n in V2_MAFIC}, **{n: "ultramafic" for n in V2_ULTRAMAFIC}}


@pytest.mark.parametrize("name", ["picrite", "oceanite", "hawaiite", "basaltic-andesite",
                                  "lherzolite, spinel, xenolith"])
def test_v2_does_not_classify_unlisted_names(name):
    assert classify_rock(name, load_mapping(CSV_V2)) is None


# --- mapeamento v3 (v2 + nomes qualificados por mineral) ----------------------

CSV_V3 = CSV.with_name("rock_mapping_v3.csv")


def test_v3_keeps_every_v2_row_and_only_adds_qualified_names():
    v2, v3 = load_mapping(CSV_V2), load_mapping(CSV_V3)
    assert {k: v3.get(k) for k in v2} == v2
    added = {k: c for k, c in v3.items() if k not in v2}
    assert len(added) > 100
    for name, cls in added.items():
        root, _, qualifier = name.partition(",")
        assert qualifier.strip(), name           # so "raiz, mineral"
        assert v2.get(root.strip()) == cls, name  # classe = a da raiz, que ja estava no v2
        assert "xenolith" not in name and " / " not in name and "[" not in name, name


def test_v3_has_the_expected_examples_and_excludes_xenoliths():
    v3 = load_mapping(CSV_V3)
    assert v3["basalt, olivine"] == "mafic"
    assert v3["gabbro, hornblende"] == "mafic"
    assert v3["basalt, olivine-augite"] == "mafic"
    assert v3["pyroxenite, olivine"] == "ultramafic"
    assert v3["lherzolite, spinel"] == "ultramafic"
    assert "peridotite, xenolith" not in v3 and "lherzolite, spinel, xenolith" not in v3
    assert "basalt, olivine / gabbro" not in v3


# --- mapeamento v4 (v3 + nomes com xenolito; decisao do usuario em 2026-11-03) -

CSV_V4 = CSV.with_name("rock_mapping_v4.csv")


def test_v4_keeps_every_v3_row_and_adds_only_xenolith_names_with_the_root_class():
    v3, v4 = load_mapping(CSV_V3), load_mapping(CSV_V4)
    assert {k: v4.get(k) for k in v3} == v3
    added = {k: c for k, c in v4.items() if k not in v3}
    assert len(added) > 100
    for name, cls in added.items():
        root = name.partition(",")[0].strip()
        assert "xenolith" in name, name
        assert " / " not in name and "[" not in name, name
        assert v3.get(root) == cls, name          # classe = a da raiz, ja mapeada no v3


def test_v4_has_the_expected_xenolith_examples():
    v4 = load_mapping(CSV_V4)
    assert v4["lherzolite, spinel, xenolith"] == "ultramafic"
    assert v4["peridotite, xenolith"] == "ultramafic"
    assert v4["harzburgite, xenolith"] == "ultramafic"
    assert "dunite, xenolith / dunite" not in v4
