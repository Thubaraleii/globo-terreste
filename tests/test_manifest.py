import json

from pipeline.common.manifest import record_download, verify_manifest


def test_verify_manifest_detects_changed_file(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    f = raw / "a.txt"
    f.write_text("one")
    manifest = raw / "manifest.json"
    entry = record_download(manifest, "src1", "http://x/a.txt", f, "CC0")
    assert len(entry["sha256"]) == 64
    assert verify_manifest(manifest, raw) == []
    f.write_text("two")
    assert verify_manifest(manifest, raw) == ["src1"]
    assert "src1" in json.loads(manifest.read_text())
