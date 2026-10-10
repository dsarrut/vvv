import unittest
from unittest.mock import MagicMock
import numpy as np
import dearpygui.dearpygui as dpg

from vvv.plugins.dose.plugin_dose import DosePlugin
from vvv.plugins.dose.control_dose import DoseSettings


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
        self.mock_viewer.volume.data = np.full((10, 10, 10), 20.0, dtype=np.float32)
        self.mock_viewer.volume.shape3d = (10, 10, 10)
        self.mock_viewer.volume.num_timepoints = 1
        self.mock_viewer.volume.is_rgb = False
        self.mock_viewer.volume.get_data_range.return_value = (0.0, 60.0)

        self.mock_overlay = MagicMock()
        self.mock_overlay.name = "dose.nii.gz"
        self.mock_overlay.unit = None
        self.mock_overlay.data = np.full((10, 10, 10), 30.0, dtype=np.float32)
        self.mock_overlay.shape3d = (10, 10, 10)
        self.mock_overlay.num_timepoints = 1
        self.mock_overlay.is_rgb = False
        self.mock_overlay.get_data_range.return_value = (0.0, 50.0)

        self.mock_viewer.view_state.display.overlay = None
        self.mock_viewer.view_state.display.ww = 1.0
        self.mock_viewer.view_state.display.wl = 0.5
        self.mock_viewer.view_state.display.min_threshold = None
        self.mock_viewer.view_state.display.colormap = "Grayscale"
        self.mock_viewer.view_state.rois = {}

        self.mock_overlay_vs = MagicMock()
        self.mock_overlay_vs.display.ww = 1.0
        self.mock_overlay_vs.display.wl = 0.5
        self.mock_overlay_vs.display.min_threshold = None
        self.mock_overlay_vs.display.colormap = "Grayscale"

        self.mock_api.get_active_viewer.return_value = self.mock_viewer
        self.mock_api.get_volumes.return_value = {
            "img_1": self.mock_viewer.volume,
            "img_2": self.mock_overlay,
        }
        self.mock_api.get_view_states.return_value = {
            "img_1": self.mock_viewer.view_state,
            "img_2": self.mock_overlay_vs,
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

    # -------------------------------------------------------------
    # STEP 2 TESTS
    # -------------------------------------------------------------
    def test_dose_scaling_factor(self):
        self.mock_viewer.volume.unit = "Gy"
        settings = self.plugin._controller.get_settings("img_1")
        self.assertEqual(settings.scaling_factor, 1.0)

        # Base range is (0.0, 60.0)
        d_min, d_max = self.plugin._controller.get_scaled_dose_range(self.mock_viewer.volume, settings.scaling_factor)
        self.assertEqual(d_min, 0.0)
        self.assertEqual(d_max, 60.0)

        # Change scaling factor to 2.5
        settings.scaling_factor = 2.5
        d_min, d_max = self.plugin._controller.get_scaled_dose_range(self.mock_viewer.volume, settings.scaling_factor)
        self.assertEqual(d_min, 0.0)
        self.assertEqual(d_max, 150.0)

        # UI update shows scaled values
        self.plugin._ui.update_ui(self.mock_api)
        self.assertIn("150", dpg.get_value(self.plugin._ui._t("text_dose_max")))

    def test_bake_scaling_factor(self):
        self.mock_viewer.volume.unit = "Gy"
        self.mock_viewer.volume.data = np.full((4, 4, 4), 10.0, dtype=np.float32)
        self.mock_viewer.view_state.display.ww = 20.0
        self.mock_viewer.view_state.display.wl = 10.0

        settings = self.plugin._controller.get_settings("img_1")
        settings.scaling_factor = 3.0

        self.plugin._controller.bake_scaling_factor()
        self.assertTrue(np.allclose(self.mock_viewer.volume.data, 30.0))
        self.assertEqual(settings.scaling_factor, 1.0)
        self.assertEqual(self.mock_viewer.view_state.display.ww, 60.0)
        self.assertEqual(self.mock_viewer.view_state.display.wl, 30.0)

    def test_normalization_modes(self):
        self.mock_viewer.volume.unit = "Gy"
        settings = self.plugin._controller.get_settings("img_1")

        # 1. Absolute Dose -> reference defaults to d_max (60.0)
        settings.norm_mode = "Absolute Dose"
        ref = self.plugin._controller.get_reference_dose(self.mock_viewer.volume, False, settings)
        self.assertEqual(ref, 60.0)

        # 2. % to Max -> reference is 60.0
        settings.norm_mode = "% to Max"
        ref = self.plugin._controller.get_reference_dose(self.mock_viewer.volume, False, settings)
        self.assertEqual(ref, 60.0)

        # 3. % to Prescription -> reference is rx_dose
        settings.norm_mode = "% to Prescription"
        settings.rx_dose = 45.0
        ref = self.plugin._controller.get_reference_dose(self.mock_viewer.volume, False, settings)
        self.assertEqual(ref, 45.0)

        # 4. % to ROI Mean
        mock_roi_vol = MagicMock()
        mock_roi_vol.data = np.ones((10, 10, 10), dtype=np.uint8)
        self.mock_viewer.volume.data = np.full((10, 10, 10), 40.0, dtype=np.float32)
        self.mock_api.get_volumes.return_value["roi_ptv"] = mock_roi_vol

        settings.norm_mode = "% to ROI Mean"
        settings.norm_roi_id = "roi_ptv"
        ref = self.plugin._controller.get_reference_dose(self.mock_viewer.volume, False, settings)
        self.assertEqual(ref, 40.0)

    def test_window_level_presets(self):
        self.mock_viewer.volume.unit = "Gy"
        settings = self.plugin._controller.get_settings("img_1")
        settings.norm_mode = "% to Prescription"
        settings.rx_dose = 50.0
        settings.scaling_factor = 1.0

        # [0 - 100%]
        self.plugin._controller.apply_display_window("rx_100")
        self.assertEqual(self.mock_viewer.view_state.display.ww, 50.0)
        self.assertEqual(self.mock_viewer.view_state.display.wl, 25.0)

        # [0 - 107%]
        self.plugin._controller.apply_display_window("rx_107")
        self.assertAlmostEqual(self.mock_viewer.view_state.display.ww, 53.5)
        self.assertAlmostEqual(self.mock_viewer.view_state.display.wl, 26.75)

        # [Full Range] -> (0, 60)
        self.plugin._controller.apply_display_window("full_range")
        self.assertEqual(self.mock_viewer.view_state.display.ww, 60.0)
        self.assertEqual(self.mock_viewer.view_state.display.wl, 30.0)

    def test_background_threshold_toggle(self):
        self.mock_viewer.volume.unit = "Gy"
        settings = self.plugin._controller.get_settings("img_1")
        settings.norm_mode = "% to Prescription"
        settings.rx_dose = 50.0
        settings.scaling_factor = 1.0

        self.plugin._controller.set_background_threshold(True, pct=0.05)
        self.assertEqual(self.mock_viewer.view_state.display.min_threshold, 2.5)
        self.assertTrue(settings.threshold_5pct)

        self.plugin._controller.set_background_threshold(False)
        self.assertIsNone(self.mock_viewer.view_state.display.min_threshold)
        self.assertFalse(settings.threshold_5pct)

    def test_crosshair_dose_sampling(self):
        self.mock_viewer.volume.unit = "Gy"
        settings = self.plugin._controller.get_settings("img_1")
        settings.norm_mode = "% to Prescription"
        settings.rx_dose = 50.0

        self.mock_viewer.view_state.camera.crosshair_phys_coord = np.array([10.0, 20.0, 30.0])
        self.mock_viewer.view_state.world_to_display.return_value = np.array([4.0, 5.0, 6.0])
        self.mock_viewer.view_state._read_voxel_value.return_value = 25.0

        pt_dose, pt_pct = self.plugin._controller.get_crosshair_dose_sample()
        self.assertEqual(pt_dose, 25.0)
        self.assertEqual(pt_pct, 50.0)

    def test_serialization_and_restore(self):
        settings = self.plugin._controller.get_settings("img_1")
        settings.scaling_factor = 1.75
        settings.norm_mode = "% to Prescription"
        settings.rx_dose = 66.0
        settings.norm_roi_id = "roi_target"
        settings.threshold_5pct = True

        state_dict = self.plugin.serialize_image_state("img_1")
        self.assertEqual(state_dict["scaling_factor"], 1.75)
        self.assertEqual(state_dict["norm_mode"], "% to Prescription")
        self.assertEqual(state_dict["rx_dose"], 66.0)
        self.assertEqual(state_dict["norm_roi_id"], "roi_target")
        self.assertTrue(state_dict["threshold_5pct"])

        # Create fresh plugin and restore
        plugin2 = DosePlugin()
        plugin2.restore_image_state("img_1", state_dict)
        restored = plugin2._controller.get_settings("img_1")
        self.assertEqual(restored.scaling_factor, 1.75)
        self.assertEqual(restored.norm_mode, "% to Prescription")
        self.assertEqual(restored.rx_dose, 66.0)
        self.assertEqual(restored.norm_roi_id, "roi_target")
        self.assertTrue(restored.threshold_5pct)


if __name__ == "__main__":
    unittest.main()
