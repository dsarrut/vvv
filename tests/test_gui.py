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
    intensity_plugin = next(p for p in gui.plugins if p.plugin_id == "intensity_plugin")

    # 1. Simulate User Typing W/L
    dpg.set_value(intensity_plugin._controller._t("drag_ww"), 450.5)
    dpg.set_value(intensity_plugin._controller._t("drag_wl"), 50.0)

    # 2. Simulate User Pressing Enter
    print("Simulating WL change")
    intensity_plugin._controller.on_ww_changed(None, 450.5, None)
    intensity_plugin._controller.on_wl_changed(None, 50.0, None)

    # 3. Assert Domain Math Updated
    assert vs.display.ww == 450.5
    assert vs.display.wl == 50.0

    # 4. Simulate Colormap Menu Click
    intensity_plugin._controller.on_colormap_changed(None, "Hot", None)

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
    sp_items = ["None", "G 1", "G 2"]
    handle_sync_group_change(controller.gui, None, "G 1", (vs1_id, sp_items))
    handle_sync_group_change(controller.gui, None, "G 1", (vs2_id, sp_items))

    assert controller.view_states[vs1_id].sync_group == 1
    assert controller.view_states[vs2_id].sync_group == 1
    assert controller.view_states[vs3_id].sync_group == 0

    # 2. Simulate UI: Put Img1 and Img2 into W/L "G A"
    wl_items = ["None", "G A", "G B"]
    handle_wl_group_change(gui, None, "G A", (vs1_id, wl_items))
    handle_wl_group_change(gui, None, "G A", (vs2_id, wl_items))

    # 3. Simulate UI: Change W/L on Img1
    intensity_plugin = next(p for p in gui.plugins if p.plugin_id == "intensity_plugin")
    dpg.set_value(intensity_plugin._controller._t("drag_ww"), 999.0)
    dpg.set_value(intensity_plugin._controller._t("drag_wl"), 50.0)
    intensity_plugin._controller.on_ww_changed(None, 999.0, None)
    intensity_plugin._controller.on_wl_changed(None, 50.0, None)

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

    # Get ROI plugin
    roi_plugin = next((p for p in gui.plugins if p.plugin_id == "roi_plugin"), None)
    assert roi_plugin is not None
    roi_ui = roi_plugin._ui
    roi_ctrl = roi_plugin._controller

    # Tell GUI/Plugin which ROI is "active" in the list
    roi_ctrl.active_roi_id = roi_id

    # 1. Simulate Color Change (DPG uses normalized 0.0 - 1.0 floats for colors)
    roi_ui.on_roi_color_changed(
        sender=None, app_data=[1.0, 0.0, 0.0, 1.0], user_data=roi_id
    )
    assert vs.rois[roi_id].color == [255, 0, 0]

    # 2. Simulate Opacity Change Slider
    roi_ui.on_roi_opacity_changed(sender=None, app_data=0.35, user_data=roi_id)
    assert vs.rois[roi_id].opacity == 0.35

    # 3. Simulate Visibility "Eye" Icon Click (Tri-State Toggle)
    assert vs.rois[roi_id].visible is True
    assert vs.rois[roi_id].is_contour is False

    # Click 1: Raster -> Contour
    roi_ui.on_roi_toggle_visible(sender=None, app_data=None, user_data=roi_id)
    assert vs.rois[roi_id].visible is True
    assert vs.rois[roi_id].is_contour is True

    # Click 2: Contour -> Hidden
    roi_ui.on_roi_toggle_visible(sender=None, app_data=None, user_data=roi_id)
    assert vs.rois[roi_id].visible is False
    assert vs.rois[roi_id].is_contour is False

    # Click 3: Hidden -> Raster
    roi_ui.on_roi_toggle_visible(sender=None, app_data=None, user_data=roi_id)
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
    assert vs.display.overlay.image_id == ov_id
    assert vs.display.overlay_data is not None

    # 4. Simulate UI: Change Opacity
    gui.fusion_ui.on_fusion_opacity_changed(sender=None, app_data=0.75, user_data=None)
    assert vs.display.overlay.opacity == 0.75

    # 5. Simulate UI: Change Mode to Checkerboard
    gui.fusion_ui.on_fusion_mode_changed(
        sender=None, app_data="Checkerboard", user_data=None
    )
    assert vs.display.overlay.mode == "Checkerboard"


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

