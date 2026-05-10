import pytest
import dearpygui.dearpygui as dpg
import numpy as np
import SimpleITK as sitk
from vvv.core.controller import Controller
from vvv.ui.gui import MainGUI
from vvv.ui.viewer import SliceViewer


@pytest.fixture(scope="session")
def synthetic_volume_factory(tmp_path_factory):
    """A factory to quickly generate 3D NIfTI files on disk for testing."""

    def _create_vol(name="test_vol.nii.gz", val=100.0, shape=(5, 5, 5)):
        data = np.full(shape, val, dtype=np.float32)
        img = sitk.GetImageFromArray(data)
        img.SetSpacing((1.0, 1.0, 1.0))
        path = tmp_path_factory.mktemp("gui_data") / name
        sitk.WriteImage(img, str(path))
        return str(path)

    return _create_vol


@pytest.fixture
def headless_gui_app(tmp_path):
    """
    Creates a fully initialized headless Controller and GUI with 2 synthetic
    volumes of differing resolutions to test complex spatial math.
    """
    controller = Controller()
    controller.use_history = False  # Disable history for pure UI testing

    # ADD THIS: Build the 4 viewers before the GUI boots!
    for tag in ["V1", "V2", "V3", "V4"]:
        controller.viewers[tag] = SliceViewer(tag, controller)

    # --- Create Synthetic Volume 1 (High Res) ---
    arr1 = np.ones((20, 30, 30), dtype=np.float32) * 100.0
    img1 = sitk.GetImageFromArray(arr1)
    img1.SetSpacing((1.0, 1.0, 1.0))
    path1 = str(tmp_path / "synthetic_1.nii.gz")
    sitk.WriteImage(img1, path1)

    # --- Create Synthetic Volume 2 (Low Res, for Fusion/Sync testing) ---
    arr2 = np.ones((10, 15, 15), dtype=np.float32) * 50.0
    img2 = sitk.GetImageFromArray(arr2)
    img2.SetSpacing((2.0, 2.0, 2.0))
    path2 = str(tmp_path / "synthetic_2.nii.gz")
    sitk.WriteImage(img2, path2)

    # Load using the standard FileManager pipeline
    vs_id1 = controller.file.load_image(path1)
    vs_id2 = controller.file.load_image(path2)

    # Initialize GUI (This builds the UI nodes, viewers, and layouts)
    gui = MainGUI(controller)
    controller.gui = gui

    # Mount images to the 4 viewers
    controller.layout["V1"] = vs_id1
    controller.layout["V2"] = vs_id2
    controller.layout["V3"] = vs_id1
    controller.layout["V4"] = vs_id2

    # Force the initial boot-up ticks to settle the geometry
    controller.tick()
    controller.tick()

    # CRITICAL: Set the active context viewer!
    gui.set_context_viewer(controller.viewers["V1"])

    return controller, gui, controller.viewers["V1"], vs_id1


@pytest.fixture(scope="session", autouse=True)
def boot_dpg_engine():
    """Boots the C++ engine exactly ONCE for the entire pytest session."""
    dpg.create_context()
    dpg.create_viewport(title="Test Viewport", width=1000, height=800)
    dpg.setup_dearpygui()
    yield
    # The OS will safely reclaim all memory when the pytest process finishes


@pytest.fixture(autouse=True)
def fresh_dpg_context():
    """Soft-resets the UI state between every single test."""
    yield  # The test runs here!

    # 1. Delete ONLY actual UI Windows
    for window in dpg.get_windows():
        if dpg.does_item_exist(window):
            info = dpg.get_item_info(window)
            if info and info.get("type") == "mvWindowAppItem":
                try:
                    dpg.delete_item(window)
                except Exception:
                    pass

    # 2. Clean up ALL aliases EXCEPT textures
    for alias in list(dpg.get_aliases()):
        alias_str = str(alias)
        if dpg.does_item_exist(alias_str):
            if alias_str.startswith("tex_") or alias_str == "global_texture_registry":
                continue
            try:
                dpg.delete_item(alias_str)
            except Exception:
                pass
