"""A worker replacing a resampled image must not free it while the main thread
may still read numpy views of it (GetArrayViewFromImage keeps no reference)."""

import numpy as np
import SimpleITK as sitk

from vvv.core.controller import Controller


def _write(path, value, shape=(20, 64, 64), spacing=(1.0, 1.0, 1.0)):
    img = sitk.GetImageFromArray(np.full(shape, value, np.float32))
    img.SetSpacing(spacing)
    sitk.WriteImage(img, str(path))
    return str(path)


def test_replaced_overlay_stays_readable_until_next_tick(tmp_path):
    c = Controller()
    c.use_history = False
    c.save_settings = lambda: None
    base = c.file.load_image(_write(tmp_path / "base.nii", 1.0))
    ov = c.file.load_image(_write(tmp_path / "ov.nii", 7.0, spacing=(2.0, 2.0, 2.0)))
    base_vs, ov_vs = c.view_states[base], c.view_states[ov]
    base_vs.set_overlay(ov, ov_vs.volume)
    c._apply_overlay_resample(base_vs, ov_vs)
    c.tick()

    in_use = base_vs.display.overlay_data  # a view the main thread is reading
    expected = np.array(in_use)

    c._apply_overlay_resample(base_vs, ov_vs)  # worker replaces the overlay
    assert base_vs.display.overlay_data is not in_use
    junk = [np.full(expected.shape, -1.0, np.float32) for _ in range(8)]  # reuse memory
    assert np.array_equal(in_use, expected)  # old image still alive
    assert c._retired

    c.tick()  # next main-thread frame: released
    assert not c._retired
    del junk
