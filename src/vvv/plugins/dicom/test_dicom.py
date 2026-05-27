import unittest
from unittest.mock import MagicMock, patch
import time
import os
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
        self.series_data = {
            "modality": "CT",
            "series_desc": "Chest CT",
            "date": "2026-01-01",
            "files": ["/path/to/dcm1.dcm", "/path/to/dcm2.dcm"],
            "patient_name": "John Doe",
            "study_desc": "Chest Study",
            "size": "512x512x2",
            "spacing": "1x1x2",
            "tags": [("0010,0010", "PatientName", "John Doe")],
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

    def test_scan_and_selection_lifecycle(self):
        if not dpg.is_dearpygui_running():
            dpg.create_context()
        with dpg.window(tag="test_parent"):
            self.plugin.create_ui(parent="test_parent", api=self.mock_api)
        
        self.plugin.show_window()
        ui = self.plugin._ui

        # Mock API scanning response
        # scan_dicom_folder yields tuples: (progress, status) or (progress, status, series_list)
        mock_scan_generator = [
            (0.5, "folder1"),
            (1.0, "done", [self.series_data])
        ]
        self.mock_api.scan_dicom_folder.return_value = mock_scan_generator

        # Trigger folder path and scanning
        dpg.set_value(ui._t("folder_path"), "/mock/folder")
        
        with patch("os.path.exists", return_value=True):
            ui.on_scan_clicked()
        
        # Wait briefly for daemon thread to execute generator
        timeout = time.time() + 2.0
        while not ui.scan_finished and time.time() < timeout:
            time.sleep(0.05)

        self.assertTrue(ui.scan_finished)
        
        # Run tick to populate and finalize scanning UI state
        ui.tick()

        # Check list item is created
        self.assertEqual(len(ui.scanned_series), 1)
        self.assertTrue(dpg.does_item_exist(ui._t("sel_0")))

        # Test selecting a series
        ui.on_series_selected(ui._t("sel_0"), None, 0)
        self.assertEqual(ui.active_idx, 0)
        self.assertEqual(ui.active_series["patient_name"], "John Doe")
        self.assertEqual(dpg.get_value(ui._t("lbl_patient")), "John Doe")

        # Test keyboard navigation selection movement
        ui.move_selection(0)  # should keep index 0
        self.assertEqual(ui.active_idx, 0)

        # Test opening series
        ui.on_open_clicked()
        self.mock_api.load_dicom_series.assert_called_once_with(self.series_data["files"])
        self.assertFalse(dpg.does_item_exist(ui.window_tag))

        dpg.delete_item("test_parent")


if __name__ == "__main__":
    unittest.main()
