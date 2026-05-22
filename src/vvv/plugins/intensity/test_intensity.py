import unittest
from unittest.mock import MagicMock, patch
import numpy as np
import dearpygui.dearpygui as dpg
from vvv.plugins.intensity.plugin_intensity import IntensityPlugin
from vvv.plugins.intensity.control_intensity import IntensityController, HistogramState


class TestIntensityPlugin(unittest.TestCase):
    def setUp(self):
        if not dpg.does_item_exist("global_texture_registry"):
            dpg.add_texture_registry(tag="global_texture_registry")

        self.plugin = IntensityPlugin()
        self.mock_api = MagicMock()
        self.mock_api.is_beginner_mode = False
        self.mock_api.beginner_tags = []

        self.mock_viewer = MagicMock()
        self.mock_viewer.image_id = "test_img_id"
        self.mock_viewer.volume.is_rgb = False
        self.mock_viewer.volume.data = np.array([1, 2, 3])
        self.mock_viewer.volume.num_components = 1

        self.mock_viewer.view_state.display.ww = 100.0
        self.mock_viewer.view_state.display.wl = 50.0
        self.mock_viewer.view_state.display.colormap = "Grayscale"
        self.mock_viewer.view_state.display.base_threshold = None

        self.mock_api.get_active_viewer.return_value = self.mock_viewer
        self.mock_api.get_active_image_name.return_value = "image.nii"
        self.mock_api.get_image_display_name.return_value = ("image.nii", False)
        self.mock_api.get_ui_config.return_value = {
            "colors": {
                "text_header": [255, 255, 255],
                "text_active": [255, 255, 255],
                "text_dim": [150, 150, 150],
                "outdated": [255, 100, 100],
            }
        }

        # Wire histogram state for the mock image (mirrors on_image_loaded)
        c = self.plugin._controller
        c.bind(self.mock_api)
        c.on_image_loaded("test_img_id")

        hs = self._hs()
        hs.data_x = np.array([0.0, 10.0, 20.0], dtype=np.float32)
        hs.data_y = np.array([5.0, 10.0, 15.0], dtype=np.float32)
        hs.is_dirty = False

    def _hs(self):
        """Shortcut to the HistogramState for the mock image."""
        return self.plugin._controller._hist["test_img_id"]

    def test_plugin_metadata(self):
        self.assertEqual(self.plugin.plugin_id, "intensity_plugin")
        self.assertEqual(self.plugin.label, "Intensity")
        self.assertIsNotNone(self.plugin.description)

    def test_create_ui(self):
        with dpg.window(tag="test_intensity_win"):
            self.plugin.create_ui(parent="test_intensity_win", api=self.mock_api)
        self.assertTrue(dpg.does_item_exist(self.plugin.plugin_id))

    def test_update_lifecycle(self):
        with dpg.window(tag="test_update_win"):
            self.plugin.create_ui(parent="test_update_win", api=self.mock_api)
        self.plugin.update(self.mock_api)

        active_title = self.plugin._controller._t("active_title")
        self.assertEqual(dpg.get_value(active_title), "image.nii")

    def test_popup_ui(self):
        with dpg.window(tag="test_popup_win"):
            self.plugin.create_ui(parent="test_popup_win", api=self.mock_api)

        self.plugin._controller.on_hist_popup(None, None, None)
        popup_tag = f"{self.plugin.plugin_id}_wl_hist_popup_win"
        self.assertTrue(dpg.does_item_exist(popup_tag))

    def test_preset_changed(self):
        c = self.plugin._controller
        c.on_preset_changed(None, "CT: Bone", None)

        self.mock_viewer.view_state.apply_wl_preset.assert_called_with("CT: Bone")
        self.mock_api.propagate_window_level.assert_called_with("test_img_id")
        self.mock_api.request_refresh.assert_called()

    def test_ww_wl_changed(self):
        c = self.plugin._controller

        c.on_ww_changed(None, 120.0, None)
        self.assertEqual(self.mock_viewer.view_state.display.ww, 120.0)

        c.on_wl_changed(None, 60.0, None)
        self.assertEqual(self.mock_viewer.view_state.display.wl, 60.0)

        self.mock_api.propagate_window_level.assert_called_with("test_img_id")

    def test_colormap_changed(self):
        c = self.plugin._controller
        c.on_colormap_changed(None, "Hot", None)

        self.assertEqual(self.mock_viewer.view_state.display.colormap, "Hot")
        self.mock_api.propagate_colormap.assert_called_with("test_img_id")

    def test_threshold_callbacks(self):
        c = self.plugin._controller

        c.on_threshold_changed(None, 15.0, None)
        self.assertEqual(self.mock_viewer.view_state.display.base_threshold, 15.0)

        c.on_threshold_toggle(None, False, None)
        self.assertIsNone(self.mock_viewer.view_state.display.base_threshold)

    def test_hist_log_bar_center_toggles(self):
        c = self.plugin._controller
        hs = self._hs()

        # Center — sets x_center/x_range from current wl/ww
        c.on_hist_center(None, None, None)
        self.assertEqual(hs.x_center, 50.0)
        self.assertAlmostEqual(hs.x_range, 100.0 / 0.3)

        # Log toggle — flips use_log, resets y_max
        self.assertTrue(hs.use_log)  # default is True
        c.on_hist_log_toggle(None, None, None)
        self.assertFalse(hs.use_log)
        self.assertIsNone(hs.y_max)

        # Bar toggle — flips use_bars
        self.assertTrue(hs.use_bars)  # default is True
        c.on_hist_bar_toggle(None, None, None)
        self.assertFalse(hs.use_bars)

    @patch("dearpygui.dearpygui.is_item_shown", return_value=True)
    def test_computing_full_hist_visibility(self, mock_shown):
        c = self.plugin._controller

        with dpg.window(tag="test_visibility_win"):
            self.plugin.create_ui(parent="test_visibility_win", api=self.mock_api)
        c.on_hist_popup(None, None, None)

        txt_panel = c._t("txt_computing_full_hist")
        txt_popup = c._t("txt_popup_computing_full_hist")

        hs = self._hs()
        hs.is_dirty = False
        hs._vol_data_id = id(self.mock_viewer.volume.data)

        hs.computing_full_hist = True
        c._refresh_wl_histogram(self.mock_viewer, has_image=True, is_rgb=False)
        self.assertTrue(dpg.get_item_configuration(txt_panel)["show"])
        self.assertTrue(dpg.get_item_configuration(txt_popup)["show"])

        hs.computing_full_hist = False
        c._refresh_wl_histogram(self.mock_viewer, has_image=True, is_rgb=False)
        self.assertFalse(dpg.get_item_configuration(txt_panel)["show"])
        self.assertFalse(dpg.get_item_configuration(txt_popup)["show"])

    def test_step_buttons(self):
        c = self.plugin._controller

        with dpg.window(tag="test_step_win"):
            tag = c._t("drag_ww")
            dpg.add_drag_float(tag=tag, default_value=100.0)

        c.on_step_button_clicked(None, None, {"tag": tag, "dir": 1})
        # ww step is ww * 0.02 = 2.0. So 100 + 2.0 = 102.0
        self.assertEqual(self.mock_viewer.view_state.display.ww, 102.0)

    def test_drag_lower_upper_level_callbacks(self):
        c = self.plugin._controller

        with dpg.window(tag="test_drag_win"):
            self.plugin.create_ui(parent="test_drag_win", api=self.mock_api)

        # wl=50, lower→10: ww = 2*|50-10| = 80
        c.on_hist_drag_lower(None, 10.0, None)
        self.assertEqual(self.mock_viewer.view_state.display.ww, 80.0)
        self.assertEqual(self.mock_viewer.view_state.display.wl, 50.0)

        # wl=50, upper→110: ww = 2*|50-110| = 120
        c.on_hist_drag_upper(None, 110.0, None)
        self.assertEqual(self.mock_viewer.view_state.display.ww, 120.0)
        self.assertEqual(self.mock_viewer.view_state.display.wl, 50.0)

        # level→60, ww stays 120
        c.on_hist_drag_level(None, 60.0, None)
        self.assertEqual(self.mock_viewer.view_state.display.wl, 60.0)
        self.assertEqual(self.mock_viewer.view_state.display.ww, 120.0)

        # lower→70 > wl=60: ww = 2*|60-70| = 20
        c.on_hist_drag_lower(None, 70.0, None)
        self.assertEqual(self.mock_viewer.view_state.display.ww, 20.0)

    def test_colorscale_texture_generation(self):
        c = self.plugin._controller
        hs = self._hs()

        with dpg.window(tag="test_colorscale_win"):
            self.plugin.create_ui(parent="test_colorscale_win", api=self.mock_api)

        c.on_hist_popup(None, None, None)

        self.mock_viewer.view_state.display.wl = 50.0
        self.mock_viewer.view_state.display.ww = 100.0
        hs.x_center = 50.0
        hs.x_range = 200.0

        c._update_colorscale_texture(self.mock_viewer.view_state, hs)
        tex_tag = c._t("wl_colorscale_tex")
        self.assertTrue(dpg.does_item_exist(tex_tag))

        pixels = dpg.get_value(tex_tag)
        self.assertIsNotNone(pixels)
        self.assertEqual(len(pixels), 256 * 4)

    def test_compute_colorscale_gradient(self):
        from vvv.maths.image_utils import compute_colorscale_gradient

        pixels = compute_colorscale_gradient(
            wl=50.0, ww=100.0, cmap_name="Grayscale", img_min=-50.0, img_max=150.0
        )
        self.assertEqual(len(pixels), 256 * 4)
        self.assertEqual(pixels[:4], [0.0, 0.0, 0.0, 1.0])
        self.assertEqual(pixels[-4:], [1.0, 1.0, 1.0, 1.0])

    def test_on_image_removed_clears_state(self):
        c = self.plugin._controller
        self.assertIn("test_img_id", c._hist)
        c.on_image_removed("test_img_id")
        self.assertNotIn("test_img_id", c._hist)


if __name__ == "__main__":
    unittest.main()
