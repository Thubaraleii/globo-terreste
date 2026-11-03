"""Mapeamento versionado de nomes de rocha para classe (mafic/ultramafic).

So casa por igualdade exata do nome normalizado; nomes desconhecidos,
compostos ou vazios ficam nulos (nada e inferido).
"""
import re
import unicodedata
from pathlib import Path

import pandas as pd

CLASSES = ("mafic", "ultramafic")


def normalize_rock_name(s: str | None) -> str | None:
    """Minusculas, sem acento, espacos colapsados; vazio vira None."""
    if s is None or (not isinstance(s, str) and pd.isna(s)):
        return None
    decomposed = unicodedata.normalize("NFKD", str(s))
    plain = "".join(c for c in decomposed if not unicodedata.combining(c))
    out = re.sub(r"\s+", " ", plain.lower()).strip()
    return out or None


def load_mapping(csv: Path) -> dict[str, str]:
    """Le `name,class` e devolve {nome normalizado: classe}."""
    df = pd.read_csv(csv, dtype=str, keep_default_na=False)
    mapping: dict[str, str] = {}
    for i, row in df.iterrows():
        raw_name, cls = row["name"], row["class"].strip()
        name = normalize_rock_name(raw_name)
        if name is None:
            raise ValueError(f"linha {i + 2}: nome vazio")
        if cls not in CLASSES:
            raise ValueError(
                f"linha {i + 2} ({raw_name!r}): classe invalida {cls!r}; "
                f"use {' ou '.join(CLASSES)}"
            )
        if mapping.get(name, cls) != cls:
            raise ValueError(
                f"linha {i + 2} ({raw_name!r}): {name!r} ja mapeado como "
                f"{mapping[name]!r}, conflita com {cls!r}"
            )
        mapping[name] = cls
    return mapping


def classify_rock(name: str | None, mapping: dict[str, str]) -> str | None:
    """Classe da rocha ou None (sem substring, sem inferencia)."""
    key = normalize_rock_name(name)
    return None if key is None else mapping.get(key)
