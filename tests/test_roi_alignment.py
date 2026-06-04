import pytest
import numpy as np
import SimpleITK as sitk

def test_load_3d_mask_on_4d_base(headless_4d_overlay_app, tmp_path):
    """
    Verifies that loading a 3D binary mask on a 4D base volume and calculating
    detailed stats does not crash due to dimension/direction mismatches.
    """
    controller, gui, viewer_v1, vs_id_3d, viewer_v2, vs_id_4d = headless_4d_overlay_app

    # Create a 3D binary mask with the spatial dimensions of the 4D base image
    base_vol = controller.volumes[vs_id_4d]
    shape = base_vol.shape3d  # (20, 30, 30)

    mask_data = np.zeros(shape, dtype=np.uint8)
    mask_data[5:15, 5:15, 5:15] = 1

    mask_img = sitk.GetImageFromArray(mask_data)
    mask_img.SetSpacing(base_vol.spacing.tolist())
    mask_img.SetOrigin(base_vol.origin.tolist())
    # Spatial direction from base_vol (3D matrix representation)
    mask_img.SetDirection(base_vol.matrix.flatten().tolist())

    mask_path = str(tmp_path / "test_3d_mask.nii.gz")
    sitk.WriteImage(mask_img, mask_path)

    # This should succeed without raising ValueError: operands could not be broadcast
    roi_id = controller.roi.load_binary_mask(vs_id_4d, mask_path)
    assert roi_id in controller.volumes
    roi_vol = controller.volumes[roi_id]
    assert roi_vol.roi_bbox is not None

    # Get ROI plugin controller
    roi_plugin = next((p for p in gui.plugins if p.plugin_id == "roi_plugin"), None)
    assert roi_plugin is not None
    roi_ctrl = roi_plugin._controller

    # Calculate detailed stats, which should succeed without raising SimpleITK RuntimeError: vector dimension mismatch
    stats = roi_ctrl.compute_detailed_roi_stats(vs_id_4d, roi_id)
    assert stats is not None
    assert "voxel_count" in stats
    assert stats["voxel_count"] > 0
