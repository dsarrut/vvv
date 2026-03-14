import pytest
import numpy as np
import SimpleITK as sitk
import dearpygui.dearpygui as dpg
from pathlib import Path
from vvv.core import Controller
from vvv.viewer import SliceViewer
from vvv.utils import ViewMode, slice_to_voxel, voxel_to_slice
from vvv.gui import MainGUI

# --- FIXTURES ---


@pytest.fixture(autouse=True)
def fresh_dpg_context():
    """Create a fresh DPG context and headless viewport for EVERY test."""
    dpg.create_context()

    # The real GUI requires a viewport to exist for the menu bar and dimensions
    dpg.create_viewport(title="Test Viewport", width=1000, height=800)
    dpg.setup_dearpygui()

    yield
    dpg.destroy_context()


@pytest.fixture(scope="session")
def synthetic_image_path(tmp_path_factory):
    """Generates a 5x5x5 checkerboard image and returns its file path."""
    indices = np.indices((5, 5, 5))
    checkerboard = (indices[0] + indices[1] + indices[2]) % 2
    checkerboard = (checkerboard * 100).astype(np.float32)

    sitk_img = sitk.GetImageFromArray(checkerboard)
    sitk_img.SetSpacing((1.0, 1.0, 1.0))
    sitk_img.SetOrigin((10.0, 20.0, 50.0))

    tests_dir = Path(__file__).parent
    img_path = tests_dir / "checkerboard_5x5x5.nrrd"

    sitk.WriteImage(sitk_img, str(img_path))
    return str(img_path)


@pytest.fixture(scope="session")
def synthetic_overlay_path(tmp_path_factory):
    """
    Generates a 3x3x3 image with DIFFERENT spacing (2.0) and exactly predictable values
    to rigorously test physical resampling and geometric fusion alignment.
    """
    indices = np.indices((3, 3, 3))
    # Value is simply Z*100 + Y*10 + X. Allows exact coordinate backwards-verification!
    data = (indices[0] * 100 + indices[1] * 10 + indices[2]).astype(np.float32)

    sitk_img = sitk.GetImageFromArray(data)
    sitk_img.SetSpacing((2.0, 2.0, 2.0))
    sitk_img.SetOrigin((10.0, 20.0, 50.0))

    tests_dir = Path(__file__).parent
    img_path = tests_dir / "overlay_3x3x3.nrrd"
    sitk.WriteImage(sitk_img, str(img_path))
    return str(img_path)


@pytest.fixture
def headless_app(synthetic_image_path):
    """Sets up the real application architecture without launching the render loop."""
    controller = Controller()

    for tag in ["V1", "V2", "V3", "V4"]:
        controller.viewers[tag] = SliceViewer(tag, controller)

    gui = MainGUI(controller)
    controller.gui = gui

    vs_id = controller.load_image(synthetic_image_path)
    viewer = controller.viewers["V1"]
    viewer.set_image(vs_id)
    gui.context_viewer = viewer

    gui.on_window_resize()

    return controller, viewer, vs_id


# --- TESTS ---


def test_utils_coordinate_conversions():
    """Verify that the 2D <-> 3D math strictly obeys ITK half-voxel offsets."""
    shape = (10, 20)  # h, w -> real_h, real_w

    # AXIAL TEST
    # Center of voxel (5, 3) on screen is 5.5, 3.5. Depth is 7.
    v = slice_to_voxel(5.5, 3.5, 7.0, ViewMode.AXIAL, shape)
    assert np.allclose(v, [5.0, 3.0, 7.0])

    s_x, s_y = voxel_to_slice(5.0, 3.0, 7.0, ViewMode.AXIAL, shape)
    assert s_x == 5.5
    assert s_y == 3.5

    # SAGITTAL TEST (Flipped/Rotated axes)
    v_sag = slice_to_voxel(5.5, 3.5, 7.0, ViewMode.SAGITTAL, shape)
    assert np.allclose(v_sag, [7.0, 14.0, 6.0])

    sx_sag, sy_sag = voxel_to_slice(7.0, 14.0, 6.0, ViewMode.SAGITTAL, shape)
    assert sx_sag == 5.5
    assert sy_sag == 3.5


