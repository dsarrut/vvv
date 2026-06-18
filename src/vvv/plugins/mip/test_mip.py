import numpy as np
from vvv.plugins.mip.math_mip import compute_mip_projection


def test_mip_projections():
    # Create a simple 3D volume (D=4, H=3, W=5)
    data = np.zeros((4, 3, 5), dtype=np.float32)
    data[2, 1, 3] = 100.0  # z=2, y=1, x=3
    data[0, 2, 4] = 50.0   # z=0, y=2, x=4

    # 1. Project along Z (axial) -> output shape (H=3, W=5)
    mip_z = compute_mip_projection(data, axis="Z", depth_cueing=False)
    assert mip_z.shape == (3, 5)
    assert mip_z[1, 3] == 100.0
    assert mip_z[2, 4] == 50.0

    # 2. Project along Y (coronal) -> output shape (D=4, W=5)
    mip_y = compute_mip_projection(data, axis="Y", depth_cueing=False)
    assert mip_y.shape == (4, 5)
    assert mip_y[2, 3] == 100.0
    assert mip_y[0, 4] == 50.0

    # 3. Project along X (sagittal) -> output shape (D=4, H=3)
    mip_x = compute_mip_projection(data, axis="X", depth_cueing=False)
    assert mip_x.shape == (4, 3)
    assert mip_x[2, 1] == 100.0
    assert mip_x[0, 2] == 50.0


def test_mip_depth_cueing():
    # Create a volume where voxel values increase along Z
    data = np.zeros((10, 3, 3), dtype=np.float32)
    for z in range(10):
        data[z, :, :] = float(z + 1) * 10.0  # z=0: 10, z=9: 100

    # With no depth cueing, the maximum value (100.0) is at z=9
    mip_z_no_cue = compute_mip_projection(data, axis="Z", depth_cueing=False)
    assert np.allclose(mip_z_no_cue, 100.0)

    # With depth cueing (strength=0.9):
    # At z=0: factor = 1.0 -> 10.0 * 1.0 = 10.0
    # At z=9: factor = 1.0 - 0.9 * (9/9) = 0.1 -> 100.0 * 0.1 = 10.0
    # Let's check a middle voxel, e.g. z=5: value = 60.0. factor = 1.0 - 0.9 * (5/9) = 0.5 -> 60.0 * 0.5 = 30.0
    # The maximum attenuated value along the ray should be greater than 10.0.
    mip_z_cue = compute_mip_projection(data, axis="Z", depth_cueing=True, depth_cueing_strength=0.9)
    assert np.all(mip_z_cue > 10.0)
    assert np.allclose(mip_z_cue, 30.0)  # Max should be 30.0 at z=5


def test_mip_rotation():
    # Simple volume (D=5, H=5, W=5)
    data = np.zeros((5, 5, 5), dtype=np.float32)
    data[2, 2, 2] = 100.0  # Center voxel is hot-spot
    
    # 0 degree rotation should match non-rotated projection
    mip_y_0 = compute_mip_projection(data, axis="Y", depth_cueing=False, rotation_angle=0.0)
    mip_y_normal = compute_mip_projection(data, axis="Y", depth_cueing=False)
    assert np.allclose(mip_y_0, mip_y_normal)
    
    # 45 degree rotation
    mip_y_45 = compute_mip_projection(data, axis="Y", depth_cueing=False, rotation_angle=45.0)
    assert mip_y_45.shape == mip_y_normal.shape
    # Center voxel (2,2) should still project to the center area
    assert mip_y_45[2, 2] == 100.0


