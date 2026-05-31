import numpy as np
from vvv.utils import ViewMode


def test_mip_integration(headless_gui_app):
    controller, gui, viewer, base_id = headless_gui_app
    
    # Verify the MIP plugin is loaded
    mip_plugin = next((p for p in gui.plugins if p.plugin_id == "mip_plugin"), None)
    assert mip_plugin is not None
    
    # Initially MIP should be disabled
    state = mip_plugin._controller.get_image_state(base_id)
    assert not state.mip_enabled
    
    # Retrieve base layer before enabling MIP
    base_layer_normal = viewer._package_base_layer()
    assert base_layer_normal.preview_override is None
    
    # Enable MIP Mode
    mip_plugin._controller.on_mip_toggle(None, True, None)
    assert state.mip_enabled
    
    # Retrieve base layer with MIP enabled
    base_layer_mip = viewer._package_base_layer()
    assert base_layer_mip.preview_override is not None
    
    # Verify shape matching. The test volume data dimensions:
    vol_shape = viewer.volume.data.shape
    if len(vol_shape) == 3:
        D, H, W = vol_shape
    else:
        T, D, H, W = vol_shape
    
    # Enabling MIP mode defaults to projection axis Y, which triggers coronal view
    assert viewer.orientation == ViewMode.CORONAL
    assert base_layer_mip.preview_override.shape == (D, W)
    
    # Set depth cueing value
    mip_plugin._controller.on_depth_cueing_changed(None, 0.7, None)
    assert state.depth_cueing == 0.7
    
    # Change orientation on the viewer directly (as F1 / F2 / F3 would do)
    viewer.set_orientation(ViewMode.AXIAL)
    mip_plugin.update(mip_plugin._controller._api)  # Triggers update_ui which does the reverse-sync
    assert state.projection_axis == "Z"
    
    base_layer_z = viewer._package_base_layer()
    assert base_layer_z.preview_override.shape == (H, W)
    
    # Test caching: dragging slice index should keep preview cached
    initial_preview = base_layer_z.preview_override
    viewer.slice_idx = 10
    base_layer_scrolled = viewer._package_base_layer()
    assert base_layer_scrolled.preview_override is initial_preview  # same object!

    # Test rotation defaults
    import dearpygui.dearpygui as dpg
    assert state.rotation_angle == 0.0
    assert state.rotation_step == 5.0

    # Modify rotation angle via controller callback
    mip_plugin._controller.on_rotation_changed(None, 15.0, None)
    assert state.rotation_angle == 15.0

    # Retrieve base layer at 15 degrees (should invalidate cache and calculate new preview)
    base_layer_rot15 = viewer._package_base_layer()
    assert base_layer_rot15.preview_override is not None
    assert base_layer_rot15.preview_override is not initial_preview

    # Test caching with same rotation angle
    viewer.slice_idx = 12
    base_layer_rot15_scrolled = viewer._package_base_layer()
    assert base_layer_rot15_scrolled.preview_override is base_layer_rot15.preview_override

    # Test keyboard shortcut Left (should decrease angle by rotation_step: 15.0 -> 10.0)
    viewer.on_key_press(dpg.mvKey_Left)
    assert state.rotation_angle == 10.0

    # Test keyboard shortcut Right (should increase angle by rotation_step: 10.0 -> 15.0)
    viewer.on_key_press(dpg.mvKey_Right)
    assert state.rotation_angle == 15.0

    # Test changing rotation step
    mip_plugin._controller.on_step_changed(None, 10.0, None)
    assert state.rotation_step == 10.0

    # Test keyboard shortcut Left again with new step (15.0 -> 5.0)
    viewer.on_key_press(dpg.mvKey_Left)
    assert state.rotation_angle == 5.0

