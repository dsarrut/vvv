"""Profile samples cache (PC4): follows in-place transform edits and data
replacement, and keeps no closed image alive."""

import numpy as np
import SimpleITK as sitk

from vvv.core.controller import Controller
from vvv.core.view_state import ProfileLineState


def _setup(tmp_path):
    c = Controller()
    c.use_history = False
    c.save_settings = lambda: None
    arr = np.tile(np.arange(40, dtype=np.float32), (10, 20, 1))  # value = x index
    path = str(tmp_path / "grad.nii")
    sitk.WriteImage(sitk.GetImageFromArray(arr), path)
    img_id = c.file.load_image(path)
    p = ProfileLineState()
    p.pt1_phys = np.array([5.0, 10.0, 5.0])
    p.pt2_phys = np.array([25.0, 10.0, 5.0])
    return c, img_id, p


def _samples(c, img_id, p):
    _, values = c.profiles.get_profile_data(img_id, p)
    return np.array(values)


def test_in_place_transform_edit_changes_the_samples(tmp_path):
    c, img_id, p = _setup(tmp_path)
    vs = c.view_states[img_id]
    vs.base_display_data = None  # sample through the transform, not the buffer
    before = _samples(c, img_id, p)

    vs.space.set_manual_transform(3.0, 0, 0, 0, 0, 0)  # SetTranslation on the same object
    vs.space.is_active = True
    moved = _samples(c, img_id, p)
    vs.space.set_manual_transform(-3.0, 0, 0, 0, 0, 0)
    moved_back = _samples(c, img_id, p)

    assert not np.allclose(before, moved)
    assert not np.allclose(moved, moved_back)


def test_replaced_data_is_sampled_again(tmp_path):
    c, img_id, p = _setup(tmp_path)
    vol, vs = c.volumes[img_id], c.view_states[img_id]
    vs.base_display_data = None
    before = _samples(c, img_id, p)
    vol.data = vol.data * 2.0
    np.testing.assert_allclose(_samples(c, img_id, p), before * 2.0)


def test_closing_the_image_empties_its_cache(tmp_path):
    c, img_id, p = _setup(tmp_path)
    _samples(c, img_id, p)
    assert any(k[0] == img_id for k in c.profiles._cache)
    c.file.close_image(img_id)
    assert not any(k[0] == img_id for k in c.profiles._cache)