def test_mip_scroll_rotation():
    from unittest.mock import MagicMock
    from vvv.ui.viewer import SliceViewer
    from vvv.utils import ViewMode

    # Setup mock controller and GUI
    controller = MagicMock()
    
    # Mock view_states dict to satisfy the real viewer.view_state and viewer.volume properties
    mock_view_state = MagicMock()
    mock_view_state.volume = MagicMock()
    controller.view_states = {"test_image": mock_view_state}
    
    # Mock MIP Plugin and controller
    mip_plugin = MagicMock()
    mip_plugin.plugin_id = "mip_plugin"
    
    # Mock gui and plugins
    gui = MagicMock()
    gui.plugins = [mip_plugin]
    controller.gui = gui
    
    # Create the viewer
    viewer = SliceViewer("V1", controller)
    
    # Setup viewer attributes to satisfy checks
    viewer.image_id = "test_image"
    viewer.is_image_orientation = MagicMock(return_value=True)
    viewer.orientation = ViewMode.AXIAL
    
    # Setup MIP viewer state
    class MockMIPState:
        mip_enabled = True
        rotation_angles = {"X": 0.0, "Y": 0.0, "Z": 0.0}
        rotation_step = 5.0
        
    mip_state = MockMIPState()
    mip_plugin._controller.get_viewer_state.return_value = mip_state
    
    # Perform scroll up (delta=1)
    viewer.on_scroll(1)
    
    # Verify rotation angle Z has increased by rotation_step (5.0)
    assert mip_state.rotation_angles["Z"] == 5.0
    mip_plugin._controller.propagate_rotation.assert_called_once_with("test_image", mip_state.rotation_angles)
    
    # Perform scroll down (delta=-2)
    mip_plugin._controller.propagate_rotation.reset_mock()
    viewer.on_scroll(-2)
    assert mip_state.rotation_angles["Z"] == -5.0
    mip_plugin._controller.propagate_rotation.assert_called_once_with("test_image", mip_state.rotation_angles)

    # Test angle wrapping (rotate past 180 deg)
    mip_state.rotation_angles["Z"] = 179.0
    viewer.on_scroll(1)  # 179.0 + 5.0 = 184.0 -> wraps to -176.0
    assert mip_state.rotation_angles["Z"] == -176.0


def test_mip_save_movie():
    from unittest.mock import MagicMock, patch
    from vvv.plugins.mip.control_mip import MIPPluginController
    from vvv.utils import ViewMode
    import numpy as np

    controller = MIPPluginController("mip_plugin")
    api = MagicMock()
    controller.bind(api)

    viewer = MagicMock()
    viewer.tag = "V1"
    viewer.image_id = "test_image"
    viewer.orientation = ViewMode.CORONAL
    viewer.slice_idx = 10
    viewer.view_state = MagicMock()
    viewer.view_state.display.overlay = None

    viewer.volume = MagicMock()
    viewer.volume.get_physical_aspect_ratio.return_value = (1.0, 2.0)

    # mock get_viewer_state
    mock_state = MagicMock()
    mock_state.rotation_angles = {"X": 0.0, "Y": 0.0, "Z": 0.0}
    mock_state.rotation_step = 90.0  # Large step to minimize frames (4 frames)
    mock_state.invert_contrast = False
    controller._states = {"test_image": {"V1": mock_state}}

    # mock package methods on viewer
    base_layer = MagicMock()
    overlay_layer = None
    viewer._package_base_layer.return_value = base_layer
    viewer._package_overlay_layer.return_value = overlay_layer

    # mock SliceRenderer.get_slice_rgba
    dummy_rgba = np.zeros(20 * 20 * 4, dtype=np.float32)
    # mock show_loading_modal, hide_loading_modal, and Image
    with patch("vvv.ui.ui_notifications.show_loading_modal") as mock_show, \
         patch("vvv.ui.ui_notifications.hide_loading_modal") as mock_hide, \
         patch("vvv.maths.image.SliceRenderer.get_slice_rgba", return_value=(dummy_rgba, (20, 20))), \
         patch("PIL.Image.fromarray") as mock_fromarray:
        
        mock_img = MagicMock()
        mock_fromarray.return_value = mock_img

        # Execute generator
        gen = controller._save_movie_sequence(viewer, "dummy.gif")
        list(gen)  # consume generator fully

        # Assertions
        # Original rotation angle should be restored to 0.0
        assert mock_state.rotation_angles["Y"] == 0.0
        # save was called on the first image (which was the resized image)
        mock_img.resize.return_value.save.assert_called_once()
        # resize was called to scale to physical aspect ratio
        mock_img.resize.assert_called()
        mock_hide.assert_called_once()



