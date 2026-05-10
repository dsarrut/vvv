import numpy as np
import dearpygui.dearpygui as dpg
from vvv.utils import ViewMode


def test_gui_registration_sliders(headless_gui_app):
    """Verifies that the DearPyGui registration sliders perfectly map to the ITK math engine."""
    controller, gui, viewer, vs_id = headless_gui_app
    vs = viewer.view_state

    # 1. Initialize the GUI slider items if they don't exist in the headless context
    for key in [
        "drag_reg_tx",
        "drag_reg_ty",
        "drag_reg_tz",
        "drag_reg_rx",
        "drag_reg_ry",
        "drag_reg_rz",
    ]:
        if not dpg.does_item_exist(key):
            dpg.add_drag_float(tag=key, default_value=0.0)

    # 2. Simulate User dragging the X-Translation slider to 15.0 mm
    dpg.set_value("drag_reg_tx", 15.0)

    # 3. Trigger the GUI update method
    vs.space.is_active = True  # Transform must be active to read it
    gui.reg_ui.apply_transform_and_keep_world_fixed(viewer)

    # 4. Assert the underlying SimpleITK Transform actually received the 15.0mm translation!
    translation = vs.space.transform.GetTranslation()
    assert translation[0] == 15.0
    assert translation[1] == 0.0


def test_registration_pin_model_invariants(headless_gui_app):
    """Verifies the Pin Model: dragging a transform moves the image, not the camera or world pin."""
    controller, gui, viewer, vs_id = headless_gui_app
    vs = viewer.view_state

    viewer.set_orientation(ViewMode.AXIAL)
    viewer.update_crosshair_data(pix_x=10, pix_y=10)

    # Initialize sliders
    for key in gui.reg_ui.SLIDER_TAGS:
        if not dpg.does_item_exist(key):
            dpg.add_drag_float(tag=key, default_value=0.0)

    orig_phys = vs.camera.crosshair_phys_coord.copy()
    orig_pan = list(vs.camera.pan[ViewMode.AXIAL])
    orig_vox = vs.camera.crosshair_voxel.copy()

    # 1. Start a drag (Translation)
    vs.space.is_active = True
    gui.reg_ui._ensure_drag_anchor(vs)
    
    dpg.set_value("drag_reg_tx", 10.0)
    gui.reg_ui._on_transform_drag(viewer)

    # Physical pin stays EXACTLY the same
    np.testing.assert_allclose(vs.camera.crosshair_phys_coord, orig_phys)
    
    # Pan compensated so the screen stays still
    new_pan = vs.camera.pan[ViewMode.AXIAL]
    assert new_pan[0] != orig_pan[0]
    
    # Voxel changed (the anatomy under the crosshair changed)
    assert vs.camera.crosshair_voxel[0] != orig_vox[0]

    # 2. Settle the transform
    gui.reg_ui._on_transform_settled(viewer)
    np.testing.assert_allclose(vs.camera.crosshair_phys_coord, orig_phys)
    assert vs._reg_anchor_world is None


def test_registration_sync_group_behavior(headless_gui_app, synthetic_volume_factory):
    """Verifies that transforming Image A properly maintains anatomical sync with Image B."""
    controller, gui, viewerA, vsA_id = headless_gui_app
    vsA = viewerA.view_state
    
    # Load Image B into Viewer 2
    pathB = synthetic_volume_factory("imgB.nii.gz", val=200.0)
    vsB_id = controller.file.load_image(pathB)
    viewerB = controller.viewers["V2"]
    viewerB.set_image(vsB_id)
    vsB = viewerB.view_state
    
    # Sync them
    controller.set_sync_group(vsA_id, 1)
    controller.set_sync_group(vsB_id, 1)
    
    # Initialize sliders
    for key in gui.reg_ui.SLIDER_TAGS:
        if not dpg.does_item_exist(key):
            dpg.add_drag_float(tag=key, default_value=0.0)
    
    # Click on an anatomical point in Image A
    viewerA.update_crosshair_data(pix_x=5, pix_y=5)
    controller.sync.propagate_sync(vsA_id)
    
    orig_phys = vsA.camera.crosshair_phys_coord.copy()
    orig_vox_B = vsB.camera.crosshair_voxel.copy()

    # Transform Image A
    vsA.space.is_active = True
    gui.reg_ui._ensure_drag_anchor(vsA)
    dpg.set_value("drag_reg_tx", 15.0)
    gui.reg_ui._on_transform_drag(viewerA)
    
    # A's crosshair physical should be same
    np.testing.assert_allclose(vsA.camera.crosshair_phys_coord, orig_phys)
    
    # B's crosshair physical must match A's
    np.testing.assert_allclose(vsB.camera.crosshair_phys_coord, vsA.camera.crosshair_phys_coord)
    
    # B's voxel must be IDENTICAL to before, because B didn't move in the world!
    np.testing.assert_allclose(vsB.camera.crosshair_voxel, orig_vox_B)


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