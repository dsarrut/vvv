import pytest
import numpy as np
import SimpleITK as sitk
import dearpygui.dearpygui as dpg
from pathlib import Path
from vvv.core import Controller
from vvv.viewer import SliceViewer
from vvv.utils import ViewMode
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

    # Get the directory where this test file lives (the 'tests/' folder)
    tests_dir = Path(__file__).parent
    img_path = tests_dir / "checkerboard_5x5x5.nrrd"

    sitk.WriteImage(sitk_img, str(img_path))

    return str(img_path)


@pytest.fixture
def headless_app(synthetic_image_path):
    """Sets up the real application architecture without launching the render loop."""
    controller = Controller()

    # 1. Initialize Viewers exactly like cli.py does
    for tag in ["V1", "V2", "V3", "V4"]:
        controller.viewers[tag] = SliceViewer(tag, controller)

    # 2. Initialize the REAL GUI
    gui = MainGUI(controller)
    controller.gui = gui

    # 3. Load the image and assign it to the primary viewer
    vs_id = controller.load_image(synthetic_image_path)
    viewer = controller.viewers["V1"]
    viewer.set_image(vs_id)

    # Set it as the context viewer so UI checks don't fail
    gui.context_viewer = viewer

    # 4. Force a resize so the viewers get actual drawing dimensions instead of 0x0
    gui.on_window_resize()

    return controller, viewer, vs_id


# --- TESTS ---


def test_image_loading_and_metadata(headless_app):
    """Test that the 5x5x5 image loads with the correct dimensions."""
    controller, viewer, vs_id = headless_app
    vol = controller.volumes[vs_id]
    vs = controller.view_states[vs_id]

    assert vol.data.shape == (5, 5, 5)
    assert vol.spacing.tolist() == [1.0, 1.0, 1.0]
    assert vs.crosshair_voxel == [2, 2, 2]


def test_scroll_interaction_updates_crosshair(headless_app):
    """Test simulating a mouse scroll to change slices."""
    controller, viewer, vs_id = headless_app
    vs = controller.view_states[vs_id]

    assert vs.crosshair_value == 0.0

    viewer.set_orientation(ViewMode.AXIAL)
    viewer.on_scroll(1)

    assert viewer.slice_idx == 3
    assert vs.crosshair_voxel == [2, 2, 3]
    assert vs.crosshair_value == 100.0


def test_auto_window_level(headless_app):
    """Test the local auto-windowing logic."""
    controller, viewer, vs_id = headless_app
    vs = controller.view_states[vs_id]

    viewer.update_window_level(ww=10.0, wl=500.0)

    # Increase the search radius so it covers multiple voxels
    # on our heavily zoomed-in 5x5 test image
    controller.settings.data["physics"]["search_radius"] = 250

    # Mock mouse position since there is no physical mouse
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

    # Zoom In
    viewer.on_zoom("in")
    zoomed_in = viewer.zoom
    assert zoomed_in > initial_zoom

    # Zoom Out
    viewer.on_zoom("out")

    # Because 1.0 * 1.1 * 0.9 = 0.99, we assert against the actual math
    assert viewer.zoom == pytest.approx(zoomed_in * 0.9)


def test_single_image_sync_across_orientations(headless_app):
    """Test that clicking in one orientation updates the slice index in another."""
    controller, viewer1, vs_id = headless_app

    # Grab the V2 viewer that was already created by the headless_app fixture
    viewer2 = controller.viewers["V2"]
    viewer2.set_image(vs_id)

    viewer1.set_orientation(ViewMode.AXIAL)
    viewer2.set_orientation(ViewMode.SAGITTAL)

    # Move crosshair on V1 (Axial) to X=1.0, Y=4.0
    viewer1.update_crosshair_data(1.0, 4.0)

    # Trigger the sync propagation that the MainGUI would normally call
    controller.propagate_sync(vs_id)

    # V2 (Sagittal) views along the X-axis.
    # Its slice depth should now match the X coordinate we just clicked on V1.
    assert viewer2.slice_idx == 1


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

    # Simulate a drag event: data structure is typically [sender, current_x, current_y]
    # Viewer calculates delta as (current_x - last_dx)
    viewer.last_dx, viewer.last_dy = 100, 100
    viewer.on_drag([None, 115, 125])  # Mouse moved +15x and +25y

    assert viewer.pan_offset[0] == initial_pan[0] + 15
    assert viewer.pan_offset[1] == initial_pan[1] + 25


def test_crosshair_update_on_click(headless_app):
    """Test that calculating a 2D crosshair position correctly updates the 3D ImageModel."""
    controller, viewer, vs_id = headless_app
    vs = controller.view_states[vs_id]

    viewer.set_orientation(ViewMode.AXIAL)

    # Initial state check
    assert vs.crosshair_voxel == [2, 2, 2]

    # Simulate a click at 2D slice coordinates (1.5, 3.5)
    viewer.update_crosshair_data(1.5, 3.5)

    # The Z-axis (index 2) should remain unchanged in Axial view
    assert vs.crosshair_voxel[0] == 1.5
    assert vs.crosshair_voxel[1] == 3.5
    assert vs.crosshair_voxel[2] == 2


def test_reset_view(headless_app):
    """Test that pressing 'R' resets zoom, pan, and slice depth to defaults."""
    controller, viewer, vs_id = headless_app
    vs = controller.view_states[vs_id]

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
