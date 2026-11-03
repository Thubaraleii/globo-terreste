"""Manifesto de downloads brutos com hash SHA-256 (data/raw/manifest.json)."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_MANIFEST = Path("data/raw/manifest.json")


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _load(manifest: Path) -> dict:
    manifest = Path(manifest)
    if manifest.exists():
        return json.loads(manifest.read_text(encoding="utf-8"))
    return {}


def record_download(manifest: Path, source_id: str, url: str, file: Path, license: str) -> dict:
    file = Path(file)
    entry = {
        "url": url,
        "file": file.name,
        "sha256": _sha256(file),
        "license": license,
        "downloaded_at": datetime.now(timezone.utc).isoformat(),
    }
    data = _load(manifest)
    data[source_id] = entry
    manifest = Path(manifest)
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return entry


def verify_manifest(manifest: Path, raw_dir: Path) -> list[str]:
    """Retorna ids cujo arquivo falta ou tem hash divergente."""
    bad = []
    for source_id, entry in _load(manifest).items():
        f = Path(raw_dir) / entry["file"]
        if not f.exists() or _sha256(f) != entry["sha256"]:
            bad.append(source_id)
    return bad
