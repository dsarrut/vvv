"""A side-car .tfm of any rigid ITK type is applied at load; a non-rigid one
is refused with its reason in the status bar (issue 53)."""

import numpy as np
import SimpleITK as sitk

from vvv.app import build_app


def _ct(tmp_path, disk_transform):
    img = sitk.GetImageFromArray(np.zeros((8, 8, 8), np.float32))
    sitk.WriteImage(img, str(tmp_path / "ct.nii.gz"))
    sitk.WriteTransform(disk_transform, str(tmp_path / "ct.tfm"))
    c, _ = build_app(use_history=False)
    return c, c.file.load_image(str(tmp_path / "ct.nii.gz"))


def test_translation_sidecar_is_applied(tmp_path):
    c, vid = _ct(tmp_path, sitk.TranslationTransform(3, (5.0, 0.0, -1900.0)))
    space = c.view_states[vid].space
    assert space.from_sidecar and space.is_active
    np.testing.assert_allclose(space.transform.TransformPoint((0.0, 0.0, 0.0)), (-5.0, 0.0, 1900.0), atol=1e-9)


def test_bspline_sidecar_is_refused_with_its_reason(tmp_path):
    c, vid = _ct(tmp_path, sitk.BSplineTransform(3))
    assert c.view_states[vid].space.transform is None
    msg, level = c.status_message
    assert level == "warning"
    assert "side-car not read" in msg and "not a linear" in msg
