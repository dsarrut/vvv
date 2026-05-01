import pytest
import threading
import numpy as np
import SimpleITK as sitk
from vvv.ui.gui import MainGUI
from vvv.utils import ViewMode
import dearpygui.dearpygui as dpg
from vvv.ui.viewer import SliceViewer
from vvv.core.controller import Controller
from vvv.ui.ui_sequences import create_boot_sequence
from vvv.ui.ui_sync import handle_sync_group_change, handle_wl_group_change


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
def headless_gui_app(synthetic_volume_factory):
    """Sets up the Controller and GUI, returning the app and a pre-loaded Base Image."""
    controller = Controller()
    controller.use_history = False  # Disable history for pure UI testing

    for tag in ["V1", "V2", "V3", "V4"]:
        controller.viewers[tag] = SliceViewer(tag, controller)

    gui = MainGUI(controller)
    controller.gui = gui

    base_path = synthetic_volume_factory("base.nii.gz", val=100.0)
    vs_id = controller.file.load_image(base_path)

    viewer = controller.viewers["V1"]
    viewer.set_image(vs_id)

    # CRITICAL: Tell the GUI which viewer we are interacting with!
    gui.set_context_viewer(viewer)

    return controller, gui, viewer, vs_id


# ==========================================
# 2. THE UI TESTS
# ==========================================


def test_gui_window_level_and_colormap(headless_gui_app):
    """Simulates a user typing into the W/L text boxes and using the colormap menu."""
    print("Running test_gui_window_level_and_colormap")
    controller, gui, viewer, vs_id = headless_gui_app
    vs = viewer.view_state

    # 1. Simulate User Typing W/L
    dpg.set_value("drag_ww", 450.5)
    dpg.set_value("drag_wl", 50.0)

    # 2. Simulate User Pressing Enter
    print("Simulating WL change")
    gui.intensities_ui.on_ww_changed(None, 450.5, None)
    gui.intensities_ui.on_wl_changed(None, 50.0, None)

    # 3. Assert Domain Math Updated
    assert vs.display.ww == 450.5
    assert vs.display.wl == 50.0

    # 4. Simulate Colormap Menu Click
    gui.intensities_ui.on_colormap_changed(None, "Hot", None)

    # 5. Assert Colormap Updated
    assert vs.display.colormap == "Hot"
    print("after assess")


def test_gui_sync_between_images(headless_gui_app, synthetic_volume_factory):
    """Simulates putting images into a Sync Group and toggling W/L Sync."""
    controller, gui, viewer1, vs1_id = headless_gui_app

    # Load two more images
    path2 = synthetic_volume_factory("img2.nii.gz", val=200.0)
    path3 = synthetic_volume_factory("img3.nii.gz", val=300.0)
    vs2_id = controller.file.load_image(path2)
    vs3_id = controller.file.load_image(path3)

    # 1. Simulate UI: Put Img1 and Img2 into "G 1", leave Img3 in "None"
    handle_sync_group_change(controller.gui, None, "G 1", vs1_id)
    handle_sync_group_change(controller.gui, None, "G 1", vs2_id)

    assert controller.view_states[vs1_id].sync_group == 1
    assert controller.view_states[vs2_id].sync_group == 1
    assert controller.view_states[vs3_id].sync_group == 0

    # 2. Simulate UI: Put Img1 and Img2 into W/L "G A"
    handle_wl_group_change(gui, None, "G A", vs1_id)
    handle_wl_group_change(gui, None, "G A", vs2_id)

    # 3. Simulate UI: Change W/L on Img1
    dpg.set_value("drag_ww", 999.0)
    dpg.set_value("drag_wl", 50.0)
    gui.intensities_ui.on_ww_changed(None, 999.0, None)
    gui.intensities_ui.on_wl_changed(None, 50.0, None)

    # 4. Assert: Img2 synced, Img3 ignored it
    assert controller.view_states[vs1_id].display.ww == 999.0
    assert controller.view_states[vs2_id].display.ww == 999.0
    assert controller.view_states[vs3_id].display.ww != 999.0


