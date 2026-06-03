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
    
    # Enabling MIP mode defaults to projection axis Y, which triggers sagittal view (F2)
    assert viewer.orientation == ViewMode.SAGITTAL
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
    assert mip_plugin._controller.get_cache_size(viewer.tag) >= 1
    
    # Test caching: dragging slice index should keep preview cached
    initial_preview = base_layer_z.preview_override
    viewer.slice_idx = 10
    base_layer_scrolled = viewer._package_base_layer()
    assert base_layer_scrolled.preview_override is initial_preview  # same object!
    
    # Test cache clearing
    mip_plugin._controller.clear_viewer_cache(viewer.tag)
    assert mip_plugin._controller.get_cache_size(viewer.tag) == 0

    # Retrieve base layer again to rebuild cache
    base_layer_z = viewer._package_base_layer()
    initial_preview = base_layer_z.preview_override

    # Test rotation defaults
    import dearpygui.dearpygui as dpg
    assert state.rotation_angles == {"X": 0.0, "Y": 0.0, "Z": 0.0}
    assert state.rotation_step == 10.0

    # Current orientation is ViewMode.AXIAL (projection axis "Z")
    assert viewer.orientation == ViewMode.AXIAL

    # Modify rotation angle via controller callback (should affect axis Z)
    mip_plugin._controller.on_rotation_changed(None, 15.0, None)
    assert state.rotation_angles["Z"] == 15.0
    assert state.rotation_angles["Y"] == 0.0
    assert state.rotation_angles["X"] == 0.0

    # Retrieve base layer at 15 degrees (should invalidate cache and calculate new preview)
    base_layer_rot15 = viewer._package_base_layer()
    assert base_layer_rot15.preview_override is not None
    assert base_layer_rot15.preview_override is not initial_preview

    # Test caching with same rotation angle
    viewer.slice_idx = 12
    base_layer_rot15_scrolled = viewer._package_base_layer()
    assert base_layer_rot15_scrolled.preview_override is base_layer_rot15.preview_override

    # Change orientation to ViewMode.CORONAL (projection axis "Y")
    viewer.set_orientation(ViewMode.CORONAL)
    mip_plugin.update(mip_plugin._controller._api)  # reverse-syncs orientation to axis Y
    assert state.projection_axis == "Y"
    # Rotation angle for axis Y should still be 0.0 (independent!)
    assert state.rotation_angles["Y"] == 0.0
    assert state.rotation_angles["Z"] == 15.0

    # Test keyboard shortcut Left on CORONAL (should decrease axis Y angle by rotation_step: 0.0 -> -10.0)
    viewer.on_key_press(dpg.mvKey_Left)
    assert state.rotation_angles["Y"] == -10.0
    assert state.rotation_angles["Z"] == 15.0

    # Test keyboard shortcut Right on CORONAL (should increase axis Y angle by rotation_step: -10.0 -> 0.0)
    viewer.on_key_press(dpg.mvKey_Right)
    assert state.rotation_angles["Y"] == 0.0

    # Test changing rotation step
    mip_plugin._controller.on_step_changed(None, 10.0, None)
    assert state.rotation_step == 10.0

    # Test keyboard shortcut Left again with new step (0.0 -> -10.0)
    viewer.on_key_press(dpg.mvKey_Left)
    assert state.rotation_angles["Y"] == -10.0
    assert state.rotation_angles["Z"] == 15.0

    # Test dictionary-based angle cache hit:
    # Switch back to AXIAL (axis Z), which had rotation angle 15.0
    viewer.set_orientation(ViewMode.AXIAL)
    mip_plugin.update(mip_plugin._controller._api)
    assert state.projection_axis == "Z"
    
    # Retrieve base layer (should hit the cache and return the exact same base_layer_rot15 preview object)
    base_layer_refetched = viewer._package_base_layer()
    assert base_layer_refetched.preview_override is base_layer_rot15.preview_override  # O(1) Cache Hit!


