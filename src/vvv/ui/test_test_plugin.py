import unittest
from unittest.mock import MagicMock, patch
import numpy as np
from vvv.plugins.test_debug import TestDebugPlugin

class TestTestDebugPlugin(unittest.TestCase):
    def setUp(self):
        self.plugin = TestDebugPlugin()
        self.mock_api = MagicMock()
        # Default mock values
        self.mock_api.get_mouse_position.return_value = [0, 0]
        self.mock_api.get_active_image_name.return_value = "image.nii"
        self.mock_api.get_crosshair_world.return_value = [1.0, 2.0, 3.0]
        self.mock_api.is_dirty = True

    @patch("dearpygui.dearpygui.set_value")
    def test_update_lifecycle(self, mock_set_value):
        # First update: everything should be set
        self.plugin.update(self.mock_api)
        
        # Check mouse, image, and coords were set
        self.assertTrue(any("mouse" in call.args[0] for call in mock_set_value.call_args_list))
        self.assertTrue(any("images" in call.args[0] for call in mock_set_value.call_args_list))
        self.assertTrue(any("coords" in call.args[0] for call in mock_set_value.call_args_list))
        
        mock_set_value.reset_mock()
        
        # Second update: same data, is_dirty is False
        self.mock_api.is_dirty = False
        self.plugin.update(self.mock_api)
        
        # No dpg.set_value calls should happen because nothing changed
        mock_set_value.assert_not_called()

    @patch("dearpygui.dearpygui.set_value")
    def test_mouse_updates_independently(self, mock_set_value):
        # Initial update
        self.plugin.update(self.mock_api)
        mock_set_value.reset_mock()

        # Mouse moves, but is_dirty remains False
        self.mock_api.get_mouse_position.return_value = [10, 10]
        self.mock_api.is_dirty = False
        
        self.plugin.update(self.mock_api)
        
        # Only mouse should update
        self.assertEqual(mock_set_value.call_count, 1)
        self.assertIn("mouse", mock_set_value.call_args[0][0])

    @patch("dearpygui.dearpygui.group")
    @patch("dearpygui.dearpygui.does_item_exist")
    def test_create_ui(self, mock_exists, mock_group):
        mock_gui = MagicMock()
        mock_gui.ui_cfg = {"colors": {"text_header": [255, 255, 255]}}
        mock_exists.return_value = False
        self.plugin.create_ui(0, mock_gui)
        
        # Verify fields were created via gui helper
        self.assertEqual(mock_gui.create_labeled_field.call_count, 3)