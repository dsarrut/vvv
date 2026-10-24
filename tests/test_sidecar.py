"""Side-car files next to an image (vvv.core.sidecar)."""

import json

import numpy as np
import pytest

from vvv.core.sidecar import (
    SidecarError,
    read_sidecar,
    sidecar_path,
    transform_sidecar_path,
    update_sidecar,
)


def test_sidecar_path_rule(tmp_path):
    for name in ("ct.nii.gz", "ct.nii", "ct.mha", "ct.mhd", "ct.mha.gz"):
        assert sidecar_path(tmp_path / name) == str(tmp_path / "ct.json")
    assert sidecar_path(tmp_path / "ct.nii.gz", ".tfm") == str(tmp_path / "ct.tfm")


def test_read_sidecar(tmp_path):
    img = tmp_path / "ct.nii.gz"
    assert read_sidecar(img) == (None, str(tmp_path / "ct.json"), None)
    (tmp_path / "ct.json").write_text('{"unit": "HU"}')
    assert read_sidecar(img)[0] == {"unit": "HU"}
    (tmp_path / "ct.json").write_text("{not json")
    content, _, error = read_sidecar(img)
    assert content is None and error.startswith("ct.json:")


def test_update_sidecar_merges_and_never_clobbers(tmp_path):
    img = tmp_path / "ct.mha"
    js = tmp_path / "ct.json"
    assert update_sidecar(img, {"unit": None}) is None  # nothing to write
    assert not js.exists()

    update_sidecar(img, {"unit": "Gy"})
    js.write_text(json.dumps({"unit": "Gy", "note": "mine"}))
    update_sidecar(img, {"unit": "cGy"})
    assert json.loads(js.read_text()) == {"unit": "cGy", "note": "mine"}
    update_sidecar(img, {"unit": None})  # removed, the file stays
    assert json.loads(js.read_text()) == {"note": "mine"}
    update_sidecar(img, {}, drop=lambda k: k == "note")
    assert json.loads(js.read_text()) == {}

    js.write_text("{broken")
    with pytest.raises(SidecarError):
        update_sidecar(img, {"unit": "HU"})
    assert js.read_text() == "{broken"


def test_transform_sidecar_path(tmp_path):
    img = tmp_path / "ct.nii.gz"
    assert transform_sidecar_path(img) is None
    (tmp_path / "ct.mat").write_text("")
    assert transform_sidecar_path(img) == str(tmp_path / "ct.mat")
    (tmp_path / "ct.tfm").write_text("")
    assert transform_sidecar_path(img) == str(tmp_path / "ct.tfm")  # preferred


def test_transform_sidecar_other_names(tmp_path):
    img = tmp_path / "ct.nii.gz"
    (tmp_path / "ct.nii.gz.tfm").write_text("")  # the full file name
    assert transform_sidecar_path(img) == str(tmp_path / "ct.nii.gz.tfm")
    (tmp_path / "ct.TFM").write_text("")  # upper case, before the full name
    assert transform_sidecar_path(img).lower() == str(tmp_path / "ct.tfm").lower()

    # a series (one file per slice): the folder's transform
    series = tmp_path / "series"
    series.mkdir()
    slice0 = series / "IM0001.dcm"
    assert transform_sidecar_path(slice0, series=True) is None
    (tmp_path / "series.tfm").write_text("")
    assert transform_sidecar_path(slice0) is None  # only for a series
    assert transform_sidecar_path(slice0, series=True) == str(tmp_path / "series.tfm")


def test_label_map_save_keeps_the_other_keys(tmp_path):
    """J2: saving ROIs as a label map replaces the label entries of an existing
    json side-car, keeps its other keys (unit...)."""
    from vvv.plugins.roi.control_roi import RoiPluginController

    out = tmp_path / "labels.nii.gz"
    (tmp_path / "labels.json").write_text(
        json.dumps({"unit": "a.u.", "1": {"name": "old"}, "7": "stale"})
    )
    mask = np.zeros((2, 3, 3), np.uint8)
    mask[0, 0, 0] = 1
    snapshot = {
        "shape3d": (2, 3, 3),
        "sitk_image": None,
        "rois": [
            {"name": "liver", "color": [255, 0, 0], "data": mask, "bbox": None, "shape3d": (2, 3, 3)}
        ],
    }
    RoiPluginController("roi_plugin").write_rois_as_labels(snapshot, str(out))
    assert json.loads((tmp_path / "labels.json").read_text()) == {
        "unit": "a.u.",
        "1": {"name": "liver", "color": [255, 0, 0]},
    }


def test_label_parser_ignores_other_keys():
    from vvv.ui.ui_sequences import _parse_label_map_json

    labels, colors = _parse_label_map_json(
        {"unit": "a.u.", "1": {"name": "liver", "color": [255, 0, 0]}, "2": "lung"}
    )
    assert labels == {1: "liver", 2: "lung"} and colors == {1: [255, 0, 0]}
    assert _parse_label_map_json(None) == ({}, {})
