import unittest
from unittest.mock import MagicMock, patch
import numpy as np
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
        self.mock_viewer.volume.data = np.full((10, 10, 10), 20.0, dtype=np.float32)
        self.mock_viewer.volume.shape3d = (10, 10, 10)
        self.mock_viewer.volume.num_timepoints = 1
        self.mock_viewer.volume.is_rgb = False
        self.mock_viewer.volume._cumulative_scale = 1.0
        self.mock_viewer.volume.get_data_range.return_value = (0.0, 60.0)

        self.mock_overlay = MagicMock()
        self.mock_overlay.name = "dose.nii.gz"
        self.mock_overlay.unit = None
        self.mock_overlay.data = np.full((10, 10, 10), 30.0, dtype=np.float32)
        self.mock_overlay.shape3d = (10, 10, 10)
        self.mock_overlay.num_timepoints = 1
        self.mock_overlay.is_rgb = False
        self.mock_overlay._cumulative_scale = 1.0
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
    # COMPONENT TESTS: Scaling & Normalization
    # -------------------------------------------------------------
    def test_scaling_component_manual(self):
        self.mock_viewer.volume.unit = "Gy"
        comp = self.plugin._ui.scaling_comp
        state = comp.get_state("img_1")
        self.assertEqual(state.scaling_factor, 1.0)
        self.assertIsNone(state.norm_mode)

        # Set scale factor to 2.5
        comp._set_scale_factor(2.5)
        self.assertEqual(state.scaling_factor, 2.5)
        self.assertEqual(self.mock_viewer.volume.scale_factor, 2.5)

        comp.update_ui(self.mock_api)
        self.assertIn("150", dpg.get_value(comp._t("text_range")))

    def test_scaling_component_norm_to_max(self):
        self.mock_viewer.volume.unit = "Gy"
        comp = self.plugin._ui.scaling_comp
        state = comp.get_state("img_1")

        # Click Max normalization (100%)
        comp._on_norm_max_clicked()
        self.assertEqual(state.norm_mode, "Max")
        # Max is 60.0 -> Auto S = 100 / 60 = 1.6666...
        self.assertAlmostEqual(state.scaling_factor, 100.0 / 60.0)
        self.assertEqual(self.mock_viewer.volume.scale_unit, "%")

    def test_scaling_component_norm_to_value(self):
        self.mock_viewer.volume.unit = "Gy"
        comp = self.plugin._ui.scaling_comp
        state = comp.get_state("img_1")

        comp._on_norm_val_clicked()
        comp._on_norm_val_changed(None, 50.0, None)

        self.assertIn(state.norm_mode, ("Ref Value", "Target Value", "Prescription"))
        self.assertEqual(state.norm_target_value, 50.0)
        # Prescription works independently with user scale factor:
        self.assertEqual(state.scaling_factor, 1.0)
        self.assertEqual(self.mock_viewer.volume.scale_factor, 2.0)
        self.assertEqual(self.mock_viewer.volume.scale_unit, "%")

        # Changing user scale factor while in Prescription mode preserves Prescription mode:
        comp._on_scale_factor_changed(None, 0.5, None)
        self.assertEqual(state.norm_mode, "Ref Value")
        self.assertEqual(state.scaling_factor, 0.5)
        # S_eff = 0.5 * 100 / 50 = 1.0
        self.assertEqual(self.mock_viewer.volume.scale_factor, 1.0)

        # Clicking None returns to Absolute dose without forgetting prescription value:
        comp._on_norm_none_clicked()
        self.assertIsNone(state.norm_mode)
        self.assertEqual(state.norm_target_value, 50.0)
        self.assertEqual(self.mock_viewer.volume.scale_factor, 0.5)
        self.assertIsNone(self.mock_viewer.volume.scale_unit)

    def test_scaling_component_norm_to_roi_mean(self):
        self.mock_viewer.volume.unit = "Gy"
        mock_roi = MagicMock()
        mock_roi.data = np.ones((10, 10, 10), dtype=np.uint8)
        self.mock_viewer.volume.data = np.full((10, 10, 10), 25.0, dtype=np.float32)
        self.mock_api.get_volumes.return_value["roi_1"] = mock_roi

        comp = self.plugin._ui.scaling_comp
        state = comp.get_state("img_1")

        comp._on_norm_roi_clicked()
        comp._on_norm_roi_changed(None, "PTV (roi_1)", None)

        self.assertEqual(state.norm_mode, "ROI Mean")
        self.assertEqual(state.norm_roi_id, "roi_1")
        # ROI Mean is 25.0 -> S = 100 / 25 = 4.0
        self.assertEqual(state.scaling_factor, 4.0)

    @patch("dearpygui.dearpygui.configure_item")
    @patch("dearpygui.dearpygui.does_item_exist", return_value=True)
    def test_scaling_component_roi_mean_disabled_when_no_rois(self, mock_exist, mock_config):
        self.mock_viewer.volume.unit = "Gy"
        comp = self.plugin._ui.scaling_comp

        # No ROIs loaded
        self.mock_api.get_volumes.return_value = {}
        self.mock_viewer.view_state.rois = {}
        comp.update_ui(self.mock_api)
        mock_config.assert_any_call(comp._t("btn_norm_roi"), enabled=False)

        # With ROI loaded
        mock_config.reset_mock()
        self.mock_viewer.view_state.rois = {"roi_1": MagicMock()}
        comp.update_ui(self.mock_api)
        mock_config.assert_any_call(comp._t("btn_norm_roi"), enabled=True)

    def test_scaling_component_manual_edit_disables_norm(self):
        self.mock_viewer.volume.unit = "Gy"
        comp = self.plugin._ui.scaling_comp
        state = comp.get_state("img_1")

        # First normalize to max
        comp._on_norm_max_clicked()
        self.assertEqual(state.norm_mode, "Max")

        # Manually changing scale factor disables active normalization mode
        comp._on_scale_factor_changed(None, 2.0, None)
        self.assertIsNone(state.norm_mode)
        self.assertEqual(state.scaling_factor, 2.0)
        self.assertIsNone(self.mock_viewer.volume.scale_unit)

    def test_scaling_component_bake_and_reset(self):
        self.mock_viewer.volume.unit = "Gy"
        self.mock_viewer.volume.data = np.full((4, 4, 4), 10.0, dtype=np.float32)
        self.mock_viewer.view_state.display.ww = 20.0
        self.mock_viewer.view_state.display.wl = 10.0

        comp = self.plugin._ui.scaling_comp
        comp._set_scale_factor(3.0)

        # Bake (applies to array)
        comp._on_bake_clicked()
        self.assertTrue(np.allclose(self.mock_viewer.volume.data, 30.0))
        self.assertEqual(getattr(self.mock_viewer.volume, "_cumulative_scale", 1.0), 3.0)
        self.assertEqual(self.mock_viewer.view_state.display.ww, 60.0)
        self.assertEqual(self.mock_viewer.view_state.display.wl, 30.0)
        self.assertEqual(comp.get_state("img_1").scaling_factor, 1.0)

        # Reset (reverts array)
        comp._on_reset_clicked()
        self.assertTrue(np.allclose(self.mock_viewer.volume.data, 10.0))
        self.assertEqual(getattr(self.mock_viewer.volume, "_cumulative_scale", 1.0), 1.0)
        self.assertEqual(self.mock_viewer.view_state.display.ww, 20.0)
        self.assertEqual(self.mock_viewer.view_state.display.wl, 10.0)

    # -------------------------------------------------------------
    # Clinical Presets & Sampling Tests
    # -------------------------------------------------------------
    def test_window_level_presets(self):
        self.mock_viewer.volume.unit = "Gy"
        # [0 - 100%] -> [0, 60.0]
        self.plugin._controller.apply_display_window("rx_100")
        self.assertEqual(self.mock_viewer.view_state.display.ww, 60.0)
        self.assertEqual(self.mock_viewer.view_state.display.wl, 30.0)

        # [0 - 107%] -> [0, 64.2]
        self.plugin._controller.apply_display_window("rx_107")
        self.assertAlmostEqual(self.mock_viewer.view_state.display.ww, 64.2)
        self.assertAlmostEqual(self.mock_viewer.view_state.display.wl, 32.1)

        # [Full Range] -> [0, 60]
        self.plugin._controller.apply_display_window("full_range")
        self.assertEqual(self.mock_viewer.view_state.display.ww, 60.0)
        self.assertEqual(self.mock_viewer.view_state.display.wl, 30.0)

    def test_background_threshold_toggle(self):
        self.mock_viewer.volume.unit = "Gy"
        self.plugin._controller.set_background_threshold(True, pct=0.05)
        # 5% of 60.0 = 3.0
        self.assertEqual(self.mock_viewer.view_state.display.min_threshold, 3.0)
        self.assertTrue(self.plugin._controller._threshold_5pct)

        self.plugin._controller.set_background_threshold(False)
        self.assertIsNone(self.mock_viewer.view_state.display.min_threshold)
        self.assertFalse(self.plugin._controller._threshold_5pct)

    def test_crosshair_dose_sampling(self):
        self.mock_viewer.volume.unit = "Gy"
        self.mock_viewer.view_state.camera.crosshair_phys_coord = np.array([10.0, 20.0, 30.0])
        self.mock_viewer.view_state.world_to_display.return_value = np.array([4.0, 5.0, 6.0])
        self.mock_viewer.view_state._read_voxel_value.return_value = 30.0

        val, pct = self.plugin._controller.get_crosshair_dose_sample()
        self.assertEqual(val, 30.0)
        self.assertEqual(pct, 50.0)  # 30 / 60 * 100 = 50%


if __name__ == "__main__":
    unittest.main()
