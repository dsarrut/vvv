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
    gui.reg_ui.on_reg_manual_changed(None, None, None)

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