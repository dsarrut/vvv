import unittest
from unittest.mock import MagicMock
import dearpygui.dearpygui as dpg
from vvv.plugins.roi.plugin_roi import RoiPlugin


class TestRoiPlugin(unittest.TestCase):
    def setUp(self):
        self.plugin = RoiPlugin()
        self.mock_api = MagicMock()
        self.mock_api._gui.is_beginner_mode = False
        self.mock_api.get_ui_config.return_value = {
            "colors": {
                "text_header": [255, 255, 255],
                "text_dim": [128, 128, 128],
                "text_active": [255, 255, 255],
            },
            "layout": {
                "nav_btn_h": 35,
            }
        }

    def test_metadata(self):
        self.assertEqual(self.plugin.plugin_id, "roi_plugin")
        self.assertEqual(self.plugin.label, "ROIs (Plugin)")
        self.assertEqual(self.plugin.order, 70)
        self.assertIsNotNone(self.plugin.description)

    def test_create_ui(self):
        if not dpg.is_dearpygui_running():
            dpg.create_context()
        with dpg.window(tag="test_parent"):
            self.plugin.create_ui(parent="test_parent", api=self.mock_api)
        
        self.assertEqual(self.plugin._ui.api, self.mock_api)
        
        # Verify that namespaced elements are created
        self.assertTrue(dpg.does_item_exist(self.plugin._ui._t("panel_group")))
        self.assertTrue(dpg.does_item_exist(self.plugin._ui._t("text_roi_active_title")))
        self.assertTrue(dpg.does_item_exist(self.plugin._ui._t("btn_roi_load")))
        self.assertTrue(dpg.does_item_exist(self.plugin._ui._t("roi_list_table")))
        
        dpg.delete_item("test_parent")

    def test_lifecycle_and_mock_callbacks(self):
        if not dpg.is_dearpygui_running():
            dpg.create_context()
        with dpg.window(tag="test_parent"):
            self.plugin.create_ui(parent="test_parent", api=self.mock_api)

        # Test stubs run without error
        self.plugin.update(self.mock_api)
        self.plugin.on_image_loaded("img1")
        self.plugin.on_image_removed("img1")
        self.assertEqual(self.plugin.serialize_image_state("img1"), {})
        self.plugin.restore_image_state("img1", {})
        self.plugin.save_settings(self.mock_api)
        self.plugin.load_settings(self.mock_api)

        # Test UI callbacks run without error
        ui = self.plugin._ui
        ui.on_mock_load_clicked(None, None, None)
        self.mock_api._gui.show_status_message.assert_called_with("ROI Plugin [Mock]: Load button clicked")

        # Test combo box toggle callback
        ui.on_mock_mode_changed(None, "Label Map", None)
        self.assertFalse(dpg.get_item_configuration(ui._t("group_roi_mode2"))["show"])

        ui.on_mock_mode_changed(None, "Target FG (val)", None)
        self.assertTrue(dpg.get_item_configuration(ui._t("group_roi_mode2"))["show"])

        # Test mock action
        ui.on_mock_action("btn_test", None, None)
        self.mock_api._gui.show_status_message.assert_called_with("ROI Plugin [Mock]: Callback triggered (sender: btn_test)")

        self.plugin.destroy()
        dpg.delete_item("test_parent")


if __name__ == "__main__":
    unittest.main()