def test_gui_roi_interactions(headless_gui_app, synthetic_volume_factory):
    """Simulates changing ROI colors, opacity, and visibility from the list."""
    controller, gui, viewer, base_id = headless_gui_app
    vs = viewer.view_state

    # Load an ROI
    roi_path = synthetic_volume_factory("roi.nii.gz", val=1.0)
    roi_id = controller.roi.load_binary_mask(base_id, roi_path, name="TestROI")

    # Tell GUI which ROI is "active" in the list
    gui.active_roi_id = roi_id

    # 1. Simulate Color Change (DPG uses normalized 0.0 - 1.0 floats for colors)
    gui.roi_ui.on_roi_color_changed(
        sender=None, app_data=[1.0, 0.0, 0.0, 1.0], user_data=roi_id
    )
    assert vs.rois[roi_id].color == [255, 0, 0]

    # 2. Simulate Opacity Change Slider
    gui.roi_ui.on_roi_opacity_changed(sender=None, app_data=0.35, user_data=roi_id)
    assert vs.rois[roi_id].opacity == 0.35

    # 3. Simulate Visibility "Eye" Icon Click (Tri-State Toggle)
    assert vs.rois[roi_id].visible is True
    assert vs.rois[roi_id].is_contour is False

    # Click 1: Raster -> Contour
    gui.roi_ui.on_roi_toggle_visible(sender=None, app_data=None, user_data=roi_id)
    assert vs.rois[roi_id].visible is True
    assert vs.rois[roi_id].is_contour is True

    # Click 2: Contour -> Hidden
    gui.roi_ui.on_roi_toggle_visible(sender=None, app_data=None, user_data=roi_id)
    assert vs.rois[roi_id].visible is False
    assert vs.rois[roi_id].is_contour is False

    # Click 3: Hidden -> Raster
    gui.roi_ui.on_roi_toggle_visible(sender=None, app_data=None, user_data=roi_id)
    assert vs.rois[roi_id].visible is True
    assert vs.rois[roi_id].is_contour is False


def test_gui_fusion_controls(headless_gui_app, synthetic_volume_factory, monkeypatch):
    """Simulates selecting an overlay and adjusting fusion sliders."""
    controller, gui, viewer, base_id = headless_gui_app
    vs = viewer.view_state

    # 1. Force threads to execute synchronously so the test doesn't finish before the resampler finishes
    def fake_thread(target, *args, **kwargs):
        target()

        class DummyThread:
            def start(self):
                pass

        return DummyThread()

    monkeypatch.setattr(threading, "Thread", fake_thread)

    # 2. Load Overlay Image
    ov_path = synthetic_volume_factory("overlay.nii.gz", val=500.0)
    ov_id = controller.file.load_image(ov_path)
    opt_name, _ = controller.get_image_display_name(ov_id)

    # 3. Simulate UI: Select Overlay from Combo Box
    gui.fusion_ui.on_fusion_target_selected(
        sender=None, app_data=opt_name, user_data=None
    )
    assert vs.display.overlay_id == ov_id
    assert vs.display.overlay_data is not None

    # 4. Simulate UI: Change Opacity
    gui.fusion_ui.on_fusion_opacity_changed(sender=None, app_data=0.75, user_data=None)
    assert vs.display.overlay_opacity == 0.75

    # 5. Simulate UI: Change Mode to Checkerboard
    gui.fusion_ui.on_fusion_mode_changed(
        sender=None, app_data="Checkerboard", user_data=None
    )
    assert vs.display.overlay_mode == "Checkerboard"


def test_cli_boot_sequence_logic(headless_gui_app, synthetic_volume_factory):
    """Tests the CLI startup generator logic (loading files & syncing)."""
    controller, gui, viewer, _ = headless_gui_app

    path1 = synthetic_volume_factory("boot1.nii.gz")
    path2 = synthetic_volume_factory("boot2.nii.gz")

    # Define tasks exactly as the CLI parser would
    image_tasks = [
        {
            "base": path1,
            "base_cmap": None,
            "fusion": None,
        },
        {
            "base": path2,
            "base_cmap": "Hot",
            "fusion": None,
        },
    ]

    # Create a boot sequence with '--sync' enabled
    boot_gen = create_boot_sequence(
        gui, controller, image_tasks, sync=True, link_all=False
    )

    # Consume the generator (simulate the render loop ticking)
    list(boot_gen)

    # Assertions
    loaded_vols = list(controller.volumes.values())
    # Use 'in' instead of '==' because the name is "boot1.nii" ---
    assert any("boot1" in v.name for v in loaded_vols)
    assert any("boot2" in v.name for v in loaded_vols)

    # Find the view state for boot2 to check the colormap
    boot2_vs = next(
        vs for vs in controller.view_states.values() if "boot2" in vs.volume.name
    )
    assert boot2_vs.display.colormap == "Hot"

    # Check that '--sync' put them in the same group!
    groups = [
        vs.sync_group
        for vs in controller.view_states.values()
        if "boot" in vs.volume.name
    ]
    assert groups[0] == groups[1]
    assert groups[0] > 0