def test_gui_interaction_modifiers(headless_gui_app, monkeypatch):
    """Verifies that holding the Ctrl key changes the mouse scroll from Slicing to Zooming."""
    import sys
    monkeypatch.setattr(sys, "platform", "linux")
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

    # Ensure modifiers are updated based on the mock
    gui.interaction.update_trackers()

    # 2. Simulate User scrolling the mouse wheel (delta = 1)
    gui.interaction.on_mouse_scroll(sender=None, app_data=1.0, user_data=None)

    # 3. Assert Zoom increased, but the Slice Index stayed exactly the same!
    assert vs.camera.zoom[viewer.orientation] > initial_zoom
    assert vs.camera.slices[viewer.orientation] == initial_slice


def test_zoom_to_cursor_no_drift(headless_gui_app, monkeypatch):
    """
    Regression test: rapid zoom-in then zoom-out (key-repeat, no render between)
    must not drift the pan anchor away from the mouse position.

    Root cause: get_center_physical_coord() called inside on_zoom() has a side effect —
    it calls mapper.update(win_w, win_h) but the render uses canvas_w = win_w - pad.
    Without the fix, the second zoom event uses a corrupted mapper.pmin, shifting the
    pan by ~0.3-0.5 px per in+out pair.
    """
    controller, gui, viewer, vs_id = headless_gui_app

    # Wire image through the layout path so view_state/volume are initialised
    controller.layout["V1"] = vs_id
    controller.tick()
    viewer = controller.viewers["V1"]
    gui.set_context_viewer(viewer)

    assert viewer.volume is not None, "fixture did not load a volume"
    assert viewer.is_image_orientation(), "viewer is not in image orientation"

    # Manually prime the mapper to a valid canvas state.
    # _get_window_dims() returns (0,0) in headless tests so tick() never calls
    # mapper.update(); we replicate what the render path would do.
    viewer.quad_w, viewer.quad_h = 500, 500
    canvas_w, canvas_h = viewer._get_canvas_size()
    sw, sh = viewer.volume.get_physical_aspect_ratio(viewer.orientation)
    shape = viewer.get_slice_shape()
    viewer.mapper.update(canvas_w, canvas_h, shape[1], shape[0], sw, sh, viewer.zoom, viewer.pan_offset)

    # Put the mouse at a clearly off-center position to maximise drift from any pmin error
    monkeypatch.setattr(dpg, "get_drawing_mouse_pos", lambda: [120.0, 180.0])

    initial_pan = list(viewer.pan_offset)
    initial_zoom = viewer.zoom

    # Simulate key-repeat: zoom-in then zoom-out with no render between them
    viewer.on_zoom("in")
    viewer.on_zoom("out")

    # Pan must return to its starting value (within floating-point tolerance)
    assert abs(viewer.pan_offset[0] - initial_pan[0]) < 0.01, (
        f"pan_offset[0] drifted: {initial_pan[0]:.4f} → {viewer.pan_offset[0]:.4f}"
    )
    assert abs(viewer.pan_offset[1] - initial_pan[1]) < 0.01, (
        f"pan_offset[1] drifted: {initial_pan[1]:.4f} → {viewer.pan_offset[1]:.4f}"
    )

    # Zoom must also return to its starting value
    assert abs(viewer.zoom - initial_zoom) < 1e-9, (
        f"zoom drifted: {initial_zoom} → {viewer.zoom}"
    )

    # Mapper must be in canvas state (not win state) after on_zoom
    canvas_w, canvas_h = viewer._get_canvas_size()
    assert canvas_w > 0
    sw, sh = viewer.volume.get_physical_aspect_ratio(viewer.orientation)
    shape = viewer.get_slice_shape()
    from vvv.ui.viewer import ViewportMapper
    expected = ViewportMapper()
    expected.update(canvas_w, canvas_h, shape[1], shape[0], sw, sh, viewer.zoom, viewer.pan_offset)
    assert abs(viewer.mapper.pmin[0] - expected.pmin[0]) < 0.01, (
        f"mapper not in canvas state after on_zoom: "
        f"got pmin[0]={viewer.mapper.pmin[0]:.4f}, expected {expected.pmin[0]:.4f}"
    )


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

    # Get ROI plugin
    roi_plugin = next((p for p in gui.plugins if p.plugin_id == "roi_plugin"), None)
    assert roi_plugin is not None
    roi_ui = roi_plugin._ui

    # 2. Simulate User typing "ap" into the filter box (matches Apple and Apricot)
    roi_ui.on_roi_filter_changed(None, "ap", None)

    # 3. Simulate User clicking "Hide All"
    roi_ui.on_roi_hide_all(None, None, None)

    # 4. Assert that ONLY the filtered items were acted upon!
    assert vs.rois[roi1].visible is False  # Apple hidden
    assert vs.rois[roi3].visible is False  # Apricot hidden
    assert vs.rois[roi2].visible is True   # Banana was hidden by filter, so it was protected!