def test_mip_viewer_isolation(headless_gui_app):
    controller, gui, viewer_v1, base_id = headless_gui_app
    
    mip_plugin = next((p for p in gui.plugins if p.plugin_id == "mip_plugin"), None)
    assert mip_plugin is not None
    
    # Get standard viewer V3 from controller (both V1 and V3 display base_id)
    viewer_v3 = controller.viewers["V3"]
    
    # State references
    state_v1 = mip_plugin._controller.get_viewer_state(base_id, "V1")
    state_v3 = mip_plugin._controller.get_viewer_state(base_id, "V3")
    
    # Initially both are independent and disabled
    assert not state_v1.mip_enabled
    assert not state_v3.mip_enabled
    
    # 1. Enable MIP on viewer_v1
    gui.set_context_viewer(viewer_v1)
    mip_plugin._controller.on_mip_toggle(None, True, None)
    assert state_v1.mip_enabled
    assert not state_v3.mip_enabled  # v3 should still be disabled!
    
    # 2. Check base layers
    base_v1 = viewer_v1._package_base_layer()
    base_v3 = viewer_v3._package_base_layer()
    assert base_v1.preview_override is not None
    assert base_v3.preview_override is None
    
    # 3. Change settings for V3 specifically
    gui.set_context_viewer(viewer_v3)
    # Modify depth cueing on V3
    mip_plugin._controller.on_depth_cueing_changed(None, 0.8, None)
    assert state_v3.depth_cueing == 0.8
    assert state_v1.depth_cueing == 1.0  # V1 should be unaffected
    
    # Modify rotation on V3 active axis (set orientation first to SAGITTAL -> axis Y)
    viewer_v3.set_orientation(ViewMode.SAGITTAL)
    mip_plugin._controller.on_rotation_changed(None, 45.0, None)
    assert state_v3.rotation_angles["Y"] == 45.0
    assert state_v1.rotation_angles["Y"] == 0.0
    
    # 4. Test serialization
    serialized = mip_plugin._controller.serialize_image_state(base_id)
    # New format contains keys "V1", "V3" etc.
    assert "V1" in serialized
    assert "V3" in serialized
    assert serialized["V1"]["mip_enabled"] is True
    assert serialized["V3"]["mip_enabled"] is False
    assert serialized["V3"]["depth_cueing"] == 0.8
    # Backward compatibility key check (flat fields represent V1)
    assert serialized["mip_enabled"] is True
    assert serialized["depth_cueing"] == 1.0
    
    # 5. Test restore of new format
    new_image_id = "test_image_new"
    # Call on_image_loaded to initialize new states
    mip_plugin._controller.on_image_loaded(new_image_id)
    mip_plugin._controller.restore_image_state(new_image_id, serialized)
    
    restored_v1 = mip_plugin._controller.get_viewer_state(new_image_id, "V1")
    restored_v3 = mip_plugin._controller.get_viewer_state(new_image_id, "V3")
    assert restored_v1.mip_enabled is True
    assert restored_v3.mip_enabled is False
    assert restored_v3.depth_cueing == 0.8
    assert restored_v3.rotation_angles["Y"] == 45.0
    
    # 6. Test restore of old flat format (all viewers get the flat state)
    old_serialized = {
        "mip_enabled": True,
        "projection_axis": "Z",
        "depth_cueing": 0.4,
        "invert_contrast": False,
        "rotation_angles": {"X": 10.0, "Y": 20.0, "Z": 30.0},
        "rotation_step": 3.0,
    }
    old_image_id = "test_image_old"
    mip_plugin._controller.on_image_loaded(old_image_id)
    mip_plugin._controller.restore_image_state(old_image_id, old_serialized)
    
    for tag in ["V1", "V2", "V3", "V4"]:
        restored = mip_plugin._controller.get_viewer_state(old_image_id, tag)
        assert restored.mip_enabled is True
        assert restored.depth_cueing == 0.4
        assert restored.rotation_angles["Z"] == 30.0
        assert restored.rotation_step == 3.0


