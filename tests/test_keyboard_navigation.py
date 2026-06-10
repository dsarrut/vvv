"""
Keyboard navigation tests.

Each test calls viewer.on_key_press(key) directly — the same path the
InteractionManager uses after routing — and asserts on view_state properties.

Key bindings come from DEFAULT_SETTINGS["shortcuts"] in config.py.
"""

import pytest
import numpy as np
import SimpleITK as sitk
import dearpygui.dearpygui as dpg

from vvv.utils import ViewMode


def press(viewer, key):
    viewer.on_key_press(key)


# ---------------------------------------------------------------------------
# Slice navigation (Up/Down arrows, Page Up/Down)
# Slice navigation clamps at boundaries (does NOT wrap).
# ---------------------------------------------------------------------------


class TestSliceNavigation:
    def test_up_arrow_advances_slice(self, headless_gui_app):
        _, _, viewer, _ = headless_gui_app
        viewer.slice_idx = 5
        press(viewer, dpg.mvKey_Up)
        assert viewer.slice_idx == 6

    def test_down_arrow_retreats_slice(self, headless_gui_app):
        _, _, viewer, _ = headless_gui_app
        viewer.slice_idx = 5
        press(viewer, dpg.mvKey_Down)
        assert viewer.slice_idx == 4

    def test_page_up_jumps_by_fast_scroll_steps(self, headless_gui_app):
        controller, _, viewer, _ = headless_gui_app
        fast = controller.settings.data["interaction"]["fast_scroll_steps"]
        viewer.slice_idx = 5
        press(viewer, 517)  # Page Up (raw DPG constant from config.py)
        assert viewer.slice_idx == 5 + fast

    def test_page_down_jumps_by_fast_scroll_steps(self, headless_gui_app):
        controller, _, viewer, _ = headless_gui_app
        fast = controller.settings.data["interaction"]["fast_scroll_steps"]
        viewer.slice_idx = 15
        press(viewer, 518)  # Page Down
        assert viewer.slice_idx == 15 - fast

    def test_up_clamps_at_last_slice(self, headless_gui_app):
        _, _, viewer, _ = headless_gui_app
        last = viewer.get_display_num_slices() - 1
        viewer.slice_idx = last
        press(viewer, dpg.mvKey_Up)
        assert viewer.slice_idx == last

    def test_down_clamps_at_first_slice(self, headless_gui_app):
        _, _, viewer, _ = headless_gui_app
        viewer.slice_idx = 0
        press(viewer, dpg.mvKey_Down)
        assert viewer.slice_idx == 0


# ---------------------------------------------------------------------------
# Orientation (F1 / F2 / F3)
# The synthetic volume is (20, 30, 30) so axial and sagittal slice counts differ.
# ---------------------------------------------------------------------------


class TestOrientationKeys:
    def test_f1_sets_axial(self, headless_gui_app):
        _, _, viewer, _ = headless_gui_app
        viewer.set_orientation(ViewMode.SAGITTAL)
        press(viewer, dpg.mvKey_F1)
        assert viewer.orientation == ViewMode.AXIAL

    def test_f2_sets_sagittal(self, headless_gui_app):
        _, _, viewer, _ = headless_gui_app
        press(viewer, dpg.mvKey_F2)
        assert viewer.orientation == ViewMode.SAGITTAL

    def test_f3_sets_coronal(self, headless_gui_app):
        _, _, viewer, _ = headless_gui_app
        press(viewer, dpg.mvKey_F3)
        assert viewer.orientation == ViewMode.CORONAL

    def test_orientation_change_updates_slice_count(self, headless_gui_app):
        # Volume shape (20, 30, 30): axial=20, sagittal=30
        _, _, viewer, _ = headless_gui_app
        press(viewer, dpg.mvKey_F1)
        axial_count = viewer.get_display_num_slices()
        press(viewer, dpg.mvKey_F2)
        sagittal_count = viewer.get_display_num_slices()
        assert axial_count != sagittal_count


# ---------------------------------------------------------------------------
# Zoom (I = in, O = out, R = reset)
# ---------------------------------------------------------------------------


