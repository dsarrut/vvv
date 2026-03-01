import pytest
import numpy as np
import SimpleITK as sitk
import dearpygui.dearpygui as dpg
from pathlib import Path
from vvv.core import Controller
from vvv.viewer import SliceViewer


# --- FIXTURES ---

@pytest.fixture(autouse=True)
def fresh_dpg_context():
    """Create a fresh DPG context for EVERY test, and destroy it afterward."""
    dpg.create_context()
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
    """Sets up the Controller and a Viewer without launching the GUI loop."""
    controller = Controller()

    # Mock the GUI just enough so the controller doesn't crash on updates
    class MockGUI:
        def refresh_image_list_ui(self): pass

        def on_window_resize(self): pass

    controller.gui = MockGUI()

    # SETUP THE VIEWER FIRST
    # This initializes the texture registry and creates 'tex_V1'
    viewer = SliceViewer("V1", controller)

    # MOCK GUI INITIALIZATION:
    # Provide the variables that gui.py normally assigns to the viewer
    viewer.axes_nodes = [viewer.axis_a_tag, viewer.axis_b_tag]
    viewer.active_axes_idx = 0
    viewer.active_strips_node = viewer.strips_a_tag
    viewer.active_grid_node = viewer.grid_a_tag

    controller.viewers["V1"] = viewer

    # CREATE THE DUMMY UI
    # Now 'tex_V1' exists, so dpg.draw_image won't crash
    with dpg.window(tag="dummy_sidebar", show=False):
        for tag in ["info_name", "info_name_label", "info_voxel_type", "info_size",
                    "info_spacing", "info_origin", "info_matrix", "info_memory",
                    "info_window", "info_level", "info_vox", "info_phys", "info_val"]:
            dpg.add_input_text(tag=tag)

        for tag in ["check_axis", "check_crosshair", "check_overlay", "check_grid"]:
            dpg.add_checkbox(tag=tag)

    with dpg.window(tag="win_V1", width=500, height=500, show=False):
        with dpg.drawlist(tag="drawlist_V1", width=500, height=500):
            dpg.draw_image("tex_V1", [0, 0], [1, 1], tag="img_V1")

            dpg.add_draw_node(tag="crosshair_node_V1")
            dpg.add_draw_node(tag="axes_node_A_V1")
            dpg.add_draw_node(tag="axes_node_B_V1")
            dpg.add_draw_node(tag="grid_node_A_V1")
            dpg.add_draw_node(tag="grid_node_B_V1")
            dpg.add_draw_node(tag="strips_node_A_V1")
            dpg.add_draw_node(tag="strips_node_B_V1")

        dpg.add_text(tag="overlay_V1")

    # LOAD IMAGE AND ASSIGN TO VIEWER
    # Now the UI exists, so set_image can safely update the sidebar texts
    img_id = controller.load_image(synthetic_image_path)
    viewer.set_image(img_id)

    return controller, viewer, img_id


# --- TESTS ---

def test_image_loading_and_metadata(headless_app):
    """Test that the 5x5x5 image loads with the correct dimensions."""
    controller, viewer, img_id = headless_app
    img_model = controller.images[img_id]

    assert img_model.data.shape == (5, 5, 5)
    assert img_model.spacing.tolist() == [1.0, 1.0, 1.0]
    assert img_model.crosshair_voxel == [2, 2, 2]


def test_scroll_interaction_updates_crosshair(headless_app):
    """Test simulating a mouse scroll to change slices."""
    controller, viewer, img_id = headless_app
    img_model = controller.images[img_id]

    assert img_model.crosshair_value == 0.0

    viewer.set_orientation("Axial")
    viewer.on_scroll(1)

    assert viewer.slice_idx == 3
    assert img_model.crosshair_voxel == [2, 2, 3]
    assert img_model.crosshair_value == 100.0


def test_auto_window_level(headless_app):
    """Test the local auto-windowing logic."""
    controller, viewer, img_id = headless_app
    img_model = controller.images[img_id]

    viewer.update_window_level(ww=10.0, wl=500.0)

    # Increase the search radius so it covers multiple voxels
    # on our heavily zoomed-in 5x5 test image
    controller.settings.data["physics"]["search_radius"] = 250

    # Mock mouse position since there is no physical mouse
    viewer.get_mouse_slice_coords = lambda ignore_hover=False: (2.5, 2.5)

    viewer.on_key_press(dpg.mvKey_W)

    assert img_model.ww >= 95.0
    assert img_model.wl == pytest.approx(50.0, abs=5.0)
