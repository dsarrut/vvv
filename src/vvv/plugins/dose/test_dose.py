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

        # Add level
        initial_len = len(state.levels)
        controller.on_add_level_clicked()
        self.assertEqual(len(state.levels), initial_len + 1)

        # Delete level
        controller.on_delete_level_clicked(None, None, 0)
        self.assertEqual(len(state.levels), initial_len)

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


if __name__ == "__main__":
    unittest.main()