def test_exact_coordinate_and_value_mapping(headless_app):
    """Test that a 2D screen click correctly hits the exact 3D voxel, physical coord, and intensity."""
    controller, viewer, vs_id = headless_app
    vs = controller.view_states[vs_id]

    viewer.set_orientation(ViewMode.AXIAL)

    # 1. Simulate a click directly in the center of voxel (1, 3) on slice Z=2
    # Because pixels are drawn from 0 to W, the center of index 1 is 1.5.
    viewer.update_crosshair_data(pix_x=1.5, pix_y=3.5)

    # 2. Verify Continuous Voxel Coordinate
    assert vs.crosshair_voxel == [1.0, 3.0, 2.0, 0]

    # 3. Verify Exact Physical Coordinate
    # Origin = (10, 20, 50), Spacing = (1, 1, 1) -> [10+1, 20+3, 50+2]
    assert vs.crosshair_phys_coord.tolist() == [11.0, 23.0, 52.0]

    # 4. Verify Exact Pixel Intensity
    # Checkerboard math: (1 + 3 + 2) = 6. 6 % 2 == 0 -> 0.0
    assert vs.crosshair_value == 0.0

    # Try another voxel that should equal 100
    viewer.update_crosshair_data(pix_x=2.5, pix_y=3.5)  # Voxel (2, 3, 2)
    assert vs.crosshair_value == 100.0


def test_overlay_fusion_resampling_accuracy(headless_app, synthetic_overlay_path):
    """Test that loading a fusion overlay strictly maps onto the base image's physical grid."""
    controller, viewer, vs_id_base = headless_app
    vs_base = controller.view_states[vs_id_base]

    # Load second image to use as overlay
    vs_id_overlay = controller.load_image(synthetic_overlay_path)
    vol_overlay = controller.volumes[vs_id_overlay]

    # Set overlay (this triggers SimpleITK NearestNeighbor resampling!)
    vs_base.set_overlay(vs_id_overlay, vol_overlay)

    # 1. Check resampling dimensions
    # Base is 5x5x5. Overlay was 3x3x3. After resampling, overlay_data MUST be exactly 5x5x5.
    assert vs_base.overlay_data.shape == (5, 5, 5)

    # 2. Check strict pixel matching (using our Z*100 + Y*10 + X predictably generated values)
    # Base voxel (2, 2, 2) -> Phys (12, 22, 52).
    # In overlay's original physical space, (12, 22, 52) perfectly aligns with its voxel (1, 1, 1).
    # The overlay value at (1, 1, 1) is 1*100 + 1*10 + 1 = 111.0.
    assert vs_base.overlay_data[2, 2, 2] == 111.0

    # Base voxel (4, 4, 4) -> Phys (14, 24, 54).
    # In overlay space, this is voxel (2, 2, 2). Value = 222.0.
    assert vs_base.overlay_data[4, 4, 4] == 222.0

    # 3. Test the Tracker text engine rendering both Base and Fusion values accurately
    viewer.set_orientation(ViewMode.AXIAL)
    viewer.slice_idx = 2

    # Mock the mouse position since there is no physical mouse hovering over the headless UI
    viewer.get_mouse_slice_coords = lambda ignore_hover=False, allow_outside=False: (
        2.5,
        2.5,
    )

    viewer.update_crosshair_data(pix_x=2.5, pix_y=2.5)  # Points to base voxel (2, 2, 2)
    viewer.update_tracker()

    tracker_text = dpg.get_value(viewer.tracker_tag)
    # The first line of the tracker string should contain the base value and overlay value
    assert "0 (111)" in tracker_text


