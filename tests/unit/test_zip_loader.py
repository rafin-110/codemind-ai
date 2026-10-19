"""T-ZIP-01..06 and T-FLT-01/02: safe extraction and filtering."""

import os
import zipfile
import io

import pytest

from codemind import config
from codemind.ingestion.zip_loader import (
    UnsafeArchiveError, ingest_zip, inspect_zip, rehash_snapshot, zip_directory,
)
from tests.helpers import SAMPLE, make_zip


def test_valid_sample_zip_extracts_all_files(tmp_path):
    snap = ingest_zip(zip_directory(SAMPLE), tmp_path / "run", source="sample")
    paths = {f.rel_path for f in snap.included_files}
    assert {"main.py", "README.md", "grades/stats.py", "grades/storage.py", "grades/cli.py",
            "tests/test_stats.py"} <= paths
    for f in snap.included_files:
        assert (snap.root / f.rel_path).read_bytes() == (SAMPLE / f.rel_path).read_bytes()
        assert f.sha256 and len(f.sha256) == 64
    assert rehash_snapshot(snap) == snap.snapshot_hash
    assert "grades/" in snap.tree_text


def test_original_is_read_only(tmp_path):
    snap = ingest_zip(zip_directory(SAMPLE), tmp_path / "run")
    mode = os.stat(snap.root / "grades" / "stats.py").st_mode
    assert not mode & 0o222


@pytest.mark.parametrize("bad_name", ["../evil.py", "a/../../evil.py", "/etc/evil.py",
                                      "C:/evil.py", "a\\..\\evil.py"])
def test_path_traversal_rejected_and_nothing_written(tmp_path, bad_name):
    data = make_zip({"ok.py": "x = 1\n", bad_name: "print('pwned')\n"})
    with pytest.raises(UnsafeArchiveError):
        ingest_zip(data, tmp_path / "run")
    assert not (tmp_path / "evil.py").exists()
    assert not (tmp_path / "run" / "original").exists()


def test_symlink_rejected(tmp_path):
    data = make_zip({"ok.py": "x = 1\n"}, symlinks={"link": "/etc/passwd"})
    with pytest.raises(UnsafeArchiveError, match="symbolic link"):
        ingest_zip(data, tmp_path / "run")


def test_oversized_archive_rejected(monkeypatch):
    monkeypatch.setattr(config, "MAX_ZIP_BYTES", 100)
    with pytest.raises(UnsafeArchiveError, match="limit"):
        inspect_zip(make_zip({"a.py": "x" * 1000}))


def test_zip_bomb_ratio_rejected():
    # 5 MB of zeros compresses to a few KB -> ratio far above 100:1
    data = make_zip({"bomb.txt": b"\0" * (5 * 1024 * 1024)})
    with pytest.raises(UnsafeArchiveError, match="ratio"):
        inspect_zip(data)


def test_total_uncompressed_cap(monkeypatch):
    monkeypatch.setattr(config, "MAX_UNCOMPRESSED_BYTES", 50)
    with pytest.raises(UnsafeArchiveError, match="uncompressed"):
        inspect_zip(make_zip({"a.py": "x" * 40, "b.py": "y" * 40}))


def test_too_many_files(monkeypatch):
    monkeypatch.setattr(config, "MAX_FILES", 3)
    with pytest.raises(UnsafeArchiveError, match="entries"):
        inspect_zip(make_zip({f"f{i}.py": "x" for i in range(5)}))


def test_not_a_zip():
    with pytest.raises(UnsafeArchiveError, match="not a valid ZIP"):
        inspect_zip(b"this is not a zip")


def test_ignored_dirs_and_binary_skipped(tmp_path):
    data = make_zip({
        "app.py": "print('hi')\n",
        ".git/config": "[core]\n",
        "__pycache__/app.cpython-311.pyc": b"\x00\x01\x02",
        "node_modules/x/index.js": "module.exports = 1\n",
        "venv/lib/site.py": "x = 1\n",
        "logo.png": b"\x89PNG\r\n\x1a\n\x00\x00",
    })
    snap = ingest_zip(data, tmp_path / "run")
    assert [f.rel_path for f in snap.included_files] == ["app.py"]
    reasons = {f.rel_path: f.skipped_reason for f in snap.files}
    assert "ignored directory" in reasons[".git/config"]
    assert reasons["logo.png"] == "binary file"
    assert not (snap.root / ".git").exists()


def test_sensitive_files_inventoried_but_not_written(tmp_path):
    secret = "AWS_SECRET=abc123supersecret"
    data = make_zip({"app.py": "x = 1\n", ".env": secret, "keys/id_rsa": "PRIVATE KEY"})
    snap = ingest_zip(data, tmp_path / "run")
    reasons = {f.rel_path: f.skipped_reason for f in snap.files}
    assert reasons[".env"].startswith("sensitive")
    assert reasons["keys/id_rsa"].startswith("sensitive")
    assert not (snap.root / ".env").exists()
    assert secret not in snap.tree_text


def test_github_style_common_root_is_stripped(tmp_path):
    data = make_zip({"repo-main/app.py": "x = 1\n", "repo-main/README.md": "# Repo\n"})
    snap = ingest_zip(data, tmp_path / "run")
    assert {f.rel_path for f in snap.files} == {"app.py", "README.md"}


def test_header_size_mismatch_detected(tmp_path):
    # Forge a central directory that understates the size of an entry.
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as zf:
        zf.writestr("a.py", "x = 1234567890\n")
    raw = bytearray(buf.getvalue())
    cd = raw.rfind(b"PK\x01\x02")
    raw[cd + 24:cd + 28] = (3).to_bytes(4, "little")      # uncompressed size field
    with pytest.raises((UnsafeArchiveError, zipfile.BadZipFile)):
        ingest_zip(bytes(raw), tmp_path / "run")