class TestZoomKeys:
    def test_i_increases_zoom(self, headless_gui_app):
        _, _, viewer, _ = headless_gui_app
        before = viewer.view_state.camera.zoom[viewer.orientation]
        press(viewer, dpg.mvKey_I)
        assert viewer.view_state.camera.zoom[viewer.orientation] > before

    def test_o_decreases_zoom(self, headless_gui_app):
        _, _, viewer, _ = headless_gui_app
        before = viewer.view_state.camera.zoom[viewer.orientation]
        press(viewer, dpg.mvKey_O)
        assert viewer.view_state.camera.zoom[viewer.orientation] < before

    def test_r_resets_zoom_after_zoom_in(self, headless_gui_app):
        _, _, viewer, _ = headless_gui_app
        initial = viewer.view_state.camera.zoom[viewer.orientation]
        press(viewer, dpg.mvKey_I)
        press(viewer, dpg.mvKey_I)
        assert viewer.view_state.camera.zoom[viewer.orientation] > initial
        press(viewer, dpg.mvKey_R)
        assert viewer.view_state.camera.zoom[viewer.orientation] == pytest.approx(
            initial, rel=0.01
        )


# ---------------------------------------------------------------------------
# Display toggles (H, K, L, G)
# ---------------------------------------------------------------------------


class TestDisplayToggleKeys:
    def test_h_hides_all_overlays(self, headless_gui_app):
        _, _, viewer, _ = headless_gui_app
        viewer.view_state.camera.show_crosshair = True
        press(viewer, dpg.mvKey_H)
        assert viewer.view_state.camera.show_crosshair is False
        assert viewer.view_state.camera.show_axis is False
        assert viewer.view_state.camera.show_contour is False

    def test_h_restores_overlays_on_second_press(self, headless_gui_app):
        _, _, viewer, _ = headless_gui_app
        viewer.view_state.camera.show_crosshair = False
        press(viewer, dpg.mvKey_H)
        assert viewer.view_state.camera.show_crosshair is True

    def test_k_toggles_pixelated_zoom(self, headless_gui_app):
        _, _, viewer, _ = headless_gui_app
        before = viewer.view_state.display.pixelated_zoom
        press(viewer, dpg.mvKey_K)
        assert viewer.view_state.display.pixelated_zoom != before

    def test_l_toggles_legend(self, headless_gui_app):
        _, _, viewer, _ = headless_gui_app
        before = viewer.view_state.camera.show_legend
        press(viewer, dpg.mvKey_L)
        assert viewer.view_state.camera.show_legend != before

    def test_g_toggles_grid(self, headless_gui_app):
        _, _, viewer, _ = headless_gui_app
        before = viewer.view_state.camera.show_grid
        press(viewer, dpg.mvKey_G)
        assert viewer.view_state.camera.show_grid != before


# ---------------------------------------------------------------------------
# Time navigation (Right / Left arrows) — requires a 4D volume.
# Time navigation wraps around (uses % num_timepoints), does NOT clamp.
# ---------------------------------------------------------------------------


@pytest.fixture
def headless_4d_app(tmp_path):
    from vvv.core.controller import Controller
    from vvv.ui.gui import MainGUI
    from vvv.ui.viewer import SliceViewer

    controller = Controller()
    controller.use_history = False
    for tag in ["V1", "V2", "V3", "V4"]:
        controller.viewers[tag] = SliceViewer(tag, controller)

    frames = [
        sitk.GetImageFromArray(np.full((5, 10, 10), float(t), dtype=np.float32))
        for t in range(4)
    ]
    img4d = sitk.JoinSeries(frames)
    path = str(tmp_path / "vol4d.nii.gz")
    sitk.WriteImage(img4d, path)

    vs_id = controller.file.load_image(path)
    gui = MainGUI(controller)
    controller.gui = gui
    controller.layout["V1"] = vs_id
    controller.tick()
    controller.tick()

    viewer = controller.viewers["V1"]
    gui.set_context_viewer(viewer)
    return controller, gui, viewer, vs_id