def test_mip_sync_propagation(headless_gui_app):
    controller, gui, viewer_v1, base_id = headless_gui_app
    
    mip_plugin = next((p for p in gui.plugins if p.plugin_id == "mip_plugin"), None)
    assert mip_plugin is not None
    
    # V1 displays vs_id1 (base_id), V2 displays vs_id2
    viewer_v2 = controller.viewers["V2"]
    overlay_id = viewer_v2.image_id
    assert overlay_id is not None
    assert overlay_id != base_id
    
    # Enable MIP on both viewers
    gui.set_context_viewer(viewer_v1)
    mip_plugin._controller.on_mip_toggle(None, True, None)
    
    gui.set_context_viewer(viewer_v2)
    mip_plugin._controller.on_mip_toggle(None, True, None)
    
    # Link all images (same sync group)
    controller.sync.link_all()
    
    # Check states
    state_v1 = mip_plugin._controller.get_viewer_state(base_id, "V1")
    state_v2 = mip_plugin._controller.get_viewer_state(overlay_id, "V2")
    
    # 1. Modify rotation on V1 and check propagation to V2
    gui.set_context_viewer(viewer_v1)
    viewer_v1.set_orientation(ViewMode.AXIAL)
    viewer_v2.set_orientation(ViewMode.AXIAL)
    
    mip_plugin._controller.on_rotation_changed(None, 30.0, None)
    assert state_v1.rotation_angles["Z"] == 30.0
    assert state_v2.rotation_angles["Z"] == 30.0  # Propagated!
    
    # 2. Modify depth cueing on V1 and check propagation to V2
    mip_plugin._controller.on_depth_cueing_changed(None, 0.65, None)
    assert state_v1.depth_cueing == 0.65
    assert state_v2.depth_cueing == 0.65  # Propagated!
    
    # Clean up sync link
    controller.sync.unlink_all()


def test_mip_fusion_precompute(headless_gui_app):
    import time
    controller, gui, viewer, base_id = headless_gui_app
    
    mip_plugin = next((p for p in gui.plugins if p.plugin_id == "mip_plugin"), None)
    assert mip_plugin is not None
    
    # Get overlay image
    overlay_id = controller.viewers["V2"].image_id
    assert overlay_id is not None
    
    # Enable fusion overlay on viewer V1 (set B as overlay of A)
    gui.set_context_viewer(viewer)
    viewer.view_state.set_overlay(overlay_id, controller.volumes[overlay_id])
    controller._apply_overlay_resample(viewer.view_state, controller.view_states[overlay_id])
    assert viewer.view_state.display.overlay is not None
    
    # Enable MIP Mode
    mip_plugin._controller.on_mip_toggle(None, True, None)
    
    # Retrieve base layer (triggers precomputation of both base and overlay)
    base_layer = viewer._package_base_layer()
    assert base_layer.preview_override is not None
    
    # Wait for background precompute thread to finish populating cache.
    # Total unique angles: 36 (since 360 / 10 = 36).
    # Total entries should be: 36 for base + 36 for overlay = 72.
    start_time = time.time()
    while time.time() - start_time < 5.0:
        size = mip_plugin._controller.get_cache_size(viewer.tag)
        if size >= 72:
            break
        time.sleep(0.1)
        
    final_precompute_size = mip_plugin._controller.get_cache_size(viewer.tag)
    assert final_precompute_size >= 72
    
    # Now modify the rotation angle to 10.0 degrees (one of the precomputed angles)
    mip_plugin._controller.on_rotation_changed(None, 10.0, None)
    
    # Package base and overlay layers
    base_layer_rot = viewer._package_base_layer()
    overlay_layer_rot = viewer._package_overlay_layer()
    
    assert base_layer_rot.preview_override is not None
    assert overlay_layer_rot.preview_override is not None
    
    # The cache size must NOT have increased, because both were hits!
    assert mip_plugin._controller.get_cache_size(viewer.tag) == final_precompute_size


def test_mip_4d_arrow_keys(headless_4d_overlay_app):
    import dearpygui.dearpygui as dpg
    controller, gui, viewer_v1, vs_id_3d, viewer_v2, vs_id_4d = headless_4d_overlay_app
    
    mip_plugin = next((p for p in gui.plugins if p.plugin_id == "mip_plugin"), None)
    assert mip_plugin is not None
    
    # Enable MIP Mode on viewer_v2 (which has the 4D image)
    gui.set_context_viewer(viewer_v2)
    mip_plugin._controller.on_mip_toggle(None, True, None)
    
    state_v2 = mip_plugin._controller.get_viewer_state(vs_id_4d, "V2")
    assert state_v2.mip_enabled
    
    # Initial time index should be 0
    assert viewer_v2.view_state.camera.time_idx == 0
    
    # Press Up arrow key — should increment time index to 1
    viewer_v2.on_key_press(dpg.mvKey_Up)
    assert viewer_v2.view_state.camera.time_idx == 1
    
    # Press Down arrow key — should decrement time index back to 0
    viewer_v2.on_key_press(dpg.mvKey_Down)
    assert viewer_v2.view_state.camera.time_idx == 0
    
    # Press Down arrow key again — should wrap to 3 (since num_timepoints is 4)
    viewer_v2.on_key_press(dpg.mvKey_Down)
    assert viewer_v2.view_state.camera.time_idx == 3
