"""VolumeData caches computed from `data` (range, nonzero bbox) are dropped
whenever `data` is replaced (C6: callers rely on the cached range)."""

import numpy as np
import SimpleITK as sitk

from vvv.core.controller import Controller
from vvv.maths.image import VolumeData


def _load(tmp_path, arr, name="img.nii"):
    path = str(tmp_path / name)
    sitk.WriteImage(sitk.GetImageFromArray(arr), path)
    return path


def test_assigning_data_drops_the_caches(tmp_path):
    vol = VolumeData(_load(tmp_path, np.arange(1000, dtype=np.float32).reshape(10, 10, 10)))
    assert vol.get_data_range() == (0.0, 999.0)
    vol.__dict__["_nonzero_bbox_cache"] = {"key": "stale"}

    vol.data = vol.data * 2.0

    assert "_nonzero_bbox_cache" not in vol.__dict__
    assert vol.get_data_range() == (0.0, 1998.0)


def _bake_translated(tmp_path, tx_mm):
    c = Controller()
    c.use_history = False
    c.save_settings = lambda: None
    arr = np.full((10, 20, 20), 50.0, np.float32)
    arr[:, :, 17:] = 100.0  # the max only lies in a band at one edge
    img_id = c.file.load_image(_load(tmp_path, arr, f"img_{tx_mm}.nii"))
    vol, vs = c.volumes[img_id], c.view_states[img_id]
    assert vol.get_data_range() == (50.0, 100.0)  # cached before the bake
    tx = sitk.Euler3DTransform()
    tx.SetTranslation((tx_mm, 0.0, 0.0))
    vs.space.transform = tx
    vs.space.is_active = True
    c.bake_transform_to_volume(img_id)
    assert c.wait_for_jobs(timeout=10)
    return vol


def test_bake_updates_the_data_range(tmp_path):
    # One of the two directions moves the max band out of the field of view
    vols = [_bake_translated(tmp_path, tx) for tx in (8.0, -8.0)]
    vol = next(v for v in vols if float(np.max(v.data)) < 100.0)
    expected = (float(np.min(vol.data)), float(np.max(vol.data)))
    assert vol.get_data_range() == expected  # not the pre-bake cache
