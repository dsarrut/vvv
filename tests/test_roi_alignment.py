import os
import time
import pytest
import numpy as np
import SimpleITK as sitk
import dearpygui.dearpygui as dpg

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


def test_reload_all_modified_rois(headless_gui_app, tmp_path):
    """
    Verifies that the reload all modified ROIs button is only shown when there
    are outdated/modified ROIs, and that clicking it reloads all outdated ROIs.
    """
    controller, gui, viewer, vs_id = headless_gui_app

    # Load an ROI mask
    shape = controller.volumes[vs_id].shape3d
    mask_data = np.zeros(shape, dtype=np.uint8)
    mask_data[2, 2, 2] = 1
    mask_img = sitk.GetImageFromArray(mask_data)
    mask_path = str(tmp_path / "test_roi.nii.gz")
    sitk.WriteImage(mask_img, mask_path)

    roi_id = controller.roi.load_binary_mask(vs_id, mask_path)
    roi_vol = controller.volumes[roi_id]

    # Get ROI plugin
    roi_plugin = next((p for p in gui.plugins if p.plugin_id == "roi_plugin"), None)
    assert roi_plugin is not None

    # Initially, the ROI is not outdated, so the reload all button should be hidden
    roi_vol._is_outdated = False
    roi_plugin._ui.refresh_rois_ui()
    btn_tag = roi_plugin._ui._t("btn_roi_reload_all")
    assert dpg.is_item_shown(btn_tag) is False

    # Touch the file on disk to simulate external modification (set mtime to future)
    new_mtime = time.time() + 10.0
    os.utime(mask_path, (new_mtime, new_mtime))

    # Force controller to check outdated status immediately by resetting throttle
    roi_vol._last_check_time = 0
    controller.tick()

    # Verify that it detected the modification and updated the flag
    assert roi_vol._is_outdated is True

    # Refresh the UI and verify that the reload all button becomes visible
    roi_plugin._ui.refresh_rois_ui()
    assert dpg.is_item_shown(btn_tag) is True

    # Trigger the reload all callback
    roi_plugin._ui.on_roi_reload_all(None, None, None)

    # After reload, the ROI is no longer outdated, and the button should be hidden
    assert roi_vol._is_outdated is False
    roi_plugin._ui.refresh_rois_ui()
    assert dpg.is_item_shown(btn_tag) is False


def test_reload_label_map_with_json_outdated(headless_gui_app, tmp_path):
    """
    Verifies that label map ROIs with a sidecar JSON file for label names
    correctly track modification times of both files and turn outdated.
    """
    controller, gui, viewer, vs_id = headless_gui_app

    # Create a 3D label map image with labels 1 and 2
    shape = controller.volumes[vs_id].shape3d
    mask_data = np.zeros(shape, dtype=np.uint8)
    mask_data[2, 2, 2] = 1
    mask_data[3, 3, 3] = 2
    mask_img = sitk.GetImageFromArray(mask_data)
    
    mask_path = str(tmp_path / "labels.nii.gz")
    sitk.WriteImage(mask_img, mask_path)
    
    # Write the JSON file
    json_path = str(tmp_path / "labels.json")
    import json
    with open(json_path, "w") as f:
        json.dump({"1": "Liver", "2": "Spleen"}, f)

    # Load the label map using the sequence generator
    from vvv.ui.ui_sequences import load_label_map_sequence
    for _ in load_label_map_sequence(gui, controller, vs_id, mask_path):
        pass

    # Verify that the two ROIs are loaded with correct names
    vs = controller.view_states[vs_id]
    rois = vs.rois
    assert len(rois) == 2
    
    # Find Liver and Spleen ROIs
    liver_id = next(rid for rid, rstate in rois.items() if rstate.name == "Liver")
    spleen_id = next(rid for rid, rstate in rois.items() if rstate.name == "Spleen")
    
    liver_vol = controller.volumes[liver_id]
    spleen_vol = controller.volumes[spleen_id]
    
    # Verify file_paths contains both image and JSON
    assert len(liver_vol.file_paths) == 2
    assert mask_path in liver_vol.file_paths
    assert json_path in liver_vol.file_paths

    # Verify initially not outdated
    assert liver_vol._is_outdated is False
    assert spleen_vol._is_outdated is False

    # Scenario A: Touch the image file
    new_mtime = time.time() + 10.0
    os.utime(mask_path, (new_mtime, new_mtime))
    
    liver_vol._last_check_time = 0
    spleen_vol._last_check_time = 0
    controller.tick()
    
    # Verify that both are marked as outdated when the image is modified
    assert liver_vol._is_outdated is True
    assert spleen_vol._is_outdated is True

    # Reload them to clear outdated status
    roi_plugin = next((p for p in gui.plugins if p.plugin_id == "roi_plugin"), None)
    assert roi_plugin is not None
    roi_plugin._ui.on_roi_reload_all(None, None, None)

    # Process tasks to run the reload generator
    while gui.tasks:
        try:
            next(gui.tasks[0])
        except StopIteration:
            gui.tasks.pop(0)

    # Re-fetch new ROI volumes after they were re-created
    rois = vs.rois
    assert len(rois) == 2
    liver_id = next(rid for rid, rstate in rois.items() if rstate.name == "Liver")
    spleen_id = next(rid for rid, rstate in rois.items() if rstate.name == "Spleen")
    liver_vol = controller.volumes[liver_id]
    spleen_vol = controller.volumes[spleen_id]

    # Verify outdated status is reset
    assert liver_vol._is_outdated is False
    assert spleen_vol._is_outdated is False

    # Scenario B: Touch the JSON file instead
    new_json_mtime = time.time() + 20.0
    os.utime(json_path, (new_json_mtime, new_json_mtime))

    liver_vol._last_check_time = 0
    spleen_vol._last_check_time = 0
    controller.tick()

    # Verify that both are marked as outdated when the JSON file is modified
    assert liver_vol._is_outdated is True
    assert spleen_vol._is_outdated is True

    # Reload again to verify cleanup
    roi_plugin._ui.on_roi_reload_all(None, None, None)
    while gui.tasks:
        try:
            next(gui.tasks[0])
        except StopIteration:
            gui.tasks.pop(0)

    rois = vs.rois
    liver_id = next(rid for rid, rstate in rois.items() if rstate.name == "Liver")
    spleen_id = next(rid for rid, rstate in rois.items() if rstate.name == "Spleen")
    assert controller.volumes[liver_id]._is_outdated is False
    assert controller.volumes[spleen_id]._is_outdated is False


