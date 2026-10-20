"""Outside a resampled DVF overlay there is no displacement (not a fake vector)."""

import numpy as np
import SimpleITK as sitk

from vvv.core.overlay_resampler import resample_overlay
from vvv.maths.image import VolumeData


def _base(tmp_path):
    p = str(tmp_path / "base.nii")
    sitk.WriteImage(sitk.GetImageFromArray(np.zeros((10, 20, 20), np.float32)), p)
    return VolumeData(p)


def test_dvf_overlay_is_zero_outside_its_field(tmp_path):
    comps = [sitk.GetImageFromArray(np.full((4, 6, 6), v, np.float32)) for v in (5.0, -7.0, 3.0)]
    dvf = sitk.Compose(comps)  # small field in a corner of the base
    p = str(tmp_path / "dvf.mha")
    sitk.WriteImage(dvf, p)
    dvf_vol = VolumeData(p)
    assert dvf_vol.is_dvf

    _, data, _ = resample_overlay(_base(tmp_path), dvf_vol, None, None)
    assert data.shape[0] == 3  # (C, Z, Y, X)
    assert np.all(data[:, 8:, 15:, 15:] == 0.0)  # outside: no vector
    assert np.allclose(data[:, 1, 2, 2], [5.0, -7.0, 3.0])  # inside: the field


def test_image_overlay_outside_is_its_minimum(tmp_path):
    arr = np.full((4, 6, 6), 40.0, np.float32)
    arr[0, 0, 0] = 10.0
    p = str(tmp_path / "ov.nii")
    sitk.WriteImage(sitk.GetImageFromArray(arr), p)
    _, data, _ = resample_overlay(_base(tmp_path), VolumeData(p), None, None)
    assert np.all(data[8:, 15:, 15:] == 10.0)
