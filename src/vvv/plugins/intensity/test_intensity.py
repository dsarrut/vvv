import unittest
from unittest.mock import MagicMock, patch
import numpy as np
import dearpygui.dearpygui as dpg
from vvv.plugins.intensity.plugin_intensity import IntensityPlugin
from vvv.plugins.intensity.control_intensity import IntensityController


class TestIntensityPlugin(unittest.TestCase):
    def setUp(self):
        # Create DPG registry if it doesn't exist
        if not dpg.does_item_exist("global_texture_registry"):
            dpg.add_texture_registry(tag="global_texture_registry")

        self.plugin = IntensityPlugin()
        self.mock_api = MagicMock()
        self.mock_api.is_beginner_mode = False
        self.mock_api.beginner_tags = []

        # Configure mock active image/viewer
        self.mock_viewer = MagicMock()
        self.mock_viewer.image_id = "test_img_id"
        self.mock_viewer.volume.is_rgb = False
        self.mock_viewer.volume.data = np.array([1, 2, 3])
        self.mock_viewer.volume.num_components = 1
        
        # Setup view state display
        self.mock_viewer.view_state.display.ww = 100.0
        self.mock_viewer.view_state.display.wl = 50.0
        self.mock_viewer.view_state.display.colormap = "Grayscale"
        self.mock_viewer.view_state.display.base_threshold = None
        self.mock_viewer.view_state.display.hist_use_bars = False
        self.mock_viewer.view_state.display.hist_use_log = False
        self.mock_viewer.view_state.display.hist_x_center = 50.0
        self.mock_viewer.view_state.display.hist_x_range = 150.0
        self.mock_viewer.view_state.display.hist_y_max = 1.0
        self.mock_viewer.view_state.display.hist_bins = 256
        self.mock_viewer.view_state.use_log_y = False
        
        # Setup histogram data
        self.mock_viewer.view_state.hist_data_x = np.array([0.0, 10.0, 20.0])
        self.mock_viewer.view_state.hist_data_y = np.array([5.0, 10.0, 15.0])
        self.mock_viewer.view_state.get_hist_bin_width.return_value = 10.0
        self.mock_viewer.view_state.get_hist_max_y.return_value = 15.0

        # API return values
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
        c.bind(self.mock_api)
        c.on_preset_changed(None, "CT: Bone", None)
        
        self.mock_viewer.view_state.apply_wl_preset.assert_called_with("CT: Bone")
        self.mock_api._controller.sync.propagate_window_level.assert_called_with("test_img_id")
        self.mock_api.request_refresh.assert_called()

    def test_ww_wl_changed(self):
        c = self.plugin._controller
        c.bind(self.mock_api)
        
        c.on_ww_changed(None, 120.0, None)
        self.assertEqual(self.mock_viewer.view_state.display.ww, 120.0)
        
        c.on_wl_changed(None, 60.0, None)
        self.assertEqual(self.mock_viewer.view_state.display.wl, 60.0)
        
        self.mock_api._controller.sync.propagate_window_level.assert_called_with("test_img_id")

    def test_colormap_changed(self):
        c = self.plugin._controller
        c.bind(self.mock_api)
        c.on_colormap_changed(None, "Hot", None)
        
        self.assertEqual(self.mock_viewer.view_state.display.colormap, "Hot")
        self.mock_api._controller.sync.propagate_colormap.assert_called_with("test_img_id")

    def test_threshold_callbacks(self):
        c = self.plugin._controller
        c.bind(self.mock_api)
        
        c.on_threshold_changed(None, 15.0, None)
        self.assertEqual(self.mock_viewer.view_state.display.base_threshold, 15.0)
        
        c.on_threshold_toggle(None, False, None)
        self.assertIsNone(self.mock_viewer.view_state.display.base_threshold)

    def test_hist_log_bar_center_toggles(self):
        c = self.plugin._controller
        c.bind(self.mock_api)
        
        # Center
        c.on_hist_center(None, None, None)
        self.assertEqual(self.mock_viewer.view_state.display.hist_x_center, 50.0)
        self.assertEqual(self.mock_viewer.view_state.display.hist_x_range, self.mock_viewer.view_state.display.ww / 0.3)
        
        # Log toggle
        c.on_hist_log_toggle(None, None, None)
        self.assertTrue(self.mock_viewer.view_state.display.hist_use_log)
        self.assertIsNone(self.mock_viewer.view_state.display.hist_y_max)
        
        # Bar toggle
        c.on_hist_bar_toggle(None, None, None)
        self.assertTrue(self.mock_viewer.view_state.display.hist_use_bars)

    @patch("dearpygui.dearpygui.is_item_shown", return_value=True)
    def test_computing_full_hist_visibility(self, mock_shown):
        c = self.plugin._controller
        c.bind(self.mock_api)
        
        # Create UI first to set up the text components
        with dpg.window(tag="test_visibility_win"):
            self.plugin.create_ui(parent="test_visibility_win", api=self.mock_api)
        c.on_hist_popup(None, None, None)
        
        txt_panel = c._t("txt_computing_full_hist")
        txt_popup = c._t("txt_popup_computing_full_hist")
        
        # Prevent the background thread from running by setting dirty to False
        vs = self.mock_viewer.view_state
        vs.histogram_is_dirty = False
        vs._hist_vol_data_id = id(self.mock_viewer.volume.data)
        
        # 1. When computing_full_hist is True
        vs.computing_full_hist = True
        c._refresh_wl_histogram(self.mock_viewer, has_image=True, is_rgb=False)
        self.assertTrue(dpg.get_item_configuration(txt_panel)["show"])
        self.assertTrue(dpg.get_item_configuration(txt_popup)["show"])
        
        # 2. When computing_full_hist is False
        vs.computing_full_hist = False
        c._refresh_wl_histogram(self.mock_viewer, has_image=True, is_rgb=False)
        self.assertFalse(dpg.get_item_configuration(txt_panel)["show"])
        self.assertFalse(dpg.get_item_configuration(txt_popup)["show"])

    def test_step_buttons(self):
        c = self.plugin._controller
        c.bind(self.mock_api)
        
        with dpg.window(tag="test_step_win"):
            tag = c._t("drag_ww")
            dpg.add_drag_float(tag=tag, default_value=100.0)
            
        c.on_step_button_clicked(None, None, {"tag": tag, "dir": 1})
        # ww step is ww * 0.02 = 2.0. So 100 + 2.0 = 102.0
        self.assertEqual(self.mock_viewer.view_state.display.ww, 102.0)

    def test_drag_lower_upper_level_callbacks(self):
        c = self.plugin._controller
        c.bind(self.mock_api)
        
        with dpg.window(tag="test_drag_win"):
            self.plugin.create_ui(parent="test_drag_win", api=self.mock_api)
            
        # Lower drag line
        # wl = 50.0, lower moved to 10.0 -> ww = 2 * |50 - 10| = 80.0
        c.on_hist_drag_lower(None, 10.0, None)
        self.assertEqual(self.mock_viewer.view_state.display.ww, 80.0)
        self.assertEqual(self.mock_viewer.view_state.display.wl, 50.0)
        
        # Upper drag line
        # wl = 50.0, upper moved to 110.0 -> ww = 2 * |50 - 110| = 120.0
        c.on_hist_drag_upper(None, 110.0, None)
        self.assertEqual(self.mock_viewer.view_state.display.ww, 120.0)
        self.assertEqual(self.mock_viewer.view_state.display.wl, 50.0)
        
        # Level drag line
        # level moved to 60.0, ww remains 120.0
        c.on_hist_drag_level(None, 60.0, None)
        self.assertEqual(self.mock_viewer.view_state.display.wl, 60.0)
        self.assertEqual(self.mock_viewer.view_state.display.ww, 120.0)
        
        # Dragging lower beyond level clamps ww to a positive value
        c.on_hist_drag_lower(None, 70.0, None) # 70 > 60.0, abs is 10.0, ww is 20.0
        self.assertEqual(self.mock_viewer.view_state.display.ww, 20.0)

    def test_colorscale_texture_generation(self):
        c = self.plugin._controller
        c.bind(self.mock_api)
        
        # Create UI first to set up the textures
        with dpg.window(tag="test_colorscale_win"):
            self.plugin.create_ui(parent="test_colorscale_win", api=self.mock_api)
        
        # Trigger popup UI which creates the colorscale texture
        c.on_hist_popup(None, None, None)
        
        self.mock_viewer.view_state.display.wl = 50.0
        self.mock_viewer.view_state.display.ww = 100.0 # [0, 100]
        self.mock_viewer.view_state.display.hist_x_center = 50.0
        self.mock_viewer.view_state.display.hist_x_range = 200.0 # [-50, 150]
        
        c._update_colorscale_texture(self.mock_viewer.view_state)
        tex_tag = c._t("wl_colorscale_tex")
        self.assertTrue(dpg.does_item_exist(tex_tag))
        
        pixels = dpg.get_value(tex_tag)
        self.assertIsNotNone(pixels)
        self.assertEqual(len(pixels), 256 * 4)

    def test_compute_colorscale_gradient(self):
        from vvv.maths.image_utils import compute_colorscale_gradient

        # Test grayscale colormap
        pixels = compute_colorscale_gradient(
            wl=50.0, ww=100.0, cmap_name="Grayscale", img_min=-50.0, img_max=150.0
        )
        self.assertEqual(len(pixels), 256 * 4)
        # Check boundary mapping: values below lower (50 - 50 = 0) are mapped to black [0, 0, 0, 1]
        # At img_min = -50, it is below lower bound. First pixel should be black.
        self.assertEqual(pixels[:4], [0.0, 0.0, 0.0, 1.0])
        # At img_max = 150, it is above upper bound (50 + 50 = 100). Last pixel should be white.
        self.assertEqual(pixels[-4:], [1.0, 1.0, 1.0, 1.0])


if __name__ == "__main__":
    unittest.main()

