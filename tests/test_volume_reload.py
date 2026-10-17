"""VolumeData.reload() must read the file again the way it was first loaded."""

import math

import numpy as np
import SimpleITK as sitk

from vvv.maths.image import VolumeData


def _write(path, arr, direction=None):
    img = sitk.GetImageFromArray(arr)
    if direction is not None:
        img.SetDirection(direction)
    sitk.WriteImage(img, str(path))
    return str(path)


def test_reload_refreshes_data_range(tmp_path):
    p = _write(tmp_path / "a.nii", np.full((4, 8, 8), 10, np.float32))
    vol = VolumeData(p)
    assert vol.get_data_range() == (10.0, 10.0)
    _write(p, np.linspace(0, 100, 4 * 8 * 8, dtype=np.float32).reshape(4, 8, 8))
    vol.reload()
    assert vol.get_data_range() == (0.0, 100.0)


def test_reload_keeps_roi_loading_options(tmp_path):
    c, s = math.cos(math.radians(20)), math.sin(math.radians(20))
    oblique = (c, -s, 0, s, c, 0, 0, 0, 1)
    mask = np.zeros((10, 20, 20), np.float32)
    mask[3:7, 5:15, 5:15] = 1.0
    p = _write(tmp_path / "roi.nii", mask, oblique)
    vol = VolumeData(p, is_roi=True)
    assert set(np.unique(vol.data)) <= {0.0, 1.0}  # nearest neighbour when straightened

    mask[3:8, 4:16, 4:16] = 1.0  # file changes: different extent -> the full re-init path
    _write(p, mask, oblique)
    vol.reload()
    assert vol._load_kwargs["is_roi"] is True
    assert set(np.unique(vol.data)) <= {0.0, 1.0}  # still a label map, not interpolated
