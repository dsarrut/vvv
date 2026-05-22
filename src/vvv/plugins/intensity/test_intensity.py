import unittest
from unittest.mock import MagicMock, patch
import dearpygui.dearpygui as dpg
from vvv.plugins.intensity import IntensityPlugin


class TestIntensityPlugin(unittest.TestCase):
    def setUp(self):
        self.plugin = IntensityPlugin()
        self.mock_api = MagicMock()
        self.mock_api.is_beginner_mode = False
        self.mock_api.beginner_tags = []
        self.mock_viewer = MagicMock()
        self.mock_viewer.view_state.display.hist_use_bars = False
        self.mock_api.get_active_viewer.return_value = self.mock_viewer
        self.mock_api.get_active_image_name.return_value = "image.nii"
        self.mock_api.get_ui_config.return_value = {
            "colors": {
                "text_header": [255, 255, 255],
                "text_active": [255, 255, 255],
                "text_dim": [150, 150, 150],
            }
        }

    def test_plugin_metadata(self):
        self.assertEqual(self.plugin.plugin_id, "intensity_plugin")
        self.assertEqual(self.plugin.label, "Intensity Plugin")
        self.assertIsNotNone(self.plugin.description)

    @patch("dearpygui.dearpygui.set_value")
    def test_update_lifecycle(self, mock_set_value):
        with dpg.window(tag="test_update_win"):
            self.plugin.create_ui(parent="test_update_win", api=self.mock_api)
        self.plugin.update(self.mock_api)
        expected_tag = f"{self.plugin.plugin_id}_active_title"
        self.assertTrue(any(call.args[0] == expected_tag for call in mock_set_value.call_args_list))

    def test_create_ui(self):
        with dpg.window(tag="test_intensity_win"):
            self.plugin.create_ui(parent="test_intensity_win", api=self.mock_api)
        self.assertTrue(dpg.does_item_exist(self.plugin.plugin_id))

    def test_popup_ui(self):
        with dpg.window(tag="test_popup_win"):
            self.plugin.create_ui(parent="test_popup_win", api=self.mock_api)
        self.plugin._controller.on_hist_popup(None, None, None)
        popup_tag = f"{self.plugin.plugin_id}_wl_hist_popup_win"
        self.assertTrue(dpg.does_item_exist(popup_tag))


if __name__ == "__main__":
    unittest.main()
