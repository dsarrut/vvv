import pytest
import os
import numpy as np
import SimpleITK as sitk
from unittest.mock import patch
from vvv.core.controller import Controller
from vvv.maths.image import VolumeData
from vvv.utils import ViewMode

def test_reload_image_failure_recovery(headless_gui_app):
    controller, gui, viewer, vs_id = headless_gui_app
    vs = controller.view_states[vs_id]
    vol = controller.volumes[vs_id]

    # Save original arrays & caches
    original_data = vol.data
    original_sitk = vol.sitk_image
    
    # Intentionally corrupt the file path to cause FileNotFoundError on reload
    old_file_paths = vol.file_paths
    vol.file_paths = ["/non_existent_directory/non_existent_file.nii.gz"]

    controller.reload_image(vs_id)

    # Verify that the volume's data and C++ bindings were fully restored
    assert vol.data is original_data
    assert vol.sitk_image is original_sitk
    assert "Reload failed" in controller.status_message

    # Clean up file path
    vol.file_paths = old_file_paths


def test_reload_roi_failure_recovery(headless_gui_app, tmp_path):
    controller, gui, viewer, vs_id = headless_gui_app
    vs = controller.view_states[vs_id]

    # Create and load a dummy binary ROI
    roi_data = np.zeros(controller.volumes[vs_id].shape3d, dtype=np.uint8)
    roi_data[2, 2, 2] = 1
    roi_img = sitk.GetImageFromArray(roi_data)
    roi_path = str(tmp_path / "test_roi.nii.gz")
    sitk.WriteImage(roi_img, roi_path)

    roi_id = controller.roi.load_binary_mask(vs_id, roi_path)
    roi_state = vs.rois[roi_id]
    roi_vol = controller.volumes[roi_id]

    # Populate dummy polygons
    roi_state.polygons[ViewMode.AXIAL][2] = [[10.0, 10.0]]

    # Save original references
    original_data = roi_vol.data
    original_sitk = roi_vol.sitk_image

    # Corrupt path to cause reload failure
    roi_vol.file_paths = ["/non_existent_dir/non_existent_roi.nii.gz"]

    controller.roi.reload_roi(vs_id, roi_id)

    # Verify that original ROI data and polygons are restored
    assert roi_vol.data is original_data
    assert roi_vol.sitk_image is original_sitk
    assert 2 in roi_state.polygons[ViewMode.AXIAL]
    assert roi_state.polygons[ViewMode.AXIAL][2] == [[10.0, 10.0]]


def test_bake_transform_failure_recovery(headless_gui_app):
    controller, gui, viewer, vs_id = headless_gui_app
    vs = controller.view_states[vs_id]
    vol = controller.volumes[vs_id]

    # Setup a dummy transform
    tx = sitk.Euler3DTransform()
    tx.SetTranslation((1.0, 2.0, 3.0))
    vs.space.transform = tx
    vs.space.is_active = True

    # Save original references
    original_data = vol.data
    original_sitk = vol.sitk_image

    # Force an exception during resampler.Execute by mocking sitk.ResampleImageFilter.Execute
    with patch("SimpleITK.ResampleImageFilter.Execute", side_effect=RuntimeError("Simulated ITK error")):
        with patch("threading.Thread") as mock_thread:
            controller.bake_transform_to_volume(vs_id)
            # Retrieve target function and run it synchronously
            target_func = mock_thread.call_args[1]["target"]
            target_func()

    # Verify recovery
    assert vol.data is original_data
    assert vol.sitk_image is original_sitk
    assert vs.space.transform is tx
    assert vs.space.is_active is True
    assert "Bake failed" in controller.status_message
