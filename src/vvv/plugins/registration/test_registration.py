import unittest
from unittest.mock import MagicMock
import numpy as np
import dearpygui.dearpygui as dpg
from vvv.plugins.registration.plugin_registration import RegistrationPlugin


class TestRegistrationPlugin(unittest.TestCase):
    def setUp(self):
        self.plugin = RegistrationPlugin()
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
        self.assertEqual(self.plugin.plugin_id, "registration_plugin")
        self.assertEqual(self.plugin.label, "Registration Plugin")
        self.assertIsNotNone(self.plugin.description)
        self.assertEqual(self.plugin.order, 40)

    def test_state_lifecycle(self):
        self.assertEqual(self.plugin.serialize_image_state("image1"), {})
        self.plugin.restore_image_state("image1", {})

    def test_create_ui(self):
        if not dpg.is_dearpygui_running():
            dpg.create_context()
        with dpg.window(tag="test_parent"):
            self.plugin.create_ui(parent="test_parent", api=self.mock_api)
        self.assertTrue(dpg.does_item_exist("registration_plugin"))
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
        viewer.view_state.space = MagicMock()
        viewer.view_state.space.transform_file = "my_matrix.tfm"
        viewer.view_state.space.transform = None
        viewer.volume = MagicMock()
        viewer.volume.shape3d = [100, 100, 100]

        self.mock_api.get_active_viewer.return_value = viewer
        self.mock_api.get_image_display_name.return_value = ("Image ABC", False)

        self.plugin.update(self.mock_api)
        self.assertEqual(dpg.get_value("registration_plugin_text_reg_active_title"), "Image ABC")
        self.assertEqual(dpg.get_value("registration_plugin_text_reg_filename"), "my_matrix.tfm")

        dpg.delete_item("test_parent")


if __name__ == "__main__":
    unittest.main()
