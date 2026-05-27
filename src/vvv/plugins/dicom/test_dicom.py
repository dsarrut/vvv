import unittest
from unittest.mock import MagicMock
import dearpygui.dearpygui as dpg
from vvv.plugins.dicom.plugin_dicom import DicomPlugin


class TestDicomPlugin(unittest.TestCase):
    def setUp(self):
        self.plugin = DicomPlugin()
        self.mock_api = MagicMock()
        self.mock_api.get_ui_config.return_value = {
            "colors": {
                "text_header": [255, 255, 255],
                "text_dim": [128, 128, 128],
            }
        }

    def test_metadata(self):
        self.assertEqual(self.plugin.plugin_id, "dicom_plugin")
        self.assertEqual(self.plugin.label, "DICOM Browser")
        self.assertEqual(self.plugin.order, 40)
        self.assertIsNotNone(self.plugin.description)

    def test_create_ui(self):
        if not dpg.is_dearpygui_running():
            dpg.create_context()
        with dpg.window(tag="test_parent"):
            self.plugin.create_ui(parent="test_parent", api=self.mock_api)
        self.assertTrue(dpg.does_item_exist("dicom_plugin"))
        dpg.delete_item("test_parent")

    def test_show_window(self):
        if not dpg.is_dearpygui_running():
            dpg.create_context()
        with dpg.window(tag="test_parent"):
            self.plugin.create_ui(parent="test_parent", api=self.mock_api)
        self.plugin.show_window()
        self.assertTrue(dpg.does_item_exist("dicom_plugin_window"))
        dpg.delete_item("dicom_plugin_window")
        dpg.delete_item("test_parent")


if __name__ == "__main__":
    unittest.main()
