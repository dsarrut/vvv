import pytest
import numpy as np
from unittest.mock import MagicMock
import dearpygui.dearpygui as dpg
from vvv.utils import ViewMode


def test_gui_registration_sliders(headless_gui_app):
    """Verifies that the DearPyGui registration sliders perfectly map to the ITK math engine."""
    controller, gui, viewer, vs_id = headless_gui_app
    vs = viewer.view_state

    reg_plugin = next(p for p in gui.plugins if p.plugin_id == "registration_plugin")
    reg_ctrl = reg_plugin._controller
    pid = "registration_plugin"

    # 1. Initialize the GUI slider items if they don't exist in the headless context
    for key in [
        f"{pid}_drag_reg_tx",
        f"{pid}_drag_reg_ty",
        f"{pid}_drag_reg_tz",
        f"{pid}_drag_reg_rx",
        f"{pid}_drag_reg_ry",
        f"{pid}_drag_reg_rz",
    ]:
        if not dpg.does_item_exist(key):
            dpg.add_drag_float(tag=key, default_value=0.0, parent="PrimaryWindow")

    # 2. Simulate User dragging the X-Translation slider to 15.0 mm
    dpg.set_value(f"{pid}_drag_reg_tx", 15.0)

    # 3. Trigger the GUI update method
    vs.space.is_active = True  # Transform must be active to read it
    reg_ctrl.on_reg_manual_changed(None, None, None)

    # 4. Assert the underlying SimpleITK Transform actually received the 15.0mm translation!
    translation = vs.space.transform.GetTranslation()
    assert translation[0] == 15.0
    assert translation[1] == 0.0


def test_registration_fusion_isolation(headless_gui_app, synthetic_volume_factory):
    """Verifies that a fused overlay (B) stays pinned to the world when the base image (A) transforms."""
    controller, gui, viewer, vsA_id = headless_gui_app
    vsA = viewer.view_state
    
    pathB = synthetic_volume_factory("imgB.nii.gz", val=200.0)
    vsB_id = controller.file.load_image(pathB)
    vsB = controller.view_states[vsB_id]
    
    vsA.set_overlay(vsB_id, controller.volumes[vsB_id], controller)
    
    # 1. Baseline: no transforms
    layer_B = viewer._package_overlay_layer()
    assert viewer.active_overlay_shift_x == 0.0
    assert viewer.active_overlay_shift_y == 0.0
    
    # 2. Transform A (Base Image moves +10mm in X)
    vsA.space.set_manual_transform(10, 0, 0, 0, 0, 0)
    vsA.space.is_active = True
    
    # The overlay (B) must mathematically shift backwards (-10mm) on the screen to stay glued to the world
    layer_B_A_moved = viewer._package_overlay_layer()
    assert viewer.active_overlay_shift_x == -10.0
    
    # 3. Transform B (Overlay Image moves +5mm in X)
    vsB.space.set_manual_transform(5, 0, 0, 0, 0, 0)
    vsB.space.is_active = True
    
    # Base shifted +10, Overlay shifted +5 -> net visual shift of the overlay on screen is -5
    layer_B_both_moved = viewer._package_overlay_layer()
    assert viewer.active_overlay_shift_x == -5.0


def test_registration_preview_generation(headless_gui_app):
    """Verifies that the fast 2D affine preview correctly populates the ViewState cache."""
    controller, gui, viewer, vs_id = headless_gui_app
    vs = viewer.view_state

    # 1. Mock extracting a rotation transform (90 degrees around Z)
    R = np.eye(3, dtype=np.float64)
    R[0, 0], R[0, 1] = 0.0, -1.0
    R[1, 0], R[1, 1] = 1.0, 0.0
    center = np.zeros(3, dtype=np.float64)
    
    viewer_slices = {id(viewer): ("base", viewer.orientation, viewer.slice_idx)}
    
    reg_plugin = next(p for p in gui.plugins if p.plugin_id == "registration_plugin")
    reg_ctrl = reg_plugin._controller

    # 2. Fire the preview generator directly (simulating the background worker)
    reg_ctrl._preview_version = 1
    reg_ctrl._trigger_fast_preview(vs_id, version=1, R=R, center=center, viewer_slices=viewer_slices)
    
    # 3. Assert the cache was populated correctly
    assert vs._preview_R is R
    assert vs._preview_center is center
    key = (viewer.orientation, viewer.slice_idx)
    assert key in viewer._preview_slices
    assert viewer._preview_slices[key] is not None
    assert viewer._preview_slices[key].shape == (viewer.get_slice_shape()[0], viewer.get_slice_shape()[1])


def test_registration_auto_update_display(headless_gui_app):
    """Verifies that the Auto-Update Display checkbox correctly schedules a resample."""
    controller, gui, viewer, vs_id = headless_gui_app

    reg_plugin = next(p for p in gui.plugins if p.plugin_id == "registration_plugin")
    reg_ctrl = reg_plugin._controller
    pid = "registration_plugin"

    # 1. Mock the resample method to track if it gets called
    controller.resample_image = MagicMock()

    # 2. Enable Auto-Update and ensure sliders exist
    check_tag = f"{pid}_check_reg_auto_resample"
    if not dpg.does_item_exist(check_tag):
        dpg.add_checkbox(tag=check_tag, default_value=True, parent="PrimaryWindow")
    else:
        dpg.set_value(check_tag, True)
    slider_tags = [
        f"{pid}_drag_reg_rx",
        f"{pid}_drag_reg_ry",
        f"{pid}_drag_reg_rz",
        f"{pid}_drag_reg_tx",
        f"{pid}_drag_reg_ty",
        f"{pid}_drag_reg_tz",
    ]
    for key in slider_tags:
        if not dpg.does_item_exist(key):
            dpg.add_drag_float(tag=key, default_value=0.0, parent="PrimaryWindow")

    # 3. Trigger a manual change
    reg_ctrl.on_reg_manual_changed(None, None, None)

    # 4. Verify the debounce timer was set
    assert reg_ctrl._auto_timer is not None
    assert reg_ctrl._auto_timer_vs_id == vs_id

    # 5. Fire the timer manually to avoid waiting for 0.7s in tests
    reg_ctrl._fire_auto_resample()

    # 6. Assert the ITK resample was requested
    controller.resample_image.assert_called_once_with(vs_id)


def test_registration_sync_behavior(headless_gui_app, synthetic_volume_factory):
    """Verifies that transforming an image correctly maintains spatial sync with grouped viewers."""
    controller, gui, viewerA, vsA_id = headless_gui_app
    vsA = viewerA.view_state
    
    pathB = synthetic_volume_factory("imgB.nii.gz", val=200.0)
    vsB_id = controller.file.load_image(pathB)
    viewerB = controller.viewers["V2"]
    viewerB.set_image(vsB_id)
    vsB = viewerB.view_state
    
    # 1. Sync them
    controller.set_sync_group(vsA_id, 1)
    controller.set_sync_group(vsB_id, 1)
    
    # 2. Transform A by +15mm in X
    vsA.space.set_manual_transform(15, 0, 0, 0, 0, 0)
    vsA.space.is_active = True
    
    # 3. Click on the center of A (forces a world coordinate evaluation through the transform)
    viewerA.update_crosshair_data(pix_x=10, pix_y=10)
    controller.sync.propagate_sync(vsA_id)
    
    # 4. Assert B's physical coordinate identically snapped to A's transformed world coordinate
    np.testing.assert_allclose(vsB.camera.crosshair_phys_coord, vsA.camera.crosshair_phys_coord)