def test_gui_dicom_not_in_sidebar(headless_gui_app):
    """Verifies that the DICOM Browser plugin is not listed in vertical navigation by default."""
    controller, gui, _, _ = headless_gui_app

    # Ensure context exists
    if not dpg.is_dearpygui_running():
        dpg.create_context()

    # Rebuild nav panel and assert dicom_plugin is NOT in nav items
    gui.build_vertical_nav()
    nav_tags = [tag for _, tag in gui.nav_items]
    assert "dicom_plugin" not in nav_tags


def test_synced_viewers_same_image_zoom_stable(headless_gui_app, monkeypatch):
    """
    Regression test: verify that having two synced viewers displaying the same image
    does not trigger a zoom feedback loop during dragging/panning.
    """
    controller, gui, viewer1, vs_id = headless_gui_app

    # 1. Setup layout: both V1 and V4 show the same image
    controller.layout["V1"] = vs_id
    controller.layout["V4"] = vs_id

    controller.tick()

    viewer1 = controller.viewers["V1"]
    viewer2 = controller.viewers["V4"]

    # 2. Both viewers display AXIAL orientation
    viewer1.orientation = ViewMode.AXIAL
    viewer2.orientation = ViewMode.AXIAL

    # 3. Put both viewers in the same sync group (their viewstate shares this)
    vs = viewer1.view_state
    assert vs == viewer2.view_state
    vs.sync_group = 1

    # 4. Give them different canvas sizes (forces different base_scale)
    viewer1.quad_w, viewer1.quad_h = 400, 400
    viewer2.quad_w, viewer2.quad_h = 500, 500

    # Manually update their mappers to establish valid pmin/pmax bounds and base_scale
    for v in [viewer1, viewer2]:
        canvas_w, canvas_h = v._get_canvas_size()
        sw, sh = v.volume.get_physical_aspect_ratio(v.orientation)
        shape = v.get_slice_shape()
        v.mapper.update(canvas_w, canvas_h, shape[1], shape[0], sw, sh, v.zoom, v.pan_offset)
        v.last_consumed_ppm = v.get_pixels_per_mm()
        cent = v.get_center_physical_coord()
        if cent is not None:
            v.last_consumed_center = list(cent)

    # Mock mouse pos and click state for drag simulation
    mouse_pos = [100.0, 100.0]
    monkeypatch.setattr(dpg, "get_mouse_pos", lambda local=False: mouse_pos)
    monkeypatch.setattr(
        dpg, "is_mouse_button_down", lambda button: button == dpg.mvMouseButton_Left
    )
    gui.interaction.modifiers["ctrl"] = True

    # Start panning drag on viewer1
    viewer1.on_mouse_down()

    # Change mouse pos to simulate a drag of 50, 50 px
    mouse_pos[0] += 50.0
    mouse_pos[1] += 50.0

    initial_zoom = viewer1.zoom

    # Trigger drag
    viewer1.on_drag(None)

    # Run the camera sync application on both viewers directly.
    # viewer1 is the source, and viewer2 is the target.
    # With decoupled zoom/pan keys, viewer2 should be able to update its local zoom/pan
    # to stay physically synced with viewer1 without modifying viewer1's zoom/pan.
    viewer1._apply_camera_sync(vs)
    viewer2._apply_camera_sync(vs)

    # 1. Assert that the drag source's zoom did not change (no feedback loop)
    assert abs(viewer1.zoom - initial_zoom) < 1e-9, (
        f"zoom feedback loop occurred: zoom shifted from {initial_zoom} to {viewer1.zoom}"
    )

    # 2. Assert that the synced target's zoom successfully updated to stay physically synced
    # Calculate base scale dynamically to avoid padding/margin constant differences
    def calc_base_scale(v):
        canvas_w, canvas_h = v._get_canvas_size()
        sw, sh = v.volume.get_physical_aspect_ratio(v.orientation)
        shape = v.get_slice_shape()
        real_w, real_h = shape[1], shape[0]
        mm_w, mm_h = real_w * sw, real_h * sh
        target_w = canvas_w - v.mapper.margin_left * 2.0
        target_h = canvas_h - v.mapper.margin_top * 2.0
        return min(target_w / mm_w, target_h / mm_h)

    base_scale_1 = calc_base_scale(viewer1)
    base_scale_2 = calc_base_scale(viewer2)
    expected_viewer2_zoom = initial_zoom * (base_scale_1 / base_scale_2)

    assert abs(viewer2.zoom - expected_viewer2_zoom) < 1e-5, (
        f"viewer2 failed to sync physical scale: got {viewer2.zoom:.4f}, expected {expected_viewer2_zoom:.4f}"
    )


