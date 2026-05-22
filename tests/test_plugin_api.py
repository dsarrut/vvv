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

    def test_is_dirty_overlay(self):
        self.mock_controller.ui_needs_refresh = False
        mock_viewer = MagicMock()
        mock_viewer.view_state.is_data_dirty = False
        mock_viewer.view_state.display.overlay_id = "overlay_img"
        
        mock_overlay_vs = MagicMock()
        mock_overlay_vs.is_data_dirty = True
        
        self.mock_controller.view_states = {"overlay_img": mock_overlay_vs}
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

    def test_discover_plugins_success(self):
        from vvv.plugins import discover_plugins
        plugins = discover_plugins()
        plugin_ids = {p.plugin_id for p in plugins}
        self.assertIn("dvf", plugin_ids)
        self.assertIn("intensity_plugin", plugin_ids)
        self.assertIn("debug", plugin_ids)
        
        for p in plugins:
            self.assertTrue(hasattr(p, "label"))
            self.assertTrue(hasattr(p, "create_ui"))
            self.assertTrue(hasattr(p, "update"))

    def test_discover_plugins_robustness(self):
        from unittest.mock import patch
        from vvv.plugins import discover_plugins
        
        mock_modules = [
            (None, "not_a_package", False),
            (None, "broken_plugin", True),
            (None, "intensity", True),
        ]
        
        with patch("pkgutil.iter_modules", return_value=mock_modules):
            with patch("importlib.import_module") as mock_import:
                def side_effect(name):
                    if "broken_plugin" in name:
                        raise ImportError("Mocked import error")
                    if "intensity" in name:
                        class MockPluginClass:
                            plugin_id = "mock_intensity"
                            label = "Mock Intensity"
                            def create_ui(self, parent, api): pass
                            def update(self, api): pass
                        mock_mod = MagicMock()
                        mock_mod.MockPluginClass = MockPluginClass
                        mock_mod.__dir__ = lambda *a, **kw: ["MockPluginClass"]
                        return mock_mod
                    raise ImportError("Unknown module")
                
                mock_import.side_effect = side_effect
                plugins = discover_plugins()
                
                self.assertEqual(len(plugins), 1)
                self.assertEqual(plugins[0].plugin_id, "mock_intensity")


if __name__ == "__main__":
    unittest.main()
