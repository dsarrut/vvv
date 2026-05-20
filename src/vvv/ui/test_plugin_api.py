import unittest
from unittest.mock import MagicMock
from vvv.core.plugin_api import PluginAPI

class TestPluginAPI(unittest.TestCase):
    def setUp(self):
        self.mock_gui = MagicMock()
        self.mock_controller = MagicMock()
        self.mock_gui.controller = self.mock_controller
        self.api = PluginAPI(self.mock_gui)

    def test_is_dirty_controller(self):
        # Case 1: Controller flags a refresh
        self.mock_controller.ui_needs_refresh = True
        self.mock_gui.context_viewer = None
        self.assertTrue(self.api.is_dirty)

    def test_is_dirty_viewer(self):
        # Case 2: Viewer state is dirty
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
        
        name = self.api.get_active_image_name()
        self.assertEqual(name, "test_image.nii")
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

        # Test fallback
        del self.mock_gui.interaction.last_mouse_pos
        self.assertEqual(self.api.get_mouse_position(), [0, 0])

if __name__ == "__main__":
    unittest.main()