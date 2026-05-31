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
