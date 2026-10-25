"""Default viewer orientations count displayed images, not fused overlays."""

import numpy as np
import SimpleITK as sitk

from vvv.app import build_app
from vvv.utils import ViewMode

A, S, C = ViewMode.AXIAL, ViewMode.SAGITTAL, ViewMode.CORONAL


def _controller(tmp_path, n):
    c, _ = build_app(use_history=False, with_gui=False)
    c.save_settings = lambda: None
    ids = []
    for i in range(n):
        p = str(tmp_path / f"img{i}.nii")
        sitk.WriteImage(sitk.GetImageFromArray(np.zeros((4, 6, 6), np.float32)), p)
        ids.append(c.file.load_image(p))
    return c, ids


def _orientations(c):
    return [c.viewers[t].orientation for t in ["V1", "V2", "V3", "V4"]]


def test_fused_overlay_does_not_count_as_a_displayed_image(tmp_path):
    c, (ct, pet) = _controller(tmp_path, 2)
    c.view_states[ct].set_overlay(pet, c.volumes[pet])
    c.default_viewers_orientation()
    assert _orientations(c) == [A, S, C, A]  # the 1-image layout


def test_two_displayed_images_keep_the_two_image_layout(tmp_path):
    c, _ = _controller(tmp_path, 2)
    c.default_viewers_orientation()
    assert _orientations(c) == [A, S, A, S]
