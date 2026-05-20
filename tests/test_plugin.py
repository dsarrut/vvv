import unittest
from unittest.mock import MagicMock, patch
import numpy as np
from vvv.plugins.test_plugin import TestDebugPlugin


class TestTestDebugPlugin(unittest.TestCase):
    def setUp(self):
        self.plugin = TestDebugPlugin()
        self.mock_api = MagicMock()
        self.mock_api.get_mouse_position.return_value = [0, 0]
        self.mock_api.get_active_image_name.return_value = "image.nii"
        self.mock_api.get_crosshair_world.return_value = [1.0, 2.0, 3.0]
        self.mock_api.is_dirty = True

    @patch("dearpygui.dearpygui.set_value")
    def test_update_lifecycle(self, mock_set_value):
        self.plugin.update(self.mock_api)
        self.assertTrue(any("mouse" in call.args[0] for call in mock_set_value.call_args_list))
        self.assertTrue(any("images" in call.args[0] for call in mock_set_value.call_args_list))
        self.assertTrue(any("coords" in call.args[0] for call in mock_set_value.call_args_list))

        mock_set_value.reset_mock()
        self.mock_api.is_dirty = False
        self.plugin.update(self.mock_api)
        mock_set_value.assert_not_called()

    @patch("dearpygui.dearpygui.set_value")
    def test_mouse_updates_independently(self, mock_set_value):
        self.plugin.update(self.mock_api)
        mock_set_value.reset_mock()

        self.mock_api.get_mouse_position.return_value = [10, 10]
        self.mock_api.is_dirty = False
        self.plugin.update(self.mock_api)

        self.assertEqual(mock_set_value.call_count, 1)
        self.assertIn("mouse", mock_set_value.call_args[0][0])

    def test_create_ui(self):
        import dearpygui.dearpygui as dpg
        mock_api = MagicMock()
        mock_api.get_ui_config.return_value = {"colors": {"text_header": [255, 255, 255]}}
        with dpg.window(tag="test_create_ui_win"):
            self.plugin.create_ui(parent=0, api=mock_api)
        self.assertEqual(mock_api.create_labeled_field.call_count, 3)

    def test_plugin_metadata(self):
        self.assertEqual(self.plugin.plugin_id, "test_debug_plugin")
        self.assertEqual(self.plugin.label, "DEBUG")
        self.assertIsNotNone(self.plugin.description)


if __name__ == "__main__":
    unittest.main()
