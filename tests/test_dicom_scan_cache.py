"""DICOM scan cache: a folder is reused only while its files are unchanged."""

import json
import os
import time

import pytest

import vvv.core.dicom_scan as ds
from vvv.core.controller import Controller


@pytest.fixture
def scan_env(tmp_path, monkeypatch):
    root = tmp_path / "root"
    for sub in ("a", "b"):
        (root / sub).mkdir(parents=True)
        (root / sub / "f1.dcm").write_bytes(b"x" * 10)
    cache_dir = tmp_path / "cache"
    monkeypatch.setattr(ds, "get_config_dir", lambda: cache_dir)
    calls = []

    def fake_scan_dir(d, reader, file_reader):
        if os.path.basename(d) == "broken":
            raise OSError("unreadable")
        calls.append(os.path.basename(d))
        files = sorted(os.path.join(d, f) for f in os.listdir(d))
        if not files:
            return []
        sid = f"uid_{os.path.basename(d)}"
        return [(sid, {"id": sid, "dir": d, "files": files, "tags": [("0008|0060", "Modality", "CT")],
                       "_base_x": 2, "_base_y": 2, "_base_z": 1})]

    monkeypatch.setattr(ds, "scan_dicom_dir", fake_scan_dir)
    fm = Controller().file

    def scan(**kw):
        calls.clear()
        last = None
        for u in fm.scan_dicom_folder(str(root), **kw):
            last = u
        return sorted(calls), last[2], last[3], fm.last_dicom_scan

    return root, cache_dir, scan


def test_unchanged_folders_come_from_the_cache(scan_env):
    root, _, scan = scan_env
    calls, series, _, info = scan()
    assert calls == ["a", "b", "root"] and info["cached"] == 0
    calls2, series2, _, info2 = scan()
    assert calls2 == [] and info2["cached"] == info2["dirs"] == 3
    assert sorted(s["id"] for s in series2) == sorted(s["id"] for s in series)
    assert all(isinstance(t, tuple) for s in series2 for t in s["tags"])


@pytest.mark.parametrize("change", ["content", "mtime", "added", "removed"])
def test_a_changed_folder_is_scanned_again(scan_env, change):
    root, _, scan = scan_env
    scan()
    f = root / "a" / "f1.dcm"
    if change == "content":
        f.write_bytes(b"y" * 11)
    elif change == "mtime":  # same size, rewritten in place
        st = f.stat()
        os.utime(f, ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000))
    elif change == "added":
        (root / "a" / "f2.dcm").write_bytes(b"z")
    else:
        f.unlink()
    calls, _, _, _ = scan()
    assert calls == ["a"]


def test_corrupt_or_old_cache_is_ignored(scan_env, monkeypatch):
    _, cache_dir, scan = scan_env
    scan()
    (cache_file,) = cache_dir.glob("dicom_cache/*.json")
    cache_file.write_text("{ not json")
    assert scan()[0] == ["a", "b", "root"]
    monkeypatch.setattr(ds, "CACHE_VERSION", ds.CACHE_VERSION + 1)  # new format
    assert scan()[0] == ["a", "b", "root"]
    assert scan()[0] == []


def test_rebuild_ignores_the_cache_and_rewrites_it(scan_env):
    _, _, scan = scan_env
    scan()
    calls, _, _, info = scan(use_cache=False)
    assert calls == ["a", "b", "root"] and info["cached"] == 0 and not info["use_cache"]
    assert scan()[0] == []


def test_failed_folder_is_not_cached_and_gone_folder_dropped(scan_env):
    root, cache_dir, scan = scan_env
    (root / "broken").mkdir()
    _, _, errors, _ = scan()
    assert len(errors) == 1
    _, _, errors2, info = scan()
    assert len(errors2) == 1 and info["cached"] == 3  # retried, not cached
    (root / "b" / "f1.dcm").unlink()
    (root / "b").rmdir()
    scan()
    (cache_file,) = cache_dir.glob("dicom_cache/*.json")
    dirs = json.loads(cache_file.read_text())["dirs"]
    assert not any(d.endswith(os.sep + "b") for d in dirs)


def test_is_dicom_part10(tmp_path):
    dcm = tmp_path / "x.dcm"
    dcm.write_bytes(b"\0" * 128 + b"DICM" + b"rest")
    other = tmp_path / "x.nii"
    other.write_bytes(b"\0" * 300)
    assert ds.is_dicom_part10(dcm) and not ds.is_dicom_part10(other)
    assert not ds.is_dicom_part10(tmp_path / "missing")
