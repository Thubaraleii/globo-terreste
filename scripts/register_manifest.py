"""Registra em data/raw/manifest.json os arquivos brutos baixados em 2026-11-03.

Nao acessa a rede: so calcula o SHA-256 dos arquivos ja presentes em
data/raw/ (via pipeline.common.manifest.record_download). Para o GEOROC, a URL
de cada arquivo vem do JSON da API do Dataverse salvo em
data/raw/_probe/georoc_rocks_dataset.json (lido como dado), e o tamanho e o
MD5 locais sao conferidos contra os declarados la; divergencia aborta.

Uso: .venv/Scripts/python scripts/register_manifest.py [--raw data/raw]
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline.common.manifest import record_download  # noqa: E402
from pipeline.realsources import (  # noqa: E402
    GEOROC_DIR, GEOROC_FILES, GLIM_FILE, GVP_FILE, PB2002_FILE, PB2002_PLATES_FILE,
    PB2002_PLATES_URL, USGS_FILE, USGS_URL,
    georoc_source_id,
)

GVP_URL = ("https://webservices.volcano.si.edu/geoserver/GVP-VOTW/wfs?service=WFS&version=1.0.0"
           "&request=GetFeature&typeName=GVP-VOTW:Smithsonian_VOTW_Holocene_Volcanoes"
           "&outputFormat=application/json")
PB2002_URL = ("https://raw.githubusercontent.com/fraxen/tectonicplates/master/GeoJSON/"
              "PB2002_boundaries.json")
GLIM_URL = "https://www.dropbox.com/s/9vuowtebp9f1iud/LiMW_GIS%202015.gdb.zip?dl=1"
DATAVERSE_FILE_URL = "https://data.goettingen-research-online.de/api/access/datafile/{id}"

FIXED = [
    ("gvp", GVP_URL, GVP_FILE,
     "Termos de uso próprios do GVP (ver volcano.si.edu); citação obrigatória"),
    ("pb2002", PB2002_URL, PB2002_FILE, "Open Data Commons Attribution License 1.0"),
    ("pb2002-plates", PB2002_PLATES_URL, PB2002_PLATES_FILE,
     "Open Data Commons Attribution License 1.0"),
    ("usgs", USGS_URL, USGS_FILE, "USGS: domínio público (verificar termos)"),
    ("glim", GLIM_URL, GLIM_FILE, "NÃO declarada na fonte — uso local; não publicar"),
]


def _md5(path: Path) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def georoc_entries(raw: Path) -> list[tuple[str, str, str, str]]:
    probe = json.loads((raw / "_probe" / "georoc_rocks_dataset.json").read_text(encoding="utf-8"))
    version = probe["data"]["latestVersion"]
    licence = version["license"]["name"]
    files = {f["label"]: f["dataFile"] for f in version["files"]}
    out = []
    for name in GEOROC_FILES:
        info = files[name]
        local = raw / GEOROC_DIR / name
        if local.stat().st_size != info["filesize"] or _md5(local) != info["md5"]:
            raise SystemExit(f"{name}: tamanho/MD5 local difere do declarado no Dataverse")
        out.append((georoc_source_id(name), DATAVERSE_FILE_URL.format(id=info["id"]),
                    f"{GEOROC_DIR}/{name}", licence))
    return out


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw", type=Path, default=ROOT / "data" / "raw")
    args = parser.parse_args(argv)
    entries = FIXED + georoc_entries(args.raw)
    manifest = args.raw / "manifest.json"
    for source_id, url, rel, licence in entries:
        entry = record_download(manifest, source_id, url, args.raw / rel, licence)
        print(f"{source_id}: {entry['sha256'][:12]} {rel}")
    print(f"{len(entries)} arquivos em {manifest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