def test_gui_registration_sliders(headless_gui_app):
    """Verifies that the DearPyGui registration sliders perfectly map to the ITK math engine."""
    controller, gui, viewer, vs_id = headless_gui_app
    vs = viewer.view_state

    # 1. Initialize the GUI slider items if they don't exist in the headless context
    for key in [
        "drag_reg_tx",
        "drag_reg_ty",
        "drag_reg_tz",
        "drag_reg_rx",
        "drag_reg_ry",
        "drag_reg_rz",
    ]:
        if not dpg.does_item_exist(key):
            dpg.add_drag_float(tag=key, default_value=0.0)

    # 2. Simulate User dragging the X-Translation slider to 15.0 mm
    dpg.set_value("drag_reg_tx", 15.0)

    # 3. Trigger the GUI update method
    vs.space.is_active = True  # Transform must be active to read it
    gui.reg_ui.apply_transform_and_keep_world_fixed(viewer)

    # 4. Assert the underlying SimpleITK Transform actually received the 15.0mm translation!
    translation = vs.space.transform.GetTranslation()
    assert translation[0] == 15.0
    assert translation[1] == 0.0


def test_gui_interaction_modifiers(headless_gui_app, monkeypatch):
    """Verifies that holding the Ctrl key changes the mouse scroll from Slicing to Zooming."""
    controller, gui, viewer, vs_id = headless_gui_app
    vs = viewer.view_state

    initial_zoom = vs.camera.zoom[viewer.orientation]
    initial_slice = vs.camera.slices[viewer.orientation]

    # 1. Mock the Ctrl key being pressed globally
    monkeypatch.setattr(
        dpg, "is_key_down", lambda key: key in [dpg.mvKey_LControl, dpg.mvKey_RControl]
    )

    # Mock mouse position so the zoom focal point math doesn't crash
    monkeypatch.setattr(dpg, "get_drawing_mouse_pos", lambda: [250, 250])

    # Mock the hovered viewer because the headless UI has no real mouse
    monkeypatch.setattr(gui.interaction, "get_hovered_viewer", lambda: viewer)

    # 2. Simulate User scrolling the mouse wheel (delta = 1)
    gui.interaction.on_mouse_scroll(sender=None, app_data=1.0, user_data=None)

    # 3. Assert Zoom increased, but the Slice Index stayed exactly the same!
    assert vs.camera.zoom[viewer.orientation] > initial_zoom
    assert vs.camera.slices[viewer.orientation] == initial_slice


def test_gui_sidebar_text_outputs(headless_gui_app):
    """Verifies that the GUI successfully formats and renders text back to the user."""
    controller, gui, viewer, vs_id = headless_gui_app

    # 1. Create the UI text nodes if they don't exist in the headless context
    if not dpg.does_item_exist("dummy_window"):
        with dpg.window(tag="dummy_window"):
            if not dpg.does_item_exist("info_phys_coord"):
                dpg.add_text("", tag="info_phys_coord")
            if not dpg.does_item_exist("info_value"):
                dpg.add_text("", tag="info_value")

    # 2. Simulate clicking in the middle of the image (Voxel 2,2,2)
    viewer.set_orientation(ViewMode.AXIAL)
    viewer.update_crosshair_data(pix_x=2.5, pix_y=2.5)

    # 3. Force the GUI to update its text nodes based on the crosshair
    gui.update_sidebar_crosshair(viewer)
    gui.update_sidebar_info(viewer)

    # 4. Read the actual UI strings displayed to the user!
    coord_text = dpg.get_value("info_phys")
    val_text = dpg.get_value("info_val")

    # The synthetic volume has 1.0 spacing and 0,0,0 origin.
    # Voxel 2,2,2 is exactly physical coordinate 2.0, 2.0, 2.0
    assert "2 2 2" in coord_text
    # The synthetic volume is filled with 100.0 values
    assert "100" in val_text


def test_gui_roi_filtering_and_bulk_actions(headless_gui_app, synthetic_volume_factory):
    """Verifies that bulk ROI actions (Hide All) safely ignore filtered-out ROIs."""
    controller, gui, viewer, base_id = headless_gui_app
    vs = viewer.view_state

    # 1. Load 3 ROIs with distinct names
    roi1 = controller.roi.load_binary_mask(base_id, synthetic_volume_factory("apple.nii.gz", val=1.0), name="Apple")
    roi2 = controller.roi.load_binary_mask(base_id, synthetic_volume_factory("banana.nii.gz", val=1.0), name="Banana")
    roi3 = controller.roi.load_binary_mask(base_id, synthetic_volume_factory("apricot.nii.gz", val=1.0), name="Apricot")

    # All should be visible by default
    assert all(vs.rois[r].visible for r in [roi1, roi2, roi3])

    # 2. Simulate User typing "ap" into the filter box (matches Apple and Apricot)
    gui.roi_ui.on_roi_filter_changed(None, "ap", None)

    # 3. Simulate User clicking "Hide All"
    gui.roi_ui.on_roi_hide_all(None, None, None)

    # 4. Assert that ONLY the filtered items were acted upon!
    assert vs.rois[roi1].visible is False  # Apple hidden
    assert vs.rois[roi3].visible is False  # Apricot hidden
    assert vs.rois[roi2].visible is True   # Banana was hidden by filter, so it was protected!