def test_gui_roi_plugin_hides_active_viewer(headless_gui_app):
    """Verifies that selecting the ROI plugin tab hides the Active Viewer panel."""
    controller, gui, _, _ = headless_gui_app

    # Ensure context exists
    if not dpg.is_dearpygui_running():
        dpg.create_context()

    # Create UI panels so av_panel exists
    if not dpg.does_item_exist("av_panel"):
        with dpg.window(tag="PrimaryWindow"):
            dpg.add_child_window(tag="av_panel")

    # Initial state (on Images tab) -> Active Viewer is shown
    gui.on_nav_clicked(None, None, "tab_images")
    assert gui._hide_av_panel is False
    assert dpg.is_item_shown("av_panel")

    # Select ROI Plugin -> Active Viewer is hidden
    gui.on_nav_clicked(None, None, "roi_plugin")
    assert gui._hide_av_panel is True
    assert dpg.is_item_shown("av_panel") is False

    # Switch back to Images -> Active Viewer is shown again
    gui.on_nav_clicked(None, None, "tab_images")
    assert gui._hide_av_panel is False
    assert dpg.is_item_shown("av_panel")

    dpg.delete_item("PrimaryWindow")


def test_gui_roi_plugin_resizes_list_window(headless_gui_app):
    """Verifies that the ROI plugin list window is correctly resized on window resize."""
    from unittest.mock import patch
    controller, gui, _, _ = headless_gui_app

    if not dpg.is_dearpygui_running():
        dpg.create_context()

    window_tag = "PrimaryWindow_test_resize"
    created_window = False
    created_items = []

    if not dpg.does_item_exist(window_tag):
        dpg.add_window(tag=window_tag)
        created_window = True

    for tag in ["top_panel", "roi_plugin_roi_list_window", "roi_plugin_roi_detail_window"]:
        if not dpg.does_item_exist(tag):
            dpg.add_child_window(tag=tag, parent=window_tag)
            created_items.append(tag)

    if not dpg.does_item_exist("roi_plugin_roi_detail_header_group"):
        dpg.add_group(tag="roi_plugin_roi_detail_header_group", parent=window_tag)
        created_items.append("roi_plugin_roi_detail_header_group")

    # Mock viewport dimensions
    with patch('dearpygui.dearpygui.get_viewport_client_width', return_value=1000), \
         patch('dearpygui.dearpygui.get_viewport_client_height', return_value=800):
        # Configure layout variables
        gui.ui_cfg["layout"]["nav_panel_w"] = 100
        gui.ui_cfg["layout"]["left_inner_m"] = 5
        gui.ui_cfg["layout"]["right_inner_m"] = 5
        gui.ui_cfg["layout"]["sidebar_gap"] = 5
        gui.ui_cfg["layout"]["panel_ch_h"] = 100
        gui.ui_cfg["layout"]["panel_av_h"] = 100
        gui.ui_cfg["layout"]["roi_detail_h"] = 300

        # Set ROI plugin active
        gui._hide_av_panel = True

        # Resize with detail panel hidden
        dpg.configure_item("roi_plugin_roi_detail_header_group", show=False)
        gui.on_window_resize()

        h_hidden = dpg.get_item_height("roi_plugin_roi_list_window")

        # Resize with detail panel shown
        dpg.configure_item("roi_plugin_roi_detail_header_group", show=True)
        gui.on_window_resize()

        h_shown = dpg.get_item_height("roi_plugin_roi_list_window")

        # The list window height when detail is hidden should be larger than when detail is shown
        assert h_hidden > h_shown

    # Clean up created items
    for tag in reversed(created_items):
        if dpg.does_item_exist(tag):
            dpg.delete_item(tag)
    if created_window and dpg.does_item_exist(window_tag):
        dpg.delete_item(window_tag)


