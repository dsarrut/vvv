import unittest
from unittest.mock import MagicMock
import dearpygui.dearpygui as dpg

from vvv.plugins.dose.plugin_dose import DosePlugin


class TestDosePlugin(unittest.TestCase):
    def setUp(self):
        self.plugin = DosePlugin()
        self.mock_api = MagicMock()
        self.mock_api.is_beginner_mode = False
        self.mock_api.beginner_tags = []

        self.mock_viewer = MagicMock()
        self.mock_viewer.image_id = "img_1"
        self.mock_viewer.volume.name = "ct.nii.gz"
        self.mock_viewer.volume.unit = "HU"

        self.mock_overlay = MagicMock()
        self.mock_overlay.name = "dose.nii.gz"
        self.mock_overlay.unit = None

        self.mock_viewer.view_state.display.overlay = None

        self.mock_api.get_active_viewer.return_value = self.mock_viewer
        self.mock_api.get_volumes.return_value = {
            "img_1": self.mock_viewer.volume,
            "img_2": self.mock_overlay,
        }
        self.mock_api.get_viewers.return_value = {"V1": self.mock_viewer}
        self.mock_api.get_ui_config.return_value = {
            "colors": {
                "text_header": [255, 255, 255, 255],
                "text_active": [255, 255, 255, 255],
                "text_dim": [150, 150, 150, 255],
                "warning": [255, 180, 50, 255],
                "text_status_ok": [80, 220, 100, 255],
            }
        }

        # Build UI inside a valid DPG window container
        parent_tag = f"test_dose_parent_{self._testMethodName}"
        with dpg.window(tag=parent_tag):
            self.plugin.create_ui(parent_tag, self.mock_api)

    def tearDown(self):
        parent_tag = f"test_dose_parent_{self._testMethodName}"
        if dpg.does_item_exist(parent_tag):
            dpg.delete_item(parent_tag)

    def test_metadata(self):
        self.assertEqual(self.plugin.plugin_id, "dose_plugin")
        self.assertEqual(self.plugin.label, "Dose")
        self.assertEqual(self.plugin.order, 80)

    def test_inactive_when_unit_not_gy(self):
        # Base image is HU, no overlay
        is_active, target_vol, is_ov, unit = self.plugin._controller.get_dose_status()
        self.assertFalse(is_active)
        self.assertEqual(unit, "HU")

        self.plugin._ui.update_ui(self.mock_api)
        req_tag = self.plugin._ui._t("group_dose_requirement")
        content_tag = self.plugin._ui._t("group_dose_content")
        self.assertTrue(dpg.is_item_shown(req_tag))
        self.assertFalse(dpg.is_item_shown(content_tag))

    def test_active_when_base_has_gy(self):
        self.mock_viewer.volume.unit = "Gy"
        is_active, target_vol, is_ov, unit = self.plugin._controller.get_dose_status()
        self.assertTrue(is_active)
        self.assertFalse(is_ov)
        self.assertEqual(target_vol, self.mock_viewer.volume)
        self.assertEqual(unit, "Gy")

        self.plugin._ui.update_ui(self.mock_api)
        req_tag = self.plugin._ui._t("group_dose_requirement")
        content_tag = self.plugin._ui._t("group_dose_content")
        self.assertFalse(dpg.is_item_shown(req_tag))
        self.assertTrue(dpg.is_item_shown(content_tag))

    def test_enable_button_assigns_gy_to_base(self):
        self.mock_viewer.volume.unit = "HU"
        self.assertFalse(self.plugin._controller.get_dose_status()[0])

        self.plugin._controller.on_enable_clicked(None, None, None)
        self.assertEqual(self.mock_viewer.volume.unit, "Gy")
        self.mock_api.request_refresh.assert_called_once()

        is_active, target_vol, is_ov, unit = self.plugin._controller.get_dose_status()
        self.assertTrue(is_active)
        self.assertEqual(unit, "Gy")

    def test_active_when_overlay_has_gy(self):
        # Base is HU, overlay is Gy
        self.mock_viewer.volume.unit = "HU"
        self.mock_overlay.unit = "Gy"

        self.mock_viewer.view_state.display.overlay = MagicMock()
        self.mock_viewer.view_state.display.overlay.image_id = "img_2"

        is_active, target_vol, is_ov, unit = self.plugin._controller.get_dose_status()
        self.assertTrue(is_active)
        self.assertTrue(is_ov)
        self.assertEqual(target_vol, self.mock_overlay)
        self.assertEqual(unit, "Gy")

        self.plugin._ui.update_ui(self.mock_api)
        req_tag = self.plugin._ui._t("group_dose_requirement")
        content_tag = self.plugin._ui._t("group_dose_content")
        self.assertFalse(dpg.is_item_shown(req_tag))
        self.assertTrue(dpg.is_item_shown(content_tag))

    def test_enable_button_assigns_gy_to_overlay_if_present(self):
        self.mock_viewer.volume.unit = "HU"
        self.mock_overlay.unit = None
        self.mock_viewer.view_state.display.overlay = MagicMock()
        self.mock_viewer.view_state.display.overlay.image_id = "img_2"

        self.plugin._controller.on_enable_clicked(None, None, None)
        self.assertEqual(self.mock_overlay.unit, "Gy")
        self.assertEqual(self.mock_viewer.volume.unit, "HU")

        is_active, target_vol, is_ov, unit = self.plugin._controller.get_dose_status()
        self.assertTrue(is_active)
        self.assertTrue(is_ov)
        self.assertEqual(target_vol, self.mock_overlay)


if __name__ == "__main__":
    unittest.main()
