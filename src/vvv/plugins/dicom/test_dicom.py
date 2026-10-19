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
        self.mock_api.is_beginner_mode = False
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
        self.assertEqual(self.plugin._ui.api, self.mock_api)
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
            (1.0, "done", [self.series_data], [])
        ]
        self.mock_api.scan_dicom_folder.return_value = mock_scan_generator

        # Trigger folder path and scanning
        dpg.set_value(ui._t("input_folder_path"), "/mock/folder")
        
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
        assert ui.active_series is not None
        self.assertEqual(ui.active_series["patient_name"], "John Doe")
        self.assertEqual(dpg.get_value(ui._t("lbl_patient")), "John Doe")

        # Test keyboard navigation selection movement
        ui.move_selection(0)  # should keep index 0
        self.assertEqual(ui.active_idx, 0)

        # Test opening series
        ui.on_open_clicked()
        self.mock_api.load_dicom_series.assert_called_once_with(self.series_data["files"])
        self.assertTrue(dpg.does_item_exist(ui.window_tag))

        dpg.delete_item("test_parent")

    def test_string_sanitization(self):
        # Construct series data containing a surrogate escape '\udc80' and a null byte '\x00'
        series_with_bad_data = {
            "modality": "CT",
            "series_desc": "Bad\x00CT\udc80Series",
            "date": "2026-01-01",
            "files": ["/path/to/bad.dcm"],
            "patient_name": "John\x00Doe\udc80",
            "study_desc": "Bad\udc80Study",
            "size": "512x512x2",
            "spacing": "1x1x2",
            "tags": [("0010,0010", "PatientName", "John\x00Doe\udc80")],
        }

        if not dpg.is_dearpygui_running():
            dpg.create_context()
        with dpg.window(tag="test_parent"):
            self.plugin.create_ui(parent="test_parent", api=self.mock_api)
        
        self.plugin.show_window()
        ui = self.plugin._ui
        ui.scanned_series = [series_with_bad_data]
        ui._populate_series_list()

        # Select the series to verify no exceptions are raised and surrogates/nulls are stripped
        ui.on_series_selected(ui._t("sel_0"), None, 0)
        
        # Verify the displayed string is sanitized
        self.assertEqual(dpg.get_value(ui._t("lbl_patient")), "JohnDoe")
        assert ui.active_series is not None
        self.assertEqual(ui.active_series["patient_name"], "John\x00Doe\udc80")  # raw dict remains unmodified, UI is cleaned

        dpg.delete_item("test_parent")

    def test_beginner_mode(self):
        if not dpg.is_dearpygui_running():
            dpg.create_context()
        with dpg.window(tag="test_parent"):
            self.plugin.create_ui(parent="test_parent", api=self.mock_api)
        
        # Test beginner mode does not hide advanced metadata tags
        self.mock_api.is_beginner_mode = True
        self.plugin.show_window()
        self.assertTrue(dpg.is_item_shown(self.plugin._ui._t("table_panel")))
        self.assertTrue(dpg.is_item_shown(self.plugin._ui._t("metadata_header")))

        # Test non-beginner mode also shows advanced metadata tags
        self.mock_api.is_beginner_mode = False
        self.plugin.update(self.mock_api)
        self.assertTrue(dpg.is_item_shown(self.plugin._ui._t("table_panel")))
        self.assertTrue(dpg.is_item_shown(self.plugin._ui._t("metadata_header")))

        dpg.delete_item(self.plugin._ui.window_tag)
        dpg.delete_item("test_parent")

    def test_destroy(self):
        if not dpg.is_dearpygui_running():
            dpg.create_context()
        with dpg.window(tag="test_parent"):
            self.plugin.create_ui(parent="test_parent", api=self.mock_api)
        self.plugin.show_window()
        self.assertTrue(dpg.does_item_exist(self.plugin._ui.window_tag))
        self.plugin.destroy()
        self.assertFalse(dpg.does_item_exist(self.plugin._ui.window_tag))
        self.assertTrue(self.plugin._ui._stop_event.is_set())
        dpg.delete_item("test_parent")

    def test_populate_tags_table_sequence(self):
        if not dpg.is_dearpygui_running():
            dpg.create_context()
        with dpg.window(tag="test_parent"):
            self.plugin.create_ui(parent="test_parent", api=self.mock_api)
        
            ui = self.plugin._ui
            table_tag = "test_table"
            with dpg.table(tag=table_tag):
                dpg.add_table_column(label="Tag")
                dpg.add_table_column(label="Name")
                dpg.add_table_column(label="Value")

            # Test flat format
            flat_tags = [("0010,0010", "PatientName", "John Doe")]
            ui._populate_tags_table(table_tag, flat_tags, "")
            rows = dpg.get_item_children(table_tag, 1) or []
            self.assertEqual(len(rows), 1)

            # Test nested format
            nested_tags = [
                {
                    "tag": "(0054,0012)",
                    "name": "Energy Window Information Sequence",
                    "value": "1 item(s)",
                    "is_seq": True,
                    "nested": [
                        [
                            {
                                "tag": "(0054,0013)",
                                "name": "Energy Window Range Sequence",
                                "value": "1 item(s)",
                                "is_seq": False,
                                "nested": []
                            }
                        ]
                    ]
                }
            ]
            ui._populate_tags_table(table_tag, nested_tags, "")
            rows = dpg.get_item_children(table_tag, 1) or []
            self.assertEqual(len(rows), 1)
        
        dpg.delete_item("test_parent")

    @patch("pydicom.dcmread")
    @patch("os.path.exists", return_value=True)
    @patch("os.path.isfile", return_value=True)
    def test_on_image_loaded_with_sequence(self, mock_isfile, mock_exists, mock_dcmread):
        if not dpg.is_dearpygui_running():
            dpg.create_context()
        
        self.mock_api.run_on_main_thread = lambda f: f()
        
        with dpg.window(tag="test_parent"):
            self.plugin.create_ui(parent="test_parent", api=self.mock_api)
            ui = self.plugin._ui
            ui.show_window()
            
            # Setup mock volume and api
            mock_volume = MagicMock()
            mock_volume.file_paths = ["/path/to/dicom.dcm"]
            self.mock_api.get_volumes.return_value = {"img_1": mock_volume}
            self.mock_api.get_image_display_name.return_value = ("Test Image", "")
            
            # Mock pydicom elements
            import pydicom
            mock_elem_simple = MagicMock()
            mock_elem_simple.tag.group = 0x0010
            mock_elem_simple.tag.element = 0x0010
            mock_elem_simple.name = "PatientName"
            mock_elem_simple.value = "John Doe"
            
            mock_sub_elem = MagicMock()
            mock_sub_elem.tag.group = 0x0018
            mock_sub_elem.tag.element = 0x0050
            mock_sub_elem.name = "SliceThickness"
            mock_sub_elem.value = "1.5"
            
            mock_dataset = MagicMock(spec=pydicom.dataset.Dataset)
            mock_dataset.__iter__.return_value = [mock_sub_elem]
            
            mock_elem_seq = MagicMock()
            mock_elem_seq.tag.group = 0x0054
            mock_elem_seq.tag.element = 0x0012
            mock_elem_seq.name = "EnergyWindowInformationSequence"
            # We make it act as a Sequence class instance (which is a list subclass in pydicom)
            mock_sequence = MagicMock(spec=pydicom.sequence.Sequence)
            mock_sequence.__iter__.return_value = [mock_dataset]
            mock_sequence.__len__.return_value = 1
            mock_elem_seq.value = mock_sequence
            
            mock_ds = MagicMock()
            mock_ds.__iter__.return_value = [mock_elem_simple, mock_elem_seq]
            mock_dcmread.return_value = mock_ds
            
            # Call on_image_loaded
            ui.on_image_loaded("img_1")
            
            # Wait for the async thread
            timeout = time.time() + 2.0
            while "img_1" not in ui.open_image_tabs and time.time() < timeout:
                time.sleep(0.05)
                
            self.assertIn("img_1", ui.open_image_tabs)
            tags = ui.open_image_tabs["img_1"]["tags"]
            self.assertEqual(len(tags), 2)
            
            # First tag is simple
            self.assertEqual(tags[0]["tag"], "(0010,0010)")
            self.assertFalse(tags[0]["is_seq"])
            
            # Second tag is sequence
            self.assertEqual(tags[1]["tag"], "(0054,0012)")
            self.assertTrue(tags[1]["is_seq"])
            self.assertEqual(len(tags[1]["nested"]), 1)
            self.assertEqual(tags[1]["nested"][0][0]["tag"], "(0018,0050)")
        
        dpg.delete_item("test_parent")

    def test_rtstruct_selection_and_load_with_open_image(self):
        if not dpg.is_dearpygui_running():
            dpg.create_context()

        with dpg.window(tag="test_parent"):
            self.plugin.create_ui(parent="test_parent", api=self.mock_api)
            ui = self.plugin._ui
            ui.show_window()

            rtstruct_series = {
                "id": "rtstruct_uid_123",
                "modality": "RTSTRUCT",
                "series_desc": "Structure Set",
                "date": "2026-01-01",
                "files": ["/path/to/rtstruct.dcm"],
                "patient_name": "John Doe",
                "study_desc": "Chest Study",
                "size": "5 ROI(s)",
                "spacing": "N/A",
                "referenced_series_uid": "ct_uid_456",
                "frame_of_ref_uid": "for_uid_789",
                "tags": [],
            }
            ui.scanned_series = [rtstruct_series]
            ui._populate_series_list()

            # Select the RTSTRUCT series
            sel_tag = ui._t("sel_0")
            ui.on_series_selected(sel_tag, None, 0)
            self.assertEqual(dpg.get_item_label(ui._t("btn_open")), "Load RT-Struct ROIs")

            # Mock an open volume in VVV
            mock_vol = MagicMock()
            mock_vol.is_roi = False
            self.mock_api.get_volumes.return_value = {"img_ct": mock_vol}

            # Clicking open should directly show the RT-Struct selection modal on img_ct
            ui.on_open_clicked()
            self.mock_api.show_rtstruct_selection_modal.assert_called_once_with(
                "/path/to/rtstruct.dcm", target_image_id="img_ct"
            )

        dpg.delete_item("test_parent")

    def test_rtstruct_load_auto_loads_scanned_reference_series(self):
        if not dpg.is_dearpygui_running():
            dpg.create_context()

        with dpg.window(tag="test_parent"):
            self.plugin.create_ui(parent="test_parent", api=self.mock_api)
            ui = self.plugin._ui
            ui.show_window()

            ct_series = {
                "id": "ct_uid_456",
                "modality": "CT",
                "series_desc": "Chest CT",
                "date": "2026-01-01",
                "files": ["/path/to/ct1.dcm", "/path/to/ct2.dcm"],
                "patient_name": "John Doe",
                "study_desc": "Chest Study",
                "frame_of_ref_uid": "for_uid_789",
                "tags": [],
            }
            rtstruct_series = {
                "id": "rtstruct_uid_123",
                "modality": "RTSTRUCT",
                "series_desc": "Structure Set",
                "date": "2026-01-01",
                "files": ["/path/to/rtstruct.dcm"],
                "patient_name": "John Doe",
                "study_desc": "Chest Study",
                "size": "5 ROI(s)",
                "spacing": "N/A",
                "referenced_series_uid": "ct_uid_456",
                "frame_of_ref_uid": "for_uid_789",
                "tags": [],
            }
            ui.scanned_series = [ct_series, rtstruct_series]
            ui.active_series = rtstruct_series
            self.mock_api.get_volumes.return_value = {}  # No images currently open

            # Calling on_load_rtstruct_clicked should auto-load the CT series first
            ui.on_load_rtstruct_clicked()
            self.mock_api.load_dicom_series_and_rtstruct.assert_called_once_with(
                ["/path/to/ct1.dcm", "/path/to/ct2.dcm"], "/path/to/rtstruct.dcm"
            )

        dpg.delete_item("test_parent")

    def test_rtstruct_load_no_reference_shows_message(self):
        if not dpg.is_dearpygui_running():
            dpg.create_context()

        with dpg.window(tag="test_parent"):
            self.plugin.create_ui(parent="test_parent", api=self.mock_api)
            ui = self.plugin._ui
            ui.show_window()

            rtstruct_series = {
                "id": "rtstruct_uid_123",
                "modality": "RTSTRUCT",
                "series_desc": "Structure Set",
                "files": ["/path/to/rtstruct.dcm"],
                "referenced_series_uid": "unknown_uid",
                "frame_of_ref_uid": "unknown_for",
                "tags": [],
            }
            ui.scanned_series = [rtstruct_series]
            ui.active_series = rtstruct_series
            self.mock_api.get_volumes.return_value = {}

            ui.on_load_rtstruct_clicked()
            self.mock_api.show_message.assert_called_once()
            args = self.mock_api.show_message.call_args[0]
            self.assertEqual(args[0], "Reference Image Required")

        dpg.delete_item("test_parent")

    def test_scan_dicom_folder_detects_rtstruct(self):
        from vvv.core.controller import Controller

        c = Controller()
        results = list(c.file.scan_dicom_folder("data/rt_dcm"))
        final_series = results[-1][2]
        modalities = [s["modality"] for s in final_series]
        self.assertIn("RTSTRUCT", modalities)
        rtstruct = next(s for s in final_series if s["modality"] == "RTSTRUCT")
        self.assertIn("ROI(s)", rtstruct["size"])
        self.assertEqual(rtstruct["spacing"], "N/A")
    def test_modality_theme_distinction(self):
        ui = self.plugin._ui
        theme_ct = ui._get_modality_theme("CT")
        theme_rtstruct = ui._get_modality_theme("RTSTRUCT")
        theme_rtdose = ui._get_modality_theme("RTDOSE")
        theme_pet = ui._get_modality_theme("PT")
        theme_nm = ui._get_modality_theme("NM")
        theme_mr = ui._get_modality_theme("MR")

        # Ensure RTSTRUCT does not collide with CT
        self.assertNotEqual(theme_rtstruct, theme_ct)
        # Ensure RTDOSE does not collide with CT or RTSTRUCT
        self.assertNotEqual(theme_rtdose, theme_ct)
        self.assertNotEqual(theme_rtdose, theme_rtstruct)

        # Ensure all major modalities have unique themes
        themes = [theme_ct, theme_rtstruct, theme_rtdose, theme_pet, theme_nm, theme_mr]
        self.assertEqual(len(themes), len(set(themes)))

    def test_tick_does_not_overwrite_scan_status_when_idle(self):
        """Verify that tick() preserves the scan_status text after scan finishes (PA14)."""
        if not dpg.is_dearpygui_running():
            dpg.create_context()
        with dpg.window(tag="test_parent"):
            self.plugin.create_ui(parent="test_parent", api=self.mock_api)

        self.plugin.show_window()
        ui = self.plugin._ui
        ui.scanned_series = [self.series_data]
        ui.scan_status_text = "  scanning_dir..."
        ui.scan_finished = True

        # First tick commits completion
        ui.tick()
        self.assertEqual(dpg.get_value(ui._t("scan_status")), "  (1 found)")

        # Subsequent ticks when idle should NOT overwrite the status with scan_status_text
        ui.tick()
        ui.tick()
        self.assertEqual(dpg.get_value(ui._t("scan_status")), "  (1 found)")

        dpg.delete_item("test_parent")


if __name__ == "__main__":
    unittest.main()
