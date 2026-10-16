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

        self.mock_viewer.view_state.base_display_data = None
        self.mock_viewer.view_state.camera.time_idx = 0
        self.mock_viewer.view_state.display.overlay = None
        self.mock_viewer.view_state.display.ww = 1.0
        self.mock_viewer.view_state.display.wl = 0.5
        self.mock_viewer.view_state.display.min_threshold = None
        self.mock_viewer.view_state.display.colormap = "Grayscale"
        self.mock_viewer.view_state.rois = {}

        self.mock_overlay_vs = MagicMock()
        self.mock_overlay_vs.base_display_data = None
        self.mock_overlay_vs.camera.time_idx = 0
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

    def test_scaling_component_updates_legend(self):
        self.mock_viewer.volume.unit = "Gy"
        self.mock_viewer.show_legend = True
        comp = self.plugin._ui.scaling_comp

        # Trigger normalization to max
        comp._on_norm_max_clicked()

        self.assertTrue(self.mock_viewer.is_geometry_dirty)
        self.assertIsNone(self.mock_viewer.drawer._last_leg_state)
        self.mock_viewer.drawer.draw_legend.assert_called()
        self.mock_api.request_refresh.assert_called()

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
        # Display window/level updated to [0, max]
        self.assertEqual(self.mock_viewer.view_state.display.ww, 60.0)
        self.assertEqual(self.mock_viewer.view_state.display.wl, 30.0)
        # Scaled max: (30 + 30) * (100/60) = 100.0
        scaled_max = (
            self.mock_viewer.view_state.display.wl
            + self.mock_viewer.view_state.display.ww / 2.0
        ) * self.mock_viewer.volume.scale_factor
        self.assertAlmostEqual(scaled_max, 100.0)

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
        # Display window/level updated to [0, ref] (ref=50)
        self.assertEqual(self.mock_viewer.view_state.display.ww, 50.0)
        self.assertEqual(self.mock_viewer.view_state.display.wl, 25.0)
        # Scaled max: (25 + 25) * 2.0 = 100.0
        scaled_max = (
            self.mock_viewer.view_state.display.wl
            + self.mock_viewer.view_state.display.ww / 2.0
        ) * self.mock_viewer.volume.scale_factor
        self.assertAlmostEqual(scaled_max, 100.0)

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


    def test_go_to_max(self):
        self.mock_viewer.volume.unit = "Gy"
        data = np.zeros((10, 10, 10), dtype=np.float32)
        # Place maximum at z=3, y=4, x=5
        data[3, 4, 5] = 95.0
        self.mock_viewer.volume.data = data
        self.mock_viewer.volume.sitk_image = None
        self.mock_viewer.volume.voxel_coord_to_physic_coord.side_effect = (
            lambda vox: np.array([vox[0] * 2.0, vox[1] * 2.0, vox[2] * 2.0])
        )

        self.plugin._controller.go_to_max()

        expected_phys = np.array([10.0, 8.0, 6.0])  # x=5*2, y=4*2, z=3*2
        np.testing.assert_allclose(self.mock_viewer.view_state.camera.target_center, expected_phys)
        self.mock_viewer.view_state.update_crosshair_from_phys.assert_called()
        np.testing.assert_allclose(
            self.mock_viewer.view_state.update_crosshair_from_phys.call_args[0][0],
            expected_phys,
        )
        self.mock_api.propagate_sync.assert_called_with("img_1")
        self.mock_api.request_refresh.assert_called()

    def test_scaling_component_goto_max(self):
        self.mock_viewer.volume.unit = "Gy"
        data = np.zeros((8, 8, 8), dtype=np.float32)
        data[2, 3, 4] = 88.0
        self.mock_viewer.volume.data = data
        self.mock_viewer.volume.sitk_image = None
        self.mock_viewer.volume.voxel_coord_to_physic_coord.side_effect = (
            lambda vox: np.array([vox[0] * 1.5, vox[1] * 1.5, vox[2] * 1.5])
        )

        comp = self.plugin._ui.scaling_comp
        comp._on_goto_max_clicked()

        expected_phys = np.array([6.0, 4.5, 3.0])  # x=4*1.5, y=3*1.5, z=2*1.5
        np.testing.assert_allclose(self.mock_viewer.view_state.camera.target_center, expected_phys)
        self.mock_viewer.view_state.update_crosshair_from_phys.assert_called()
        np.testing.assert_allclose(
            self.mock_viewer.view_state.update_crosshair_from_phys.call_args[0][0],
            expected_phys,
        )

    @patch("dearpygui.dearpygui.bind_item_font")
    @patch("dearpygui.dearpygui.does_item_exist", return_value=True)
    def test_goto_max_icon_font_bound(self, mock_exist, mock_bind_font):
        comp = self.plugin._ui.scaling_comp
        comp._bind_icon_font("test_btn")
        mock_bind_font.assert_called_with("test_btn", "icon_font_tag")

    # -------------------------------------------------------------
    # ISOCONTOUR TESTS
    # -------------------------------------------------------------
    def test_isocontour_default_state(self):
        self.mock_viewer.volume.unit = "Gy"
        state = self.plugin._controller.get_isocontour_state("img_1")
        self.assertTrue(state.is_enabled)
        self.assertTrue(state.subpixel_accurate)
        self.assertEqual(len(state.levels), 8)
        self.assertEqual(state.levels[0].value, 107.0)
        self.assertEqual(state.levels[1].value, 100.0)

    def test_isocontour_update_and_extract(self):
        self.mock_viewer.volume.unit = "Gy"
        # 10x10x10 slice with dose peak in center (30 Gy max)
        data = np.zeros((10, 10, 10), dtype=np.float32)
        data[5, 4:7, 4:7] = 30.0
        self.mock_viewer.volume.data = data
        self.mock_viewer.volume.get_data_range.return_value = (0.0, 30.0)
        self.mock_viewer.slice_idx = 5
        from vvv.utils import ViewMode
        self.mock_viewer.orientation = ViewMode.AXIAL
        self.mock_viewer.volume.get_physical_aspect_ratio.return_value = (1.0, 1.0)
        self.mock_viewer.view_state.contours = {}

        def mock_add(img_id, c_roi):
            c_id = f"c_{len(self.mock_viewer.view_state.contours)}"
            c_roi.id = c_id
            self.mock_viewer.view_state.contours[c_id] = c_roi
            return c_id

        self.mock_api.add_contour.side_effect = mock_add

        # Normalize to Max (Max = 30 Gy = 100%)
        comp = self.plugin._ui.scaling_comp
        comp._on_norm_max_clicked()

        # Update isocontours
        self.plugin._controller.update_isocontours(self.mock_viewer)

        # Contours should be created in contours dict
        self.assertGreater(len(self.mock_viewer.view_state.contours), 0)

        # Check 100% and 50% levels
        rois = list(self.mock_viewer.view_state.contours.values())
        dose_rois = [r for r in rois if getattr(r, "is_dose_isocontour", False)]
        self.assertEqual(len(dose_rois), 8)

        # Test extraction even before normalizing (unnormalized mode uses raw max as 100% reference)
        lvl_100_roi = next(r for r in dose_rois if "100" in r.name)
        self.assertIn(5, lvl_100_roi.polygons[ViewMode.AXIAL])
        self.assertGreater(len(lvl_100_roi.polygons[ViewMode.AXIAL][5]), 0)

        # For level 50% (threshold = 15 Gy), polygons should be present on slice 5
        lvl_50_roi = next(r for r in dose_rois if "50" in r.name)
        self.assertIn(5, lvl_50_roi.polygons[ViewMode.AXIAL])
        self.assertGreater(len(lvl_50_roi.polygons[ViewMode.AXIAL][5]), 0)

    def test_isocontour_overlay_extract(self):
        # Base CT image
        self.mock_viewer.image_id = "img_ct"
        self.mock_viewer.volume.unit = "HU"
        self.mock_viewer.slice_idx = 5
        from vvv.utils import ViewMode
        self.mock_viewer.orientation = ViewMode.AXIAL
        self.mock_viewer.volume.get_physical_aspect_ratio.return_value = (1.0, 1.0)
        self.mock_viewer.view_state.contours = {}

        # Dose overlay
        data = np.zeros((10, 10, 10), dtype=np.float32)
        data[5, 4:7, 4:7] = 20.0
        self.mock_overlay.unit = "Gy"
        self.mock_overlay.data = data
        self.mock_overlay.get_data_range.return_value = (0.0, 20.0)
        self.mock_viewer.view_state.display.overlay = MagicMock()
        self.mock_viewer.view_state.display.overlay.image_id = "img_2"
        self.mock_viewer.view_state.display.overlay_data = data
        self.mock_overlay_vs.contours = {}

        def mock_add(img_id, c_roi):
            c_id = f"c_{len(self.mock_overlay_vs.contours)}"
            c_roi.id = c_id
            self.mock_overlay_vs.contours[c_id] = c_roi
            return c_id

        self.mock_api.add_contour.side_effect = mock_add

        # Update isocontours for overlay
        self.plugin._controller.update_isocontours(self.mock_viewer)

        # Contours should be created in overlay's contours dict
        self.assertEqual(len(self.mock_overlay_vs.contours), 8)
        rois = list(self.mock_overlay_vs.contours.values())
        lvl_50 = next(r for r in rois if "50" in r.name)
        self.assertIn(5, lvl_50.polygons[ViewMode.AXIAL])
        self.assertGreater(len(lvl_50.polygons[ViewMode.AXIAL][5]), 0)

    def test_isocontour_level_callbacks(self):
        self.mock_viewer.volume.unit = "Gy"
        controller = self.plugin._controller

        # Toggle subpixel
        controller.on_toggle_subpixel(None, False, None)
        state = controller.get_isocontour_state("img_1")
        self.assertFalse(state.subpixel_accurate)

        # Toggle a level
        controller.on_level_enabled_toggle(None, False, 0)
        self.assertFalse(state.levels[0].enabled)

        # Edit level value
        controller.on_level_value_changed(None, 65.0, 0)
        self.assertEqual(state.levels[0].value, 65.0)

        # Change color
        controller.on_level_color_changed(None, [10, 20, 30, 255], 0)
        self.assertEqual(state.levels[0].color, [10, 20, 30, 255])

        # Delete level
        initial_len = len(state.levels)
        controller.on_delete_level_clicked(None, None, 0)
        self.assertEqual(len(state.levels), initial_len - 1)

        # Reset levels
        controller.on_reset_levels_clicked()
        self.assertEqual(len(state.levels), 8)
        self.assertEqual(state.levels[0].value, 107.0)

    def test_isocontour_serialization_and_restore(self):
        controller = self.plugin._controller
        state = controller.get_isocontour_state("img_1")
        state.levels[0].value = 110.0
        state.subpixel_accurate = False

        data = controller.serialize_image_state("img_1")
        self.assertIn("levels", data)
        self.assertFalse(data["subpixel_accurate"])
        self.assertEqual(data["levels"][0]["value"], 110.0)

        # Restore into another image
        controller.restore_image_state("img_restore", data)
        restored = controller.get_isocontour_state("img_restore")
        self.assertFalse(restored.subpixel_accurate)
        self.assertEqual(restored.levels[0].value, 110.0)

    def test_monte_carlo_low_magnitude_thresholds(self):
        from vvv.plugins.dose.control_dose import DoseIsocontourLevel
        controller = self.plugin._controller
        # Create a mock volume with small magnitude values (e.g. Monte Carlo dose 6.7e-8 Gy/particle)
        vol = MagicMock()
        vol.get_data_range.return_value = (0.0, 6.746e-8)
        vol.unit = "Gy"

        # Check 10%, 50%, 100% levels
        lvl_10 = DoseIsocontourLevel(10.0, [255, 0, 0, 255])
        thr_10 = controller.compute_raw_threshold_for_level(lvl_10, vol, False, "test_mc")
        self.assertAlmostEqual(thr_10, 0.10 * 6.746e-8, delta=1e-12)

        lvl_50 = DoseIsocontourLevel(50.0, [255, 0, 0, 255])
        thr_50 = controller.compute_raw_threshold_for_level(lvl_50, vol, False, "test_mc")
        self.assertAlmostEqual(thr_50, 0.50 * 6.746e-8, delta=1e-12)

        lvl_100 = DoseIsocontourLevel(100.0, [255, 0, 0, 255])
        thr_100 = controller.compute_raw_threshold_for_level(lvl_100, vol, False, "test_mc")
        # 100% should be nudged slightly (0.999 * max)
        self.assertAlmostEqual(thr_100, 6.746e-8 * 0.999, delta=1e-12)

    def test_dose_filename_heuristic_unit(self):
        from vvv.maths.image import VolumeData
        vol = VolumeData("data/output_dose.mhd")
        self.assertEqual(vol.unit, "Gy")
        self.assertIn("Filename", vol.unit_source)

    def test_update_isocontours_data_token_invalidation(self):
        controller = self.plugin._controller
        self.mock_viewer.image_id = "img_1"
        self.mock_viewer.slice_idx = 2
        from vvv.utils import ViewMode
        self.mock_viewer.orientation = ViewMode.AXIAL
        self.mock_viewer.volume.get_physical_aspect_ratio.return_value = (1.0, 1.0)

        # Initial overlay data
        data1 = np.zeros((5, 5, 5), dtype=np.float32)
        data1[2, 2, 2] = 10.0
        self.mock_overlay.data = data1
        self.mock_overlay.unit = "Gy"
        self.mock_overlay.get_data_range.return_value = (0.0, 10.0)
        self.mock_viewer.view_state.display.overlay = MagicMock()
        self.mock_viewer.view_state.display.overlay.image_id = "img_2"
        self.mock_viewer.view_state.display.overlay_data = data1
        self.mock_overlay_vs.contours = {}

        def mock_add(img_id, c_roi):
            c_id = f"c_{len(self.mock_overlay_vs.contours)}"
            c_roi.id = c_id
            self.mock_overlay_vs.contours[c_id] = c_roi
            return c_id
        self.mock_api.add_contour.side_effect = mock_add

        controller.update_isocontours(self.mock_viewer)
        c_roi = self.mock_overlay_vs.contours["c_0"]
        self.assertEqual(c_roi.last_computed_data_token, id(data1))

        # Now simulate background resample finishing and replacing overlay_data with data2
        data2 = np.zeros((5, 5, 5), dtype=np.float32)
        data2[2, 1:4, 1:4] = 10.0
        self.mock_viewer.view_state.display.overlay_data = data2
        controller.update_isocontours(self.mock_viewer)
        self.assertEqual(c_roi.last_computed_data_token, id(data2))

    def test_dose_threshold_toggle_and_change(self):
        self.mock_viewer.volume.unit = "Gy"
        controller = self.plugin._controller

        # Initial state: None
        self.assertIsNone(self.mock_viewer.view_state.display.min_threshold)

        # Toggle ON
        controller.on_dose_threshold_toggle(None, True, None)
        self.assertEqual(self.mock_viewer.view_state.display.min_threshold, 0.0)
        self.assertTrue(self.mock_viewer.view_state.is_data_dirty)
        self.mock_api.request_refresh.assert_called()

        # Change threshold value
        controller.on_dose_threshold_changed(None, 5.5, None)
        self.assertEqual(self.mock_viewer.view_state.display.min_threshold, 5.5)

        # Step button clicked (+ direction)
        with patch("dearpygui.dearpygui.does_item_exist", return_value=True), \
             patch("dearpygui.dearpygui.get_value", return_value=5.5):
            controller.on_step_button_clicked(None, None, {"tag": controller._t("drag_dose_threshold"), "dir": 1.0})
            self.assertGreater(self.mock_viewer.view_state.display.min_threshold, 5.5)

        # Toggle OFF
        controller.on_dose_threshold_toggle(None, False, None)
        self.assertIsNone(self.mock_viewer.view_state.display.min_threshold)

    def test_dicom_rtdose_scaling(self):
        import SimpleITK as sitk
        from vvv.maths.image import VolumeData

        # Create a synthetic 3D image with DoseGridScaling tag
        img = sitk.Image([4, 4, 4], sitk.sitkUInt16)
        img.SetSpacing([1.0, 1.0, 1.0])
        img.SetOrigin([0.0, 0.0, 0.0])
        img = sitk.Add(img, 1000)
        img.SetMetaData("3004|000e", "0.001114921")

        scaled_img = VolumeData._apply_dicom_dose_scaling(img)
        self.assertEqual(scaled_img.GetPixelID(), sitk.sitkFloat32)
        arr = sitk.GetArrayFromImage(scaled_img)
        np.testing.assert_allclose(arr, 1.114921, rtol=1e-5)

    def test_dose_colorwash_bands(self):
        self.mock_viewer.volume.unit = "Gy"
        self.mock_viewer.volume.get_data_range.return_value = (0.0, 70.0)
        controller = self.plugin._controller

        # Initial: colorwash is disabled
        bands = controller.get_colorwash_bands(self.mock_viewer.image_id)
        self.assertIsNone(bands)

        # Toggle shading ON
        controller.on_toggle_shading(None, True, None)
        bands = controller.get_colorwash_bands(self.mock_viewer.image_id, is_overlay=False)
        self.assertIsNotNone(bands)
        self.assertGreater(len(bands), 0)

        # Verify sorted in ascending order of threshold
        thrs = [b[0] for b in bands]
        self.assertEqual(thrs, sorted(thrs))

        # Check opacity: for base (is_overlay=False), op is colorwash_opacity (0.5)
        self.assertEqual(bands[0][1][3], 0.5)

        # For overlay (is_overlay=True), op is 1.0 (DPG GPU compositor handles overlay opacity)
        bands_ov = controller.get_colorwash_bands(self.mock_viewer.image_id, is_overlay=True)
        self.assertEqual(bands_ov[0][1][3], 1.0)

    def test_dose_shading_opacity_callback(self):
        self.mock_viewer.volume.unit = "Gy"
        controller = self.plugin._controller

        # When target is base image
        controller.on_shading_opacity_changed(None, 0.72, None)
        state = controller.get_isocontour_state(self.mock_viewer.image_id)
        self.assertEqual(state.colorwash_opacity, 0.72)

        # When target is overlay image
        self.mock_viewer.view_state.display.overlay = MagicMock(image_id="ov_dose_id", opacity=0.5)
        ov_vol = MagicMock(unit="Gy", is_roi=False)
        ov_vol.get_data_range.return_value = (0.0, 60.0)
        self.mock_api.get_volumes.return_value = {"ov_dose_id": ov_vol, self.mock_viewer.image_id: self.mock_viewer.volume}
        self.mock_api.get_view_states.return_value = {
            "ov_dose_id": MagicMock(display=MagicMock(overlay=None)),
            self.mock_viewer.image_id: self.mock_viewer.view_state,
        }

        controller.on_shading_opacity_changed(None, 0.85, None)
        self.assertEqual(self.mock_viewer.view_state.display.overlay.opacity, 0.85)
        self.mock_api.propagate_overlay_opacity.assert_called_with(self.mock_viewer.image_id)

    def test_dose_full_vvw_serialization_and_restore(self):
        controller = self.plugin._controller
        img_id = "dose_vvw_test"
        state = controller.get_isocontour_state(img_id)
        state.colorwash_enabled = True
        state.colorwash_opacity = 0.42
        state.levels[0].value = 115.0
        state.levels[1].enabled = False

        # Set scaling component state
        scaling_comp = self.plugin._ui.scaling_comp
        sc_state = scaling_comp.get_state(img_id)
        sc_state.scaling_factor = 2.5
        sc_state.norm_mode = "Prescription"
        sc_state.norm_target_value = 60.0

        # Serialize
        data = controller.serialize_image_state(img_id)
        self.assertTrue(data.get("colorwash_enabled"))
        self.assertEqual(data.get("colorwash_opacity"), 0.42)
        self.assertIn("scaling", data)
        self.assertEqual(data["scaling"]["scaling_factor"], 2.5)
        self.assertEqual(data["scaling"]["norm_mode"], "Prescription")
        self.assertEqual(data["scaling"]["norm_target_value"], 60.0)

        # Restore into another image
        target_vol = MagicMock(unit="Gy", scale_factor=1.0, scale_unit=None)
        target_vol.get_data_range.return_value = (0.0, 70.0)
        self.mock_api.get_volumes.return_value = {"dose_restored": target_vol}

        controller.restore_image_state("dose_restored", data)
        restored_state = controller.get_isocontour_state("dose_restored")
        self.assertTrue(restored_state.colorwash_enabled)
        self.assertEqual(restored_state.colorwash_opacity, 0.42)
        self.assertEqual(restored_state.levels[0].value, 115.0)
        self.assertFalse(restored_state.levels[1].enabled)

        # Check restored scaling state
        restored_sc = scaling_comp.get_state("dose_restored")
        self.assertEqual(restored_sc.scaling_factor, 2.5)
        self.assertEqual(restored_sc.norm_mode, "Prescription")
        self.assertEqual(restored_sc.norm_target_value, 60.0)

        # Check volume scale factor synced
        self.assertEqual(target_vol.scale_unit, "%")

    def test_slice_renderer_colorwash_colorize(self):
        from vvv.maths.image import SliceRenderer

        slice_data = np.array([
            [0.0, 15.0],
            [55.0, 100.0]
        ], dtype=np.float32)

        bands = [
            (10.0, [0.0, 0.0, 1.0, 0.5]),   # Blue >= 10
            (50.0, [1.0, 1.0, 0.0, 0.5]),   # Yellow >= 50
            (90.0, [1.0, 0.0, 0.0, 0.5]),   # Red >= 90
        ]

        rgba, norm = SliceRenderer._colorize_layer(
            slice_data=slice_data,
            is_rgb=False,
            num_components=1,
            ww=100.0,
            wl=50.0,
            cmap_name="Grayscale",
            threshold=None,
            colorwash=bands,
        )

        self.assertEqual(rgba.shape, (2, 2, 4))
        # (0, 0) is 0.0 (< 10): transparent
        np.testing.assert_allclose(rgba[0, 0], [0.0, 0.0, 0.0, 0.0])
        # (0, 1) is 15.0 (>= 10 and < 50): blue
        np.testing.assert_allclose(rgba[0, 1], [0.0, 0.0, 1.0, 0.5])
        # (1, 0) is 55.0 (>= 50 and < 90): yellow
        np.testing.assert_allclose(rgba[1, 0], [1.0, 1.0, 0.0, 0.5])
        # (1, 1) is 100.0 (>= 90): red
        np.testing.assert_allclose(rgba[1, 1], [1.0, 0.0, 0.0, 0.5])

        # Test with display threshold
        rgba_thr, _ = SliceRenderer._colorize_layer(
            slice_data=slice_data,
            is_rgb=False,
            num_components=1,
            ww=100.0,
            wl=50.0,
            cmap_name="Grayscale",
            threshold=20.0,
            colorwash=bands,
        )
        # (0, 1) has value 15.0 <= 20.0: should be masked to transparent
        np.testing.assert_allclose(rgba_thr[0, 1], [0.0, 0.0, 0.0, 0.0])
        # (1, 0) and (1, 1) are > 20.0: remain colored
        np.testing.assert_allclose(rgba_thr[1, 0], [1.0, 1.0, 0.0, 0.5])

    def test_dose_overlay_shading_toggles_and_refreshes(self):
        controller = self.plugin._controller
        controller.bind(self.mock_api)

        # Configure mock_viewer to have an overlay pointing to mock_overlay ("img_2")
        mock_ov_config = MagicMock()
        mock_ov_config.image_id = "img_2"
        mock_ov_config.opacity = 0.5
        self.mock_viewer.view_state.display.overlay = mock_ov_config
        self.mock_viewer.view_state.is_data_dirty = False
        self.mock_overlay.unit = "Gy"

        # Toggle shading ON
        controller.on_toggle_shading(app_data=True)
        state = controller.get_isocontour_state("img_2")
        self.assertTrue(state.colorwash_enabled)
        # Viewer was notified to refresh
        self.mock_api.request_refresh.assert_called()

        # Check colorwash bands generated for overlay
        bands = controller.get_colorwash_bands("img_2", is_overlay=True)
        self.assertIsNotNone(bands)
        self.assertGreater(len(bands), 0)
        # Overlay band colors should have alpha 1.0 (GPU/CPU compositing uses overlay.opacity)
        for thr, col in bands:
            self.assertEqual(col[3], 1.0)

        # Changing shading opacity updates overlay opacity on viewer view_state
        controller.on_shading_opacity_changed(app_data=0.75)
        self.assertEqual(mock_ov_config.opacity, 0.75)
        self.assertEqual(state.colorwash_opacity, 0.75)

    def test_compute_native_voxel_overlay_with_colorwash(self):
        from vvv.ui.render_strategy import compute_native_voxel_overlay
        from vvv.maths.image import ViewMode

        # Create mock viewer and mock overlay volume
        mock_v = MagicMock()
        mock_v.orientation = ViewMode.AXIAL
        mock_v.slice_idx = 0
        mock_v.get_slice_shape.return_value = (2, 2)
        mock_v.current_pmin = [0.0, 0.0]
        mock_v.current_pmax = [2.0, 2.0]

        # Base volume
        base_vol = MagicMock()
        base_vol.origin = np.zeros(3)
        base_vol.spacing = np.ones(3)
        base_vol.matrix = np.eye(3)
        base_vol.inverse_matrix = np.eye(3)
        mock_v.volume = base_vol

        # Overlay volume with 3D dose data: [0, 15, 55, 100]
        ov_vol = MagicMock()
        ov_vol.origin = np.zeros(3)
        ov_vol.spacing = np.ones(3)
        ov_vol.matrix = np.eye(3)
        ov_vol.inverse_matrix = np.eye(3)
        ov_vol.num_timepoints = 1
        data = np.array([[[0.0, 15.0], [55.0, 100.0]]], dtype=np.float32)  # (1, 2, 2)
        ov_vol.data = data
        ov_vol.shape3d = (1, 2, 2)

        # View states
        base_vs = MagicMock()
        base_vs.camera.time_idx = 0
        base_vs.space.transform = None
        base_vs.space.is_active = False
        base_vs.display.overlay.image_id = "ov_dose"
        mock_v.view_state = base_vs

        ov_vs = MagicMock()
        ov_vs.space.transform = None
        ov_vs.space.is_active = False
        ov_vs.display.colormap = "Grayscale"
        ov_vs.display.min_threshold = None
        ov_vs.display.wl = 50.0
        ov_vs.display.ww = 100.0

        mock_v.controller.view_states = {"ov_dose": ov_vs}
        mock_v.controller.volumes = {"ov_dose": ov_vol}
        mock_v.controller.settings.data = {"rendering": {"numba": False}}

        bands = [
            (10.0, [0.0, 0.0, 1.0, 1.0]),  # Blue >= 10
            (50.0, [1.0, 1.0, 0.0, 1.0]),  # Yellow >= 50
            (90.0, [1.0, 0.0, 0.0, 1.0]),  # Red >= 90
        ]

        # 1. Dual-texture mode (target_buffer=None): returns RGBA flat array
        res = compute_native_voxel_overlay(
            mock_v,
            pmin=[0.0, 0.0],
            pmax=[2.0, 2.0],
            canvas_w=2,
            canvas_h=2,
            target_buffer=None,
            opacity=1.0,
            colorwash=bands,
        )
        self.assertIsNotNone(res)
        res_2d = res.reshape(2, 2, 4)
        # Voxel (0, 0) is 0.0 (< 10): transparent
        np.testing.assert_allclose(res_2d[0, 0], [0.0, 0.0, 0.0, 0.0])
        # Voxel (0, 1) is 15.0 (>= 10 and < 50): Blue
        np.testing.assert_allclose(res_2d[0, 1], [0.0, 0.0, 1.0, 1.0])
        # Voxel (1, 0) is 55.0 (>= 50 and < 90): Yellow
        np.testing.assert_allclose(res_2d[1, 0], [1.0, 1.0, 0.0, 1.0])
        # Voxel (1, 1) is 100.0 (>= 90): Red
        np.testing.assert_allclose(res_2d[1, 1], [1.0, 0.0, 0.0, 1.0])

        # 2. Single-texture mode (target_buffer=nn_base): precomposited into base
        base_buf = np.zeros((2, 2, 4), dtype=np.float32)
        base_buf[:, :] = [0.2, 0.2, 0.2, 1.0]  # dark gray base
        compute_native_voxel_overlay(
            mock_v,
            pmin=[0.0, 0.0],
            pmax=[2.0, 2.0],
            canvas_w=2,
            canvas_h=2,
            target_buffer=base_buf,
            opacity=0.5,
            colorwash=bands,
        )
        # (0, 0) was < 10, so base pixel is left untouched!
        np.testing.assert_allclose(base_buf[0, 0], [0.2, 0.2, 0.2, 1.0])
        # (0, 1) blended with blue at 0.5 opacity: 0.0*0.5 + 0.2*0.5 = 0.1, 1.0*0.5 + 0.2*0.5 = 0.6
        np.testing.assert_allclose(base_buf[0, 1, 0], 0.1, atol=1e-5)
        np.testing.assert_allclose(base_buf[0, 1, 2], 0.6, atol=1e-5)

    def test_dose_opacity_slider_synchronization(self):
        controller = self.plugin._controller
        ui = self.plugin._ui
        slider_tag = ui._t("slider_shading_opacity")

        # 1. Base image mode
        self.mock_viewer.volume.unit = "Gy"
        self.mock_viewer.view_state.display.overlay = None

        with patch("dearpygui.dearpygui.does_item_exist", return_value=True), \
             patch("dearpygui.dearpygui.configure_item") as mock_cfg, \
             patch("dearpygui.dearpygui.set_value") as mock_set_val, \
             patch("dearpygui.dearpygui.is_item_active", return_value=False):

            # Base + Shading OFF -> slider should be disabled
            controller.on_toggle_shading(app_data=False)
            mock_cfg.assert_called_with(slider_tag, enabled=False)

            # Base + Shading ON -> slider should be enabled
            controller.on_toggle_shading(app_data=True)
            mock_cfg.assert_called_with(slider_tag, enabled=True)

            # 2. Overlay mode
            mock_ov = MagicMock(image_id="img_ov", opacity=0.4)
            self.mock_viewer.view_state.display.overlay = mock_ov
            ov_vol = MagicMock(unit="Gy", is_roi=False)
            self.mock_api.get_volumes.return_value = {"img_ov": ov_vol, self.mock_viewer.image_id: self.mock_viewer.volume}
            self.mock_api.get_view_states.return_value = {
                "img_ov": MagicMock(display=MagicMock(overlay=None)),
                self.mock_viewer.image_id: self.mock_viewer.view_state,
            }

            # Overlay + Shading OFF -> slider should remain enabled (controls fusion opacity!)
            controller.on_toggle_shading(app_data=False)
            mock_cfg.assert_called_with(slider_tag, enabled=True)

            # Changing slider updates both overlay.opacity and state.colorwash_opacity
            controller.on_shading_opacity_changed(app_data=0.62)
            self.assertEqual(mock_ov.opacity, 0.62)
            state = controller.get_isocontour_state("img_ov")
            self.assertEqual(state.colorwash_opacity, 0.62)
            mock_set_val.assert_any_call("slider_fusion_opacity", 0.62)

            # In update_ui, slider and state are synced with overlay.opacity
            mock_ov.opacity = 0.88
            ui.update_ui(self.mock_api)
            self.assertEqual(state.colorwash_opacity, 0.88)
            mock_set_val.assert_any_call(slider_tag, 0.88)

    def test_dvh_calculation(self):
        import SimpleITK as sitk
        from vvv.plugins.dose.dvh_calc import compute_roi_dvh

        # Create mock dose volume (shape: 10x10x10)
        dose_arr = np.linspace(0, 50, 1000, dtype=np.float32).reshape((10, 10, 10))
        mock_dose_vol = MagicMock()
        mock_dose_vol.sitk_image = sitk.GetImageFromArray(dose_arr)
        mock_dose_vol.sitk_image.SetSpacing((1.0, 1.0, 1.0))
        mock_dose_vol.data = dose_arr

        # Create mock ROI volume (shape: 10x10x10 with 100 non-zero voxels)
        roi_arr = np.zeros((10, 10, 10), dtype=np.uint8)
        roi_arr[2:4, 2:7, 2:7] = 1  # 2 * 5 * 5 = 50 voxels
        mock_roi_vol = MagicMock()
        mock_roi_vol.sitk_image = sitk.GetImageFromArray(roi_arr)
        mock_roi_vol.sitk_image.SetSpacing((1.0, 1.0, 1.0))
        mock_roi_vol.data = roi_arr

        curve = compute_roi_dvh(
            dose_vol=mock_dose_vol,
            roi_vol=mock_roi_vol,
            roi_name="PTV",
            color=[255, 0, 0, 255],
            num_bins=100,
        )

        self.assertIsNotNone(curve)
        self.assertEqual(curve.roi_name, "PTV")
        self.assertAlmostEqual(curve.volume_cc, 0.05, places=3)
        self.assertEqual(curve.volume_percent[0], 100.0)
        self.assertTrue(curve.volume_percent[-1] <= 1.0)
        self.assertTrue(curve.min_dose < curve.max_dose)
        self.assertTrue(curve.d98 <= curve.median_dose <= curve.d2)

    def test_dvh_window_ui(self):
        import SimpleITK as sitk

        ui = self.plugin._ui
        ctrl = self.plugin._controller

        # Setup active dose image
        self.mock_viewer.volume.unit = "Gy"
        dose_arr = np.full((10, 10, 10), 45.0, dtype=np.float32)
        self.mock_viewer.volume.data = dose_arr
        self.mock_viewer.volume.sitk_image = sitk.GetImageFromArray(dose_arr)
        self.mock_viewer.volume.sitk_image.SetSpacing((1.0, 1.0, 1.0))

        # Setup ROI in view_state
        roi_arr = np.ones((10, 10, 10), dtype=np.uint8)
        mock_roi_vol = MagicMock()
        mock_roi_vol.data = roi_arr
        mock_roi_vol.sitk_image = sitk.GetImageFromArray(roi_arr)
        mock_roi_vol.sitk_image.SetSpacing((1.0, 1.0, 1.0))

        roi_state = MagicMock()
        roi_state.name = "Bladder"
        roi_state.color = [0, 0, 255, 255]
        self.mock_viewer.view_state.rois = {"roi_bladder": roi_state}
        self.mock_api.get_volumes.return_value = {
            "img_1": self.mock_viewer.volume,
            "roi_bladder": mock_roi_vol,
        }

        # Open DVH window
        ui.on_open_dvh_clicked()
        win_tag = ui.dvh_win.window_tag
        self.assertTrue(dpg.does_item_exist(win_tag))
        self.assertTrue(dpg.does_item_exist(ui.dvh_win._t("dvh_plot")))
        self.assertTrue(dpg.does_item_exist(ui.dvh_win._t("dvh_metrics_table")))

        # Check controls existence
        self.assertTrue(dpg.does_item_exist(ui.dvh_win._t("dvh_btn_fit_view")))
        self.assertTrue(dpg.does_item_exist(ui.dvh_win._t("dvh_chk_show_legend")))
        self.assertTrue(dpg.does_item_exist(ui.dvh_win._t("dvh_combo_legend_loc")))
        self.assertTrue(dpg.does_item_exist(ui.dvh_win._t("input_dvh_filter")))
        self.assertTrue(dpg.does_item_exist(ui.dvh_win._t("btn_clear_dvh_filter")))
        self.assertTrue(dpg.does_item_exist(ui.dvh_win._t("btn_dvh_filter_invert")))

        # Check that curve was computed
        self.assertEqual(len(ui.dvh_win.curves), 1)
        self.assertEqual(ui.dvh_win.curves[0].roi_name, "Bladder")

        # Test filter matching & inverting
        ui.dvh_win._on_filter_changed("blad")
        self.assertEqual(len(ui.dvh_win._get_filtered_curves()), 1)
        ui.dvh_win._on_filter_changed("rect")
        self.assertEqual(len(ui.dvh_win._get_filtered_curves()), 0)

        # Invert filter
        ui.dvh_win._on_toggle_filter_invert()
        self.assertEqual(len(ui.dvh_win._get_filtered_curves()), 1)
        self.assertEqual(ui.dvh_win._get_filtered_curves()[0].roi_name, "Bladder")

        # Clear filter
        ui.dvh_win._on_clear_filter()
        self.assertEqual(len(ui.dvh_win._get_filtered_curves()), 1)

        # Test Fit View
        ui.dvh_win.fit_view()

        # Test legend toggle & location switcher
        for loc in ["Top-Left", "Bottom-Left", "Bottom-Right", "Outside", "Top-Right"]:
            dpg.set_value(ui.dvh_win._t("dvh_combo_legend_loc"), loc)
            ui.dvh_win._on_legend_location_changed(app_data=loc)

        dpg.set_value(ui.dvh_win._t("dvh_chk_show_legend"), False)
        ui.dvh_win._on_toggle_legend()
        self.assertFalse(dpg.get_item_configuration(ui.dvh_win._t("dvh_combo_legend_loc"))["enabled"])

        # Test radio toggle
        ui.dvh_win._on_display_option_changed()

        # Test CSV export
        import os
        import tempfile
        test_csv_path = os.path.join(tempfile.gettempdir(), "test_dvh.csv")
        with patch("vvv.ui.file_dialog.save_file_dialog", return_value=test_csv_path):
            ui.dvh_win.on_export_csv_clicked()
            self.assertTrue(os.path.exists(test_csv_path))
            with open(test_csv_path, "r", encoding="utf-8") as f:
                content = f.read()
                self.assertIn("Bladder", content)
                self.assertIn("# DVH Summary Metrics", content)
            os.remove(test_csv_path)

        # Close window
        ui.dvh_win.on_window_close()
        self.assertFalse(dpg.does_item_exist(win_tag))

    def test_dvh_roi_color_sync(self):
        import SimpleITK as sitk

        ui = self.plugin._ui
        self.mock_viewer.volume.unit = "Gy"
        dose_arr = np.linspace(0, 50, 1000, dtype=np.float32).reshape((10, 10, 10))
        self.mock_viewer.volume.data = dose_arr
        self.mock_viewer.volume.sitk_image = sitk.GetImageFromArray(dose_arr)
        self.mock_viewer.volume.sitk_image.SetSpacing((1.0, 1.0, 1.0))

        # Setup ROI in view_state with Red color
        roi_arr = np.ones((10, 10, 10), dtype=np.uint8)
        mock_roi_vol = MagicMock()
        mock_roi_vol.data = roi_arr
        mock_roi_vol.sitk_image = sitk.GetImageFromArray(roi_arr)
        mock_roi_vol.sitk_image.SetSpacing((1.0, 1.0, 1.0))

        roi_state = MagicMock()
        roi_state.name = "PTV"
        roi_state.color = [255, 0, 0, 255]
        self.mock_viewer.view_state.rois = {"roi_ptv": roi_state}
        self.mock_api.get_volumes.return_value = {
            "img_1": self.mock_viewer.volume,
            "roi_ptv": mock_roi_vol,
        }

        # Open DVH window
        ui.on_open_dvh_clicked()
        self.assertTrue(dpg.does_item_exist(ui.dvh_win.window_tag))
        self.assertEqual(len(ui.dvh_win.curves), 1)
        self.assertEqual(ui.dvh_win.curves[0].color[:3], [255, 0, 0])

        series_col_tag = ui.dvh_win._t("dvh_series_col_roi_ptv")
        swatch_tag = ui.dvh_win._t("dvh_struct_color_roi_ptv")
        metric_name_tag = ui.dvh_win._t("dvh_metric_name_roi_ptv")

        self.assertTrue(dpg.does_item_exist(series_col_tag))
        self.assertTrue(dpg.does_item_exist(swatch_tag))
        self.assertTrue(dpg.does_item_exist(metric_name_tag))

        # 1. External change in ROI tool (e.g. ROI color changed to green)
        roi_state.color = [0, 255, 0, 255]
        ui.update_ui(self.mock_api)

        # DVH curve, line series theme, swatch, and table metric should be updated to green
        self.assertEqual(ui.dvh_win.curves[0].color[:3], [0, 255, 0])
        self.assertEqual(dpg.get_value(series_col_tag)[:3], [0, 255, 0])
        self.assertEqual(dpg.get_value(swatch_tag)[:3], [0, 255, 0])

        # 2. User edits color swatch directly inside DVH window (e.g. to cyan)
        ui.dvh_win._on_structure_color_edited(
            sender=swatch_tag,
            app_data=[0.0, 1.0, 1.0, 1.0],
            user_data="roi_ptv",
        )
        self.assertEqual(roi_state.color[:3], [0, 255, 255])
        self.assertEqual(ui.dvh_win.curves[0].color[:3], [0, 255, 255])
        self.assertEqual(dpg.get_value(series_col_tag)[:3], [0, 255, 255])
        self.assertTrue(self.mock_api.request_refresh.called)

        ui.dvh_win.on_window_close()

    def test_dvh_table_sorting(self):
        import SimpleITK as sitk

        ui = self.plugin._ui
        self.mock_viewer.volume.unit = "Gy"
        dose_arr = np.linspace(0, 50, 1000, dtype=np.float32).reshape((10, 10, 10))
        self.mock_viewer.volume.data = dose_arr
        self.mock_viewer.volume.sitk_image = sitk.GetImageFromArray(dose_arr)
        self.mock_viewer.volume.sitk_image.SetSpacing((1.0, 1.0, 1.0))

        # Setup 3 ROIs
        def make_roi(name, mask_slice):
            arr = np.zeros((10, 10, 10), dtype=np.uint8)
            arr[mask_slice] = 1
            vol = MagicMock()
            vol.data = arr
            vol.sitk_image = sitk.GetImageFromArray(arr)
            vol.sitk_image.SetSpacing((1.0, 1.0, 1.0))
            st = MagicMock()
            st.name = name
            st.color = [255, 0, 0, 255]
            return vol, st

        v_blad, s_blad = make_roi("Bladder", (slice(0, 2), slice(0, 5), slice(0, 5)))
        v_rect, s_rect = make_roi("Rectum", (slice(0, 1), slice(0, 5), slice(0, 5)))
        v_ptv, s_ptv = make_roi("PTV", (slice(0, 4), slice(0, 5), slice(0, 5)))

        self.mock_viewer.view_state.rois = {
            "roi_blad": s_blad,
            "roi_rect": s_rect,
            "roi_ptv": s_ptv,
        }
        self.mock_api.get_volumes.return_value = {
            "img_1": self.mock_viewer.volume,
            "roi_blad": v_blad,
            "roi_rect": v_rect,
            "roi_ptv": v_ptv,
        }

        # Open DVH window
        ui.on_open_dvh_clicked()
        tbl_tag = ui.dvh_win._t("dvh_metrics_table")
        self.assertTrue(dpg.does_item_exist(tbl_tag))
        self.assertTrue(dpg.get_item_configuration(tbl_tag)["sortable"])

        def get_rendered_names():
            rows = dpg.get_item_children(tbl_tag, slot=1) or []
            names = []
            for r in rows:
                first_cell = (dpg.get_item_children(r, slot=1) or [])[0]
                names.append(dpg.get_value(first_cell))
            return names

        # 1. Sort by structure name ascending
        ui.dvh_win._on_table_sort(sort_specs=[[ui.dvh_win._t("dvh_col_struct"), 1]])
        self.assertEqual(get_rendered_names(), ["Bladder", "PTV", "Rectum"])

        # 2. Sort by structure name descending
        ui.dvh_win._on_table_sort(sort_specs=[[ui.dvh_win._t("dvh_col_struct"), -1]])
        self.assertEqual(get_rendered_names(), ["Rectum", "PTV", "Bladder"])

        # 3. Sort by volume ascending (Rectum < Bladder < PTV)
        ui.dvh_win._on_table_sort(sort_specs=[[ui.dvh_win._t("dvh_col_vol"), 1]])
        self.assertEqual(get_rendered_names(), ["Rectum", "Bladder", "PTV"])

        # 4. Sort by volume descending (PTV > Bladder > Rectum)
        ui.dvh_win._on_table_sort(sort_specs=[[ui.dvh_win._t("dvh_col_vol"), -1]])
        self.assertEqual(get_rendered_names(), ["PTV", "Bladder", "Rectum"])

        # 5. Clear sorting
        ui.dvh_win._on_table_sort(sort_specs=None)
        self.assertIsNone(ui.dvh_win.sort_column)

        ui.dvh_win.on_window_close()

    def test_isodose_input_tag_shielding(self):
        ui = self.plugin._ui
        self.mock_viewer.volume.unit = "Gy"
        ui.rebuild_levels_ui(self.mock_api)
        tag = ui._t("input_lvl_0")
        self.assertTrue(dpg.does_item_exist(tag))
        self.assertIn("input_", tag)

    def test_dvh_window_cleanup_on_image_removed_and_destroy(self):
        import SimpleITK as sitk

        ui = self.plugin._ui
        controller = self.plugin._controller
        self.mock_viewer.volume.unit = "Gy"
        dose_arr = np.linspace(0, 50, 1000, dtype=np.float32).reshape((10, 10, 10))
        self.mock_viewer.volume.data = dose_arr
        self.mock_viewer.volume.sitk_image = sitk.GetImageFromArray(dose_arr)
        self.mock_viewer.volume.sitk_image.SetSpacing((1.0, 1.0, 1.0))

        # 1. Test image removal closes DVH window when target dose image is removed
        ui.on_open_dvh_clicked()
        self.assertTrue(dpg.does_item_exist(ui.dvh_win.window_tag))

        # When img_1 (active dose volume) is removed
        controller.on_image_removed("img_1")
        self.assertFalse(dpg.does_item_exist(ui.dvh_win.window_tag))

        # 2. Test destroy closes DVH window
        ui.on_open_dvh_clicked()
        self.assertTrue(dpg.does_item_exist(ui.dvh_win.window_tag))
        self.plugin.destroy()
        self.assertFalse(dpg.does_item_exist(ui.dvh_win.window_tag))


if __name__ == "__main__":
    unittest.main()