def test_sync_correspondence_between_different_geometries(
    headless_app, synthetic_overlay_path
):
    """Test that placing viewers in the same sync group properly maps physical coordinates via matrices."""
    controller, viewer1, vs_id1 = headless_app

    # Load the second image with different spacing (2.0) and size (3x3x3)
    vs_id2 = controller.load_image(synthetic_overlay_path)
    viewer2 = controller.viewers["V2"]
    viewer2.set_image(vs_id2)

    # Put both in Group 1
    controller.on_sync_group_change(None, "Group 1", vs_id1)
    controller.on_sync_group_change(None, "Group 1", vs_id2)

    viewer1.set_orientation(ViewMode.AXIAL)
    viewer2.set_orientation(ViewMode.AXIAL)

    # Click on Viewer 1 at voxel (2.0, 2.0, 2.0)
    viewer1.update_crosshair_data(pix_x=2.5, pix_y=2.5)
    controller.propagate_sync(vs_id1)

    vs1 = controller.view_states[vs_id1]
    vs2 = controller.view_states[vs_id2]

    # V1 Voxel should be [2.0, 2.0, 2.0], Phys [12.0, 22.0, 52.0]
    assert vs1.crosshair_voxel == [2.0, 2.0, 2.0, 0]
    assert vs1.crosshair_phys_coord.tolist() == [12.0, 22.0, 52.0]

    # V2 Physical coordinate MUST exactly match V1
    assert np.allclose(vs2.crosshair_phys_coord, vs1.crosshair_phys_coord)

    # V2 voxel coordinate should be dynamically calculated via ITK inverse matrix
    # Origin (10, 20, 50), Spacing (2, 2, 2) -> Phys 12 -> (12 - 10)/2 = 1.0
    assert vs2.crosshair_voxel == [1.0, 1.0, 1.0, 0.0]

    # V2 view plane depth must have automatically updated
    assert vs2.slices[ViewMode.AXIAL] == 1

    # V2 Exact intensity fetch
    assert vs2.crosshair_value == 111.0


def test_auto_window_level(headless_app):
    """Test the local auto-windowing logic."""
    controller, viewer, vs_id = headless_app
    vs = controller.view_states[vs_id]

    viewer.update_window_level(ww=10.0, wl=500.0)

    # Increase the search radius so it covers multiple voxels on our zoomed-in 5x5 test image
    controller.settings.data["physics"]["auto_window_fov"] = 0.80

    # Mock mouse position
    viewer.get_mouse_slice_coords = lambda ignore_hover=False, allow_outside=False: (
        2.5,
        2.5,
    )
    viewer.on_key_press(dpg.mvKey_W)

    assert vs.ww >= 95.0
    assert vs.wl == pytest.approx(50.0, abs=5.0)


def test_zoom_interaction(headless_app, monkeypatch):
    """Test that zooming in and out properly updates the zoom multiplier."""
    controller, viewer, vs_id = headless_app

    # Mock the mouse position to a fixed point during the zoom operation
    monkeypatch.setattr(dpg, "get_drawing_mouse_pos", lambda: (250, 250))

    initial_zoom = viewer.zoom
    viewer.on_zoom("in")
    zoomed_in = viewer.zoom
    assert zoomed_in > initial_zoom

    viewer.on_zoom("out")
    # Because 1.0 * 1.1 * 0.9 = 0.99, we assert against the actual math trajectory
    assert viewer.zoom == pytest.approx(
        zoomed_in * (1.0 / controller.settings.data["interaction"]["zoom_speed"])
    )


def test_pan_interaction_via_drag(headless_app, monkeypatch):
    """Test that panning with Ctrl+Drag updates the pan_offset."""
    controller, viewer, vs_id = headless_app
    initial_pan = viewer.pan_offset.copy()

    # Mock DPG states to simulate holding Ctrl and Left-Click
    monkeypatch.setattr(
        dpg, "is_mouse_button_down", lambda btn: btn == dpg.mvMouseButton_Left
    )
    monkeypatch.setattr(
        dpg, "is_key_down", lambda key: key in [dpg.mvKey_LControl, dpg.mvKey_RControl]
    )

    viewer.last_dx, viewer.last_dy = 100, 100
    viewer.on_drag([None, 115, 125])  # Mouse moved +15x and +25y

    assert viewer.pan_offset[0] == initial_pan[0] + 15
    assert viewer.pan_offset[1] == initial_pan[1] + 25


def test_reset_view(headless_app):
    """Test that pressing 'R' resets zoom, pan, and slice depth to defaults."""
    controller, viewer, vs_id = headless_app

    # Deliberately mess up the view state
    viewer.zoom = 5.0
    viewer.pan_offset = [100, -50]
    viewer.slice_idx = 0

    # Simulate pressing the 'R' key
    viewer.on_key_press(dpg.mvKey_R)

    # Everything should return to the center of the 5x5x5 volume
    assert viewer.zoom == 1.0
    assert viewer.pan_offset == [0, 0]
    assert viewer.slice_idx == 2