class TestTimeNavigation:
    def test_right_arrow_advances_time(self, headless_4d_app):
        _, _, viewer, _ = headless_4d_app
        viewer.view_state.camera.time_idx = 1
        press(viewer, dpg.mvKey_Right)
        assert viewer.view_state.camera.time_idx == 2

    def test_left_arrow_retreats_time(self, headless_4d_app):
        _, _, viewer, _ = headless_4d_app
        viewer.view_state.camera.time_idx = 2
        press(viewer, dpg.mvKey_Left)
        assert viewer.view_state.camera.time_idx == 1

    def test_time_wraps_forward_at_last_frame(self, headless_4d_app):
        _, _, viewer, _ = headless_4d_app
        nt = viewer.volume.num_timepoints
        viewer.view_state.camera.time_idx = nt - 1
        press(viewer, dpg.mvKey_Right)
        assert viewer.view_state.camera.time_idx == 0

    def test_time_wraps_backward_at_first_frame(self, headless_4d_app):
        _, _, viewer, _ = headless_4d_app
        nt = viewer.volume.num_timepoints
        viewer.view_state.camera.time_idx = 0
        press(viewer, dpg.mvKey_Left)
        assert viewer.view_state.camera.time_idx == nt - 1

    def test_time_arrows_are_noop_on_3d_volume(self, headless_gui_app):
        _, _, viewer, _ = headless_gui_app
        before = viewer.slice_idx
        press(viewer, dpg.mvKey_Right)
        press(viewer, dpg.mvKey_Left)
        assert viewer.slice_idx == before


class TestStuckKeysOverride:
    def test_stuck_keys_override_lifecycle(self, headless_gui_app):
        controller, gui, viewer, vs_id = headless_gui_app
        from unittest.mock import patch
        from vvv.ui.ui_interaction import _overridden_keys, clear_modifier_overrides

        _overridden_keys.clear()

        # Mock the underlying dpg.is_key_down to return True (simulating a stuck key)
        with patch("vvv.ui.ui_interaction._original_is_key_down", return_value=True):
            # Initially, without override, it should return True
            assert dpg.is_key_down(dpg.mvKey_LControl) is True

            # Clear modifier overrides
            clear_modifier_overrides()

            # Now, it should return False
            assert dpg.is_key_down(dpg.mvKey_LControl) is False

            # Simulate physical key press
            gui.interaction.on_key_press(None, dpg.mvKey_LControl, None)

            # It should return True again
            assert dpg.is_key_down(dpg.mvKey_LControl) is True

            # Simulate physical key release
            gui.interaction.on_key_release(None, dpg.mvKey_LControl, None)

            # It should return False again
            assert dpg.is_key_down(dpg.mvKey_LControl) is False


def test_on_key_press_dictionary_changed_size_safety(headless_gui_app):
    """Test that on_key_press handles concurrent modification of ui.roi_selectables safely."""
    controller, gui, viewer, vs_id = headless_gui_app
    from unittest.mock import MagicMock
    import dearpygui.dearpygui as dpg

    # Mock the roi_plugin in plugins list
    roi_plugin = MagicMock()
    roi_plugin.plugin_id = "roi_plugin"
    
    # Set up ui with roi_selectables that change size during iteration
    ui = MagicMock()
    roi_selectables = {"roi_1": "input_1", "roi_2": "input_2"}
    ui.roi_selectables = roi_selectables
    roi_plugin._ui = ui
    
    # Inject roi_plugin into gui.plugins
    gui.plugins.append(roi_plugin)
    
    # Mock dpg methods to avoid actual dearpygui crashes
    # and to trigger modification of the dictionary during lookup/iteration
    original_does_item_exist = dpg.does_item_exist
    original_is_item_focused = dpg.is_item_focused
    
    def side_effect_does_item_exist(item):
        # Concurrently modify the dictionary size when checked
        roi_selectables["roi_new"] = "input_new"
        return False

    try:
        dpg.does_item_exist = MagicMock(side_effect=side_effect_does_item_exist)
        dpg.is_item_focused = MagicMock(return_value=False)
        
        # Call on_key_press which iterates over roi_selectables.values()
        # It should run successfully without raising RuntimeError: dictionary changed size during iteration
        gui.interaction.on_key_press(None, dpg.mvKey_A, None)
    finally:
        dpg.does_item_exist = original_does_item_exist
        dpg.is_item_focused = original_is_item_focused
        
        # Cleanup injected plugin
        if roi_plugin in gui.plugins:
            gui.plugins.remove(roi_plugin)
