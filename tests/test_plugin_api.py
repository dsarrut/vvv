import unittest
from unittest.mock import MagicMock
from vvv.plugins.plugin_api import PluginAPI


class TestPluginAPI(unittest.TestCase):
    def setUp(self):
        self.mock_gui = MagicMock()
        self.mock_controller = MagicMock()
        self.mock_gui.controller = self.mock_controller
        self.api = PluginAPI(self.mock_gui)

    def test_is_dirty_controller(self):
        self.mock_controller.ui_needs_refresh = True
        self.mock_gui.context_viewer = None
        self.assertTrue(self.api.is_dirty)

    def test_is_dirty_viewer(self):
        self.mock_controller.ui_needs_refresh = False
        mock_viewer = MagicMock()
        mock_viewer.view_state.is_data_dirty = True
        self.mock_gui.context_viewer = mock_viewer
        self.assertTrue(self.api.is_dirty)

    def test_get_active_image_name(self):
        mock_viewer = MagicMock()
        mock_viewer.image_id = "img_1"
        self.mock_gui.context_viewer = mock_viewer
        self.mock_controller.get_image_display_name.return_value = ("test_image.nii", None)
        self.assertEqual(self.api.get_active_image_name(), "test_image.nii")
        self.mock_controller.get_image_display_name.assert_called_with("img_1")

    def test_get_crosshair_world(self):
        mock_viewer = MagicMock()
        coords = [10.5, 20.0, -5.2]
        mock_viewer.view_state.camera.crosshair_phys_coord = coords
        self.mock_gui.context_viewer = mock_viewer
        self.assertEqual(self.api.get_crosshair_world(), coords)

    def test_get_mouse_position(self):
        self.mock_gui.interaction.last_mouse_pos = [100, 200]
        self.assertEqual(self.api.get_mouse_position(), [100, 200])
        del self.mock_gui.interaction.last_mouse_pos
        self.assertEqual(self.api.get_mouse_position(), [0, 0])

    def test_get_ui_config(self):
        self.mock_gui.ui_cfg = {"colors": {}}
        self.assertEqual(self.api.get_ui_config(), {"colors": {}})

    def test_create_labeled_field_delegates(self):
        self.api.create_labeled_field("Label", "tag_x", help_text="help")
        self.mock_gui.create_labeled_field.assert_called_once_with("Label", "tag_x", help_text="help")

    def test_request_refresh(self):
        self.api.request_refresh()
        self.assertTrue(self.mock_controller.ui_needs_refresh)


if __name__ == "__main__":
    unittest.main()