def test_gui_profiles_checkbox_sync(headless_gui_app):
    """Verifies that the main Profiles checkbox and the Profile plugin checkbox toggle each other."""
    controller, gui, viewer, vs_id = headless_gui_app
    vs = viewer.view_state

    # 1. Retrieve the profile plugin
    profile_plugin = next(p for p in gui.plugins if p.plugin_id == "profile_plugin")
    plugin_chk_tag = profile_plugin._ui._t("check_show_profiles")

    # Ensure items exist
    assert dpg.does_item_exist("check_profiles")
    assert dpg.does_item_exist(plugin_chk_tag)

    # Initially they should both be True (the default)
    assert vs.camera.show_profiles is True
    assert dpg.get_value("check_profiles") is True
    assert dpg.get_value(plugin_chk_tag) is True

    # 2. Simulate User untoggling the main check_profiles checkbox
    gui.on_visibility_toggle(sender="check_profiles", value=False, user_data="profiles")

    # Assert model updated
    assert vs.camera.show_profiles is False

    # Simulate the GUI update loop (plugin updates run if ui_needs_refresh is True)
    assert controller.ui_needs_refresh is True
    if gui.plugin_api.is_dirty:
        for plugin in gui.plugins:
            if plugin.plugin_id == "profile_plugin":
                plugin.update(gui.plugin_api)

    # Now verify the plugin checkbox has updated to False
    assert dpg.get_value(plugin_chk_tag) is False

    # Clear ui_needs_refresh
    controller.ui_needs_refresh = False

    # 3. Simulate User toggling the plugin checkbox back to True
    profile_plugin._ui.on_show_profiles_changed(sender=plugin_chk_tag, app_data=True, user_data=None)

    # Assert model updated
    assert vs.camera.show_profiles is True

    # Check that main check_profiles checkbox has updated to True
    assert dpg.get_value("check_profiles") is True
    assert controller.ui_needs_refresh is True



