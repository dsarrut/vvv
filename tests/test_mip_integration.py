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
    
    # Toggle depth cueing on
    mip_plugin._controller.on_depth_cueing_toggle(None, True, None)
    assert state.depth_cueing
    
    # Change axis to Z
    mip_plugin._controller.on_axis_changed(None, "Z", None)
    assert state.projection_axis == "Z"
    assert viewer.orientation == ViewMode.AXIAL
    
    base_layer_z = viewer._package_base_layer()
    assert base_layer_z.preview_override.shape == (H, W)
