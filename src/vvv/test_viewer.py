import pytest
import numpy as np
import SimpleITK as sitk
import os
import dearpygui.dearpygui as dpg

from core import Controller
from viewer import SliceViewer

# --- FIXTURES ---

@pytest.fixture(scope="session")
def dpg_context():
    """Initialize DPG headless context for the test session."""
    dpg.create_context()
    yield
    dpg.destroy_context()

@pytest.fixture(scope="session")
def synthetic_image_path(tmp_path_factory):
    """Generates a 5x5x5 checkerboard image and returns its file path."""
    # Create a 5x5x5 checkerboard: values will alternate 0 and 1
    indices = np.indices((5, 5, 5))
    checkerboard = (indices[0] + indices[1] + indices[2]) % 2
    
    # Scale it so we have clear values (e.g., 0 and 100)
    checkerboard = (checkerboard * 100).astype(np.float32)
    
    sitk_img = sitk.GetImageFromArray(checkerboard)
    sitk_img.SetSpacing((1.0, 1.0, 1.0))
    sitk_img.SetOrigin((0.0, 0.0, 0.0))
    
    # Save to a temporary file
    temp_dir = tmp_path_factory.mktemp("data")
    img_path = temp_dir / "checkerboard_5x5x5.nrrd"
    sitk.WriteImage(sitk_img, str(img_path))
    
    return str(img_path)

@pytest.fixture
def headless_app(dpg_context, synthetic_image_path):
    """Sets up the Controller and a Viewer without launching the GUI loop."""
    controller = Controller()
    
    # Mock the GUI just enough so the controller doesn't crash on updates
    class MockGUI:
        def refresh_image_list_ui(self): pass
        def on_window_resize(self): pass
    controller.gui = MockGUI()

    # Load the image
    img_id = controller.load_image(synthetic_image_path)
    
    # Setup a single viewer
    viewer = SliceViewer("V1", controller)
    controller.viewers["V1"] = viewer
    
    # We must create the dummy window and drawlist that the viewer expects
    with dpg.window(tag=f"win_V1", width=500, height=500):
        with dpg.drawlist(tag=f"drawlist_V1", width=500, height=500):
            pass

    viewer.set_image(img_id)
    return controller, viewer, img_id

# --- TESTS ---

def test_image_loading_and_metadata(headless_app):
    """Test that the 5x5x5 image loads with the correct dimensions."""
    controller, viewer, img_id = headless_app
    img_model = controller.images[img_id]
    
    assert img_model.data.shape == (5, 5, 5)
    assert img_model.spacing.tolist() == [1.0, 1.0, 1.0]
    
    # Initial crosshair should be at the center (2, 2, 2)
    assert img_model.crosshair_pixel_coord == [2, 2, 2]

def test_scroll_interaction_updates_crosshair(headless_app):
    """Test simulating a mouse scroll to change slices."""
    controller, viewer, img_id = headless_app
    img_model = controller.images[img_id]
    
    # Center of a 5x5x5 grid is (2, 2, 2).
    # Since 2+2+2 = 6 (even), the value should be 0 based on our generator.
    assert img_model.crosshair_pixel_value == 0.0
    
    # Simulate scrolling up by 1 slice in Axial view
    viewer.set_orientation("Axial")
    viewer.on_scroll(1) 
    
    # The slice index should now be 3. The coordinate is (2, 2, 3).
    # Since 2+2+3 = 7 (odd), the value should be 100.
    assert viewer.slice_idx == 3
    assert img_model.crosshair_pixel_coord == [2, 2, 3]
    assert img_model.crosshair_pixel_value == 100.0

def test_auto_window_level(headless_app):
    """Test the local auto-windowing logic."""
    controller, viewer, img_id = headless_app
    img_model = controller.images[img_id]
    
    # Artificially set Window/Level to wrong values
    viewer.update_window_level(ww=10.0, wl=500.0)
    
    # We must mock get_mouse_to_pixel_coords because there is no mouse
    viewer.get_mouse_to_pixel_coords = lambda ignore_hover: (2.5, 2.5) 
    
    # Simulate pressing 'W'
    viewer.on_key_press(dpg.mvKey_W)
    
    # Our checkerboard goes from 0 to 100. The auto window should 
    # detect this range and set Window=100, Level=50.
    assert img_model.ww >= 95.0 # Allowing small variance for percentiles
    assert img_model.wl == pytest.approx(50.0, abs=5.0)
