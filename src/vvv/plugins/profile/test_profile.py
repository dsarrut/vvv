import unittest
from unittest.mock import MagicMock
import dearpygui.dearpygui as dpg
from vvv.plugins.profile.plugin_profile import ProfilePlugin


class TestProfilePlugin(unittest.TestCase):
    def setUp(self):
        self.plugin = ProfilePlugin()
        self.mock_api = MagicMock()
        self.mock_api.is_beginner_mode = False
        self.mock_api.get_ui_config.return_value = {
            "colors": {
                "text_header": [255, 255, 255],
                "text_active": [255, 255, 255],
                "text_dim": [128, 128, 128],
                "outdated": [255, 165, 0],
            }
        }
        self.mock_api.get_active_viewer.return_value = None

    def test_metadata(self):
        self.assertEqual(self.plugin.plugin_id, "profile_plugin")
        self.assertEqual(self.plugin.label, "Profiles Plugin")
        self.assertIsNotNone(self.plugin.description)
        self.assertEqual(self.plugin.order, 30)

    def test_state_lifecycle(self):
        # State pre-populates with two mock profiles when get_image_state is called
        self.plugin.on_image_loaded("image1")
        state = self.plugin._controller.get_image_state("image1")
        self.assertEqual(len(state.profiles), 2)

        # Serialization
        serialized = self.plugin.serialize_image_state("image1")
        self.assertIn("profiles", serialized)
        self.assertEqual(len(serialized["profiles"]), 2)

        # Restore state
        self.plugin.restore_image_state("image2", serialized)
        state2 = self.plugin._controller.get_image_state("image2")
        self.assertEqual(len(state2.profiles), 2)

        # Removal
        self.plugin.on_image_removed("image1")
        self.assertNotIn("image1", self.plugin._controller._states)

    def test_create_ui(self):
        if not dpg.is_dearpygui_running():
            dpg.create_context()
        with dpg.window(tag="test_parent"):
            self.plugin.create_ui(parent="test_parent", api=self.mock_api)
        self.assertTrue(dpg.does_item_exist("profile_plugin"))
        dpg.delete_item("test_parent")

    def test_update_ui(self):
        if not dpg.is_dearpygui_running():
            dpg.create_context()
        with dpg.window(tag="test_parent"):
            self.plugin.create_ui(parent="test_parent", api=self.mock_api)

        # Update when no viewer active
        self.plugin.update(self.mock_api)

        # Update when viewer is active
        viewer = MagicMock()
        viewer.image_id = "image_abc"
        viewer.view_state = MagicMock()
        viewer.volume = MagicMock()
        viewer.volume.is_rgb = False
        self.mock_api.get_active_viewer.return_value = viewer
        self.mock_api.get_image_display_name.return_value = ("Image ABC", False)

        self.plugin.update(self.mock_api)
        self.assertEqual(
            dpg.get_value("profile_plugin_active_title"), "Image ABC [Plugin UI Only]"
        )

        dpg.delete_item("test_parent")


if __name__ == "__main__":
    unittest.main()
