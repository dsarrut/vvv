"""ROIs computed in a worker (defer=True) are only registered by register_roi()."""

import numpy as np
import SimpleITK as sitk

from vvv.core.controller import Controller


def test_deferred_binary_mask_registers_only_on_register_roi(tmp_path):
    base_path, roi_path = str(tmp_path / "base.nii"), str(tmp_path / "roi.nii")
    sitk.WriteImage(sitk.GetImageFromArray(np.zeros((8, 16, 16), np.float32)), base_path)
    mask = np.zeros((8, 16, 16), np.uint8)
    mask[2:6, 4:12, 4:12] = 1
    sitk.WriteImage(sitk.GetImageFromArray(mask), roi_path)

    c = Controller()
    c.use_history = False
    c.save_settings = lambda: None
    base = c.file.load_image(base_path)
    n_volumes = len(c.volumes)

    pending = c.roi.load_binary_mask(base, roi_path, name="lesion", defer=True)
    assert len(c.volumes) == n_volumes and not c.view_states[base].rois  # nothing yet

    roi_id = c.roi.register_roi(pending)
    assert c.view_states[base].rois[roi_id].name == "lesion"
    assert c.volumes[roi_id] is pending["vol"]
    assert c.roi.register_roi(None) is None
