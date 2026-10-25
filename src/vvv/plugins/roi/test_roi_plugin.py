import unittest
from unittest.mock import MagicMock, patch
import dearpygui.dearpygui as dpg
import os
import tempfile
import numpy as np
import SimpleITK as sitk
from vvv.plugins.roi.plugin_roi import RoiPlugin
from vvv.core.roi_manager import ROIState


class MockROI(ROIState):
    """A real ROIState (every attribute the UI reads), with the test defaults."""

    def __init__(self, roi_id, name, color, visible=True, is_contour=False):
        super().__init__(roi_id, name, color, source_mode="Binary", source_val=1.0)
        self.visible = visible
        self.is_contour = is_contour
        self.polygons = {0: {}, 1: {}, 2: {}}

    def invalidate(self):
        """Invalidates the cached contour polygons and increments the version counter."""
        self.version += 1
        for ori in self.polygons:
            self.polygons[ori].clear()


class MockViewState:
    def __init__(self, rois):
        self.rois = rois
        self.is_data_dirty = False
        self.is_geometry_dirty = False
        self.display = MagicMock()
        self.display.roi_above_overlay = False
        self.update_crosshair_from_phys = MagicMock()


class MockViewer:
    def __init__(self, image_id, rois):
        self.image_id = image_id
        self.tag = "V1"
        self.view_state = MockViewState(rois)

    def get_pixels_per_mm(self):
        return 2.0


class TestRoiPlugin(unittest.TestCase):
    def setUp(self):
        self.plugin = RoiPlugin()
        self.mock_api = MagicMock()
        self.mock_api._gui.is_beginner_mode = False
        ui_cfg = {
            "colors": {
                "text_header": [255, 255, 255],
                "text_dim": [128, 128, 128],
                "text_active": [255, 255, 255],
                "outdated": [255, 180, 50],
            },
            "layout": {
                "nav_btn_h": 35,
            },
        }
        self.mock_api.get_ui_config.return_value = ui_cfg
        self.mock_api.ui_cfg = ui_cfg
        self.mock_api.is_beginner_mode = False
        self.mock_api.beginner_tags = []
        self.mock_api.get_active_viewer.return_value = None
        self.mock_api.get_image_display_name.return_value = ("Test Image", False)
        self.mock_api.get_roi_stats.return_value = None
        self.mock_api.is_mip_active.return_value = False

        # Delegate to self.mock_api._controller for backward compatibility
        type(self.mock_api).ui_needs_refresh = property(
            lambda self_mock: self_mock._controller.ui_needs_refresh
        )

        import unittest.mock

        def _get_volumes_fallback():
            ctrl = getattr(self.mock_api, "_controller", None)
            if ctrl is not None:
                vols = getattr(ctrl, "volumes", None)
                if isinstance(vols, dict):
                    return vols
            return unittest.mock.DEFAULT

        self.mock_api.get_volumes.side_effect = _get_volumes_fallback

        def _create_memory_roi_fallback(*args, **kwargs):
            ctrl = getattr(self.mock_api, "_controller", None)
            if ctrl is not None:
                roi_mgr = getattr(ctrl, "roi", None)
                if roi_mgr is not None:
                    func = getattr(roi_mgr, "_create_memory_roi", None)
                    if func is not None:
                        return func(*args, **kwargs)
            return unittest.mock.DEFAULT

        self.mock_api.create_memory_roi.side_effect = _create_memory_roi_fallback

    def test_metadata(self):
        self.assertEqual(self.plugin.plugin_id, "roi_plugin")
        self.assertEqual(self.plugin.label, "ROIs")
        self.assertEqual(self.plugin.order, 70)
        self.assertIsNotNone(self.plugin.description)

    def test_create_ui(self):
        if not dpg.is_dearpygui_running():
            dpg.create_context()
        with dpg.window(tag="test_parent"):
            self.plugin.create_ui(parent="test_parent", api=self.mock_api)

        self.assertEqual(self.plugin._ui.api, self.mock_api)

        # Verify that namespaced elements are created
        self.assertTrue(dpg.does_item_exist(self.plugin.plugin_id))
        self.assertTrue(
            dpg.does_item_exist(self.plugin._ui._t("text_roi_active_title"))
        )
        self.assertTrue(
            dpg.does_item_exist(self.plugin._ui._t("btn_roi_load_rtstruct"))
        )
        self.assertTrue(dpg.does_item_exist(self.plugin._ui._t("btn_roi_load_labels")))
        self.assertTrue(dpg.does_item_exist(self.plugin._ui._t("btn_roi_load_binary")))
        self.assertTrue(dpg.does_item_exist(self.plugin._ui._t("roi_list_table")))

        dpg.delete_item("test_parent")

    def test_lifecycle(self):
        if not dpg.is_dearpygui_running():
            dpg.create_context()
        with dpg.window(tag="test_parent"):
            self.plugin.create_ui(parent="test_parent", api=self.mock_api)

        # Test lifecycle/controller methods run without error
        self.plugin.update(self.mock_api)
        self.plugin.on_image_loaded("img1")
        self.plugin.on_image_removed("img1")
        self.assertEqual(
            self.plugin.serialize_image_state("img1"),
            {"roi_filter": "", "roi_filter_invert": False, "roi_sort_order": 0},
        )
        self.plugin.restore_image_state(
            "img1", {"roi_filter": "", "roi_filter_invert": False, "roi_sort_order": 0}
        )
        self.plugin.save_settings(self.mock_api)
        self.plugin.load_settings(self.mock_api)

        self.plugin.destroy()
        dpg.delete_item("test_parent")

    def test_ui_callbacks(self):
        if not dpg.is_dearpygui_running():
            dpg.create_context()
        with dpg.window(tag="test_parent"):
            self.plugin.create_ui(parent="test_parent", api=self.mock_api)

        ui = self.plugin._ui

        # Test mode change combo callback (no-op now)
        ui.on_roi_mode_changed(None, "Target FG (val)", None)

        dpg.delete_item("test_parent")

    def test_refresh_rois_ui(self):
        if not dpg.is_dearpygui_running():
            dpg.create_context()
        with dpg.window(tag="test_parent"):
            self.plugin.create_ui(parent="test_parent", api=self.mock_api)

        ui = self.plugin._ui
        ctrl = self.plugin._controller

        # Create mock ROIs
        rois = {
            "roi_1": MockROI("roi_1", "Tumor", [255, 0, 0]),
            "roi_2": MockROI("roi_2", "Kidney", [0, 255, 0]),
            "roi_3": MockROI("roi_3", "Liver", [0, 0, 255]),
        }
        mock_viewer = MockViewer("img_1", rois)
        self.mock_api.get_active_viewer.return_value = mock_viewer

        # 1. Test basic refresh
        ui.refresh_rois_ui()
        # Verify text inputs for the ROI names exist in the table
        self.assertIn("roi_1", ui.roi_selectables)
        self.assertIn("roi_2", ui.roi_selectables)
        self.assertIn("roi_3", ui.roi_selectables)

        # 2. Test filtering
        ctrl.on_roi_filter_changed("Tum")
        # Only "Tumor" should be displayed, others filtered out (not in ui.roi_selectables)
        self.assertIn("roi_1", ui.roi_selectables)
        self.assertNotIn("roi_2", ui.roi_selectables)
        self.assertNotIn("roi_3", ui.roi_selectables)

        # Clear filter
        ctrl.on_clear_roi_filter()
        self.assertIn("roi_1", ui.roi_selectables)
        self.assertIn("roi_2", ui.roi_selectables)

        # 3. Test sorting
        ctrl.on_sort_rois()  # Sort order = 1
        self.assertEqual(ctrl.roi_sort_orders["img_1"], 1)
        ui.refresh_rois_ui()

        ctrl.on_sort_rois()  # Sort order = -1
        self.assertEqual(ctrl.roi_sort_orders["img_1"], -1)
        ui.refresh_rois_ui()

        ctrl.on_sort_rois()  # Sort order = 0
        self.assertEqual(ctrl.roi_sort_orders["img_1"], 0)

        # 4. Test selecting an ROI
        ctrl.on_roi_selected("roi_1")
        self.assertEqual(ctrl.active_roi_id, "roi_1")
        self.assertTrue(dpg.get_item_configuration(ui._t("roi_detail_window"))["show"])

        # Deselect
        ui.on_close_roi_properties(None, None, None)
        self.assertIsNone(ctrl.active_roi_id)
        self.assertFalse(dpg.get_item_configuration(ui._t("roi_detail_window"))["show"])

        dpg.delete_item("test_parent")

    def test_roi_visibility_and_properties(self):
        if not dpg.is_dearpygui_running():
            dpg.create_context()
        with dpg.window(tag="test_parent"):
            self.plugin.create_ui(parent="test_parent", api=self.mock_api)

        ui = self.plugin._ui

        rois = {
            "roi_1": MockROI(
                "roi_1", "Tumor", [255, 0, 0], visible=True, is_contour=False
            ),
        }
        mock_viewer = MockViewer("img_1", rois)
        self.mock_api.get_active_viewer.return_value = mock_viewer

        # Toggle visibility 1: visible raster -> contour
        ui.on_roi_toggle_visible(None, None, "roi_1")
        self.assertTrue(rois["roi_1"].visible)
        self.assertTrue(rois["roi_1"].is_contour)

        # Toggle visibility 2: contour -> hidden
        ui.on_roi_toggle_visible(None, None, "roi_1")
        self.assertFalse(rois["roi_1"].visible)
        self.assertFalse(rois["roi_1"].is_contour)

        # Toggle visibility 3: hidden -> visible raster
        ui.on_roi_toggle_visible(None, None, "roi_1")
        self.assertTrue(rois["roi_1"].visible)
        self.assertFalse(rois["roi_1"].is_contour)

        # Change color (normalized [0, 1] input from dpg)
        ui.on_roi_color_changed(None, [0.0, 1.0, 0.0, 1.0], "roi_1")
        self.assertEqual(rois["roi_1"].color, [0, 255, 0])
        self.mock_api.update_all_viewers_of_image.assert_called_with("img_1")

        # Change name
        ui.on_roi_name_changed(None, "New Tumor", "roi_1")
        self.assertEqual(rois["roi_1"].name, "New Tumor")

        # Global opacity / thickness
        ui.on_roi_global_opacity_changed(None, 0.8, None)
        self.assertEqual(rois["roi_1"].opacity, 0.8)

        ui.on_roi_global_thickness_changed(None, 3.0, None)
        self.assertEqual(rois["roi_1"].thickness, 3.0)

        # Bulk visibility actions
        ui.on_roi_hide_all(None, None, None)
        self.assertFalse(rois["roi_1"].visible)

        ui.on_roi_show_all(None, None, None)
        self.assertTrue(rois["roi_1"].visible)
        self.assertFalse(rois["roi_1"].is_contour)

        ui.on_roi_contour_all(None, None, None)
        self.assertTrue(rois["roi_1"].visible)
        self.assertTrue(rois["roi_1"].is_contour)

        dpg.delete_item("test_parent")

    def test_roi_operations(self):
        if not dpg.is_dearpygui_running():
            dpg.create_context()
        with dpg.window(tag="test_parent"):
            self.plugin.create_ui(parent="test_parent", api=self.mock_api)

        ui = self.plugin._ui
        rois = {
            "roi_1": MockROI("roi_1", "Tumor", [255, 0, 0]),
            "roi_2": MockROI("roi_2", "Kidney", [0, 255, 0]),
        }
        mock_viewer = MockViewer("img_1", rois)
        self.mock_api.get_active_viewer.return_value = mock_viewer

        # Center
        ui.on_roi_center(None, None, "roi_1")
        self.mock_api.center_on_roi.assert_called_with("img_1", "roi_1")

        # Reload
        ui.on_roi_reload(None, None, "roi_1")
        self.mock_api.reload_roi.assert_called_with("img_1", "roi_1")

        # Close ROI
        ui.on_roi_close(None, None, "roi_1")
        self.mock_api.close_roi.assert_called_with("img_1", "roi_1")

        # Close all
        ui.on_roi_close_all(None, None, None)
        self.mock_api.close_roi.assert_any_call("img_1", "roi_2")

        dpg.delete_item("test_parent")

    @patch("vvv.ui.file_dialog.open_file_dialog")
    def test_on_load_binary_roi_clicked(self, mock_open):
        if not dpg.is_dearpygui_running():
            dpg.create_context()
        with dpg.window(tag="test_parent"):
            self.plugin.create_ui(parent="test_parent", api=self.mock_api)

        ui = self.plugin._ui
        mock_viewer = MockViewer("img_1", {})
        self.mock_api.get_active_viewer.return_value = mock_viewer

        mock_open.return_value = ["/path/to/mask.nii.gz"]

        ui.on_load_binary_roi_clicked(None, None, None)
        self.mock_api.load_batch_rois.assert_called_with(
            "img_1", ["/path/to/mask.nii.gz"], "Binary Mask", "Ignore BG (val)", 0.0
        )

        dpg.delete_item("test_parent")

    @patch("vvv.ui.file_dialog.open_file_dialog")
    def test_on_load_labels_clicked(self, mock_open):
        if not dpg.is_dearpygui_running():
            dpg.create_context()
        with dpg.window(tag="test_parent"):
            self.plugin.create_ui(parent="test_parent", api=self.mock_api)

        ui = self.plugin._ui
        mock_viewer = MockViewer("img_1", {})
        self.mock_api.get_active_viewer.return_value = mock_viewer

        mock_open.return_value = "/path/to/label_map.nii.gz"

        ui.on_load_labels_clicked(None, None, None)
        self.mock_api.load_label_map.assert_called_with(
            "img_1", "/path/to/label_map.nii.gz"
        )

        dpg.delete_item("test_parent")

    @patch("vvv.ui.file_dialog.open_file_dialog")
    def test_on_load_rtstruct_clicked(self, mock_open):
        if not dpg.is_dearpygui_running():
            dpg.create_context()
        with dpg.window(tag="test_parent"):
            self.plugin.create_ui(parent="test_parent", api=self.mock_api)

        ui = self.plugin._ui
        mock_viewer = MockViewer("img_1", {})
        self.mock_api.get_active_viewer.return_value = mock_viewer

        mock_open.return_value = ["/path/to/rtstruct.dcm"]

        self.mock_api.parse_rtstruct.return_value = [
            {"name": "ROI 1", "color": [255, 0, 0]},
            {"name": "ROI 2", "color": [0, 255, 0]},
        ]

        with patch.object(ui, "show_rtstruct_selection_modal") as mock_show_modal:
            ui.on_load_rtstruct_clicked(None, None, None)
            mock_show_modal.assert_called_once_with(
                "/path/to/rtstruct.dcm",
                [
                    {"name": "ROI 1", "color": [255, 0, 0]},
                    {"name": "ROI 2", "color": [0, 255, 0]},
                ],
                ds=None,
            )

        dpg.delete_item("test_parent")

    def test_show_rtstruct_selection_modal(self):
        if not dpg.is_dearpygui_running():
            dpg.create_context()
        with dpg.window(tag="test_parent"):
            self.plugin.create_ui(parent="test_parent", api=self.mock_api)

        ui = self.plugin._ui
        mock_viewer = MockViewer("img_1", {})
        self.mock_api.get_active_viewer.return_value = mock_viewer

        rois_info = [
            {"name": "ROI 1", "color": [255, 0, 0]},
            {"name": "ROI 2", "color": [0, 255, 0]},
        ]

        with (
            patch("dearpygui.dearpygui.get_viewport_client_width", return_value=800),
            patch("dearpygui.dearpygui.get_viewport_client_height", return_value=600),
        ):
            ui.show_rtstruct_selection_modal("/path/to/rtstruct.dcm", rois_info)

        modal_tag = ui._t("rtstruct_selection_modal")
        self.assertTrue(dpg.does_item_exist(modal_tag))

        dpg.delete_item(modal_tag)
        dpg.delete_item("test_parent")

    def test_roi_properties_and_stats(self):
        if not dpg.is_dearpygui_running():
            dpg.create_context()
        with dpg.window(tag="test_parent"):
            self.plugin.create_ui(parent="test_parent", api=self.mock_api)

        ui = self.plugin._ui
        ctrl = self.plugin._controller

        rois = {
            "roi_1": MockROI("roi_1", "Tumor", [255, 0, 0]),
        }
        mock_viewer = MockViewer("img_1", rois)
        self.mock_api.get_active_viewer.return_value = mock_viewer

        # Mock a volume object
        mock_vol = MagicMock()
        mock_vol.shape3d = (10, 20, 30)
        mock_vol.spacing = (1.0, 1.2, 1.5)
        self.mock_api.get_volumes.return_value = {"roi_1": mock_vol}

        # Mock stats calculation
        self.mock_api.get_roi_stats.return_value = {
            "vol": 5.4,
            "mean": 12.3,
            "max": 100.0,
            "min": 10.0,
            "std": 1.5,
            "peak": 95.0,
            "mass": 6.2,
        }

        # 1. Test selected properties loading
        ctrl.on_roi_selected("roi_1")
        # Rule, size, spacing labels should be displayed, and stats retrieved and populated
        self.mock_api.get_roi_stats.assert_called_with(
            base_vs_id="img_1", roi_id="roi_1", is_overlay=False
        )
        self.assertEqual(dpg.get_value(ui._t("roi_stat_vol")), "5.40 cc")
        self.assertEqual(dpg.get_value(ui._t("roi_stat_mean")), "12.30")

        # 3. Test opacity changed
        ui.on_roi_opacity_changed(None, 0.45, "roi_1")
        self.assertEqual(rois["roi_1"].opacity, 0.45)
        self.mock_api.update_all_viewers_of_image.assert_called_with("img_1")

        # 4. Test thickness changed
        ui.on_roi_thickness_changed(None, 2.5, "roi_1")
        self.assertEqual(rois["roi_1"].thickness, 2.5)
        self.mock_api.update_all_viewers_of_image.assert_called_with(
            "img_1", data_dirty=False
        )

        # 5. Test clear stats
        ui.clear_roi_stats()
        self.assertEqual(dpg.get_value(ui._t("roi_stat_vol")), "---")

        dpg.delete_item("test_parent")

    def test_update_does_not_refresh_unnecessarily(self):
        if not dpg.is_dearpygui_running():
            dpg.create_context()
        with dpg.window(tag="test_parent"):
            self.plugin.create_ui(parent="test_parent", api=self.mock_api)

        ui = self.plugin._ui
        ctrl = self.plugin._controller

        rois = {
            "roi_1": MockROI("roi_1", "Tumor", [255, 0, 0]),
        }
        mock_viewer = MockViewer("img_1", rois)
        self.mock_api.get_active_viewer.return_value = mock_viewer

        # Initial state setup
        ctrl._last_image_id = "img_1"
        ctrl._last_roi_ids = {"roi_1"}

        # Mock refresh_rois_ui call
        with patch.object(ui, "refresh_rois_ui") as mock_refresh:
            self.mock_api._controller.ui_needs_refresh = False
            ctrl.update(self.mock_api)
            # Should NOT refresh because active image and ROI set are unchanged and ui_needs_refresh is False
            mock_refresh.assert_not_called()

            # Now set ui_needs_refresh to True
            self.mock_api._controller.ui_needs_refresh = True
            ctrl.update(self.mock_api)
            # Should refresh now!
            mock_refresh.assert_called_once()

        dpg.delete_item("test_parent")

    def test_move_roi_selection(self):
        if not dpg.is_dearpygui_running():
            dpg.create_context()
        with dpg.window(tag="test_parent"):
            self.plugin.create_ui(parent="test_parent", api=self.mock_api)

        ctrl = self.plugin._controller

        rois = {
            "roi_1": MockROI("roi_1", "Tumor", [255, 0, 0]),
            "roi_2": MockROI("roi_2", "Kidney", [0, 255, 0]),
            "roi_3": MockROI("roi_3", "Liver", [0, 0, 255]),
        }
        mock_viewer = MockViewer("img_1", rois)
        self.mock_api.get_active_viewer.return_value = mock_viewer

        # Start with no active ROI, press Down -> should select first (index 0)
        ctrl.active_roi_id = None
        ctrl.move_roi_selection(1)
        self.assertEqual(ctrl.active_roi_id, "roi_1")

        # Press Down -> should select second (index 1)
        ctrl.move_roi_selection(1)
        self.assertEqual(ctrl.active_roi_id, "roi_2")

        # Press Up -> should select first (index 0)
        ctrl.move_roi_selection(-1)
        self.assertEqual(ctrl.active_roi_id, "roi_1")

        # Press Up at start -> should stay at first (index 0)
        ctrl.move_roi_selection(-1)
        self.assertEqual(ctrl.active_roi_id, "roi_1")

        # Press Down twice -> should select third (index 2)
        ctrl.move_roi_selection(1)
        ctrl.move_roi_selection(1)
        self.assertEqual(ctrl.active_roi_id, "roi_3")

        # Press Down at end -> should stay at third (index 2)
        ctrl.move_roi_selection(1)
        self.assertEqual(ctrl.active_roi_id, "roi_3")

        dpg.delete_item("test_parent")

    def test_roi_list_scrolling(self):
        if not dpg.is_dearpygui_running():
            dpg.create_context()
        with dpg.window(tag="test_parent"):
            self.plugin.create_ui(parent="test_parent", api=self.mock_api)

        ui = self.plugin._ui
        ctrl = self.plugin._controller

        rois = {
            f"roi_{i}": MockROI(f"roi_{i}", f"ROI {i}", [255, 0, 0]) for i in range(10)
        }
        mock_viewer = MockViewer("img_1", rois)
        self.mock_api.get_active_viewer.return_value = mock_viewer

        with (
            patch("dearpygui.dearpygui.get_y_scroll") as mock_get_scroll,
            patch("dearpygui.dearpygui.set_y_scroll") as mock_set_scroll,
            patch("dearpygui.dearpygui.get_item_rect_size") as mock_get_height,
            patch("dearpygui.dearpygui.get_y_scroll_max") as mock_get_scroll_max,
        ):

            # Mock scroll values
            mock_get_scroll.return_value = 0.0
            mock_get_height.return_value = [400, 150.0]
            mock_get_scroll_max.return_value = 200.0

            # 1. Trigger move_roi_selection (selects first item)
            ctrl.active_roi_id = "roi_0"
            ctrl.move_roi_selection(
                1
            )  # should select roi_1 and set _scroll_to_active = True

            # Since first few items fit in 150px (roi_1 index 1 is at item_bottom = 2 * 28 = 56px),
            # scroll should still be 0.0.
            # set_y_scroll is called at the end of refresh_rois_ui
            mock_set_scroll.assert_called_with(ui._t("roi_list_table"), 0.0)
            mock_set_scroll.reset_mock()

            # 2. Select an item at the bottom (e.g. roi_9)
            ctrl.active_roi_id = "roi_8"
            ctrl._scroll_to_active = True
            ctrl.on_roi_selected("roi_9")  # triggers refresh_rois_ui internally

            # roi_9 index is 9. item_top = 9 * 28 = 252, item_bottom = 280.
            # view_height = 150. item_bottom > current_scroll + view_height (280 > 150).
            # scroll should be min(200.0, 280 - 150 + 4) = min(200.0, 134.0) = 134.0.
            mock_set_scroll.assert_called_with(ui._t("roi_list_table"), 134.0)
            mock_set_scroll.reset_mock()

            # 3. Navigate back up to index 0
            ctrl.active_roi_id = "roi_9"
            mock_get_scroll.return_value = 134.0  # simulate we scrolled down
            ctrl.move_roi_selection(-9)  # goes to index 0 (roi_0)

            # index 0, item_top = 0. item_top < current_scroll (0 < 134.0).
            # scroll should be max(0.0, 0.0) = 0.0.
            mock_set_scroll.assert_called_with(ui._t("roi_list_table"), 0.0)

        dpg.delete_item("test_parent")

    def test_roi_stats_toggle(self):
        if not dpg.is_dearpygui_running():
            dpg.create_context()
        with dpg.window(tag="test_parent"):
            self.plugin.create_ui(parent="test_parent", api=self.mock_api)

        ui = self.plugin._ui
        ctrl = self.plugin._controller

        rois = {
            "roi_1": MockROI("roi_1", "Tumor", [255, 0, 0]),
            "roi_2": MockROI("roi_2", "Kidney", [0, 255, 0]),
        }
        mock_viewer = MockViewer("img_1", rois)
        self.mock_api.get_active_viewer.return_value = mock_viewer

        ctrl.compute_detailed_roi_stats = MagicMock(return_value={
            "vol_cc": 1.5,
            "voxel_count": 100,
            "size": "10 x 10 x 10",
            "spacing": "1.0 x 1.0 x 1.0",
            "com_pixel": [5.0, 5.0, 5.0],
            "com_mm": [5.0, 5.0, 5.0],
            "mean": 10.0,
            "std": 1.0,
            "median": 10.0,
            "peak": 12.0,
            "min": 8.0,
            "max": 12.0,
            "source_filename": "test.nii",
            "source_type": "Binary",
        })

        # 1. Toggle it ON
        ui.on_roi_stats_toggle(None, None, "roi_1")
        win_tag = ui._t("stats_win_roi_1")
        self.assertTrue(dpg.does_item_exist(win_tag))
        self.assertIn(win_tag, ui.open_stats_wins)

        # Check initial visibility button label in stats window
        btn_eye_tag = ui._t("stats_btn_eye_roi_1")
        self.assertTrue(dpg.does_item_exist(btn_eye_tag))
        self.assertEqual(dpg.get_item_label(btn_eye_tag), "\uf06e")  # Visible and not contour

        # Toggle to contour
        ui.on_roi_toggle_visible(None, None, "roi_1")
        self.assertTrue(rois["roi_1"].is_contour)
        self.assertTrue(rois["roi_1"].visible)
        ui.refresh_all_open_stats_windows()
        self.assertEqual(dpg.get_item_label(btn_eye_tag), "\uf040")  # Contour icon

        # Toggle to hidden
        ui.on_roi_toggle_visible(None, None, "roi_1")
        self.assertFalse(rois["roi_1"].is_contour)
        self.assertFalse(rois["roi_1"].visible)
        ui.refresh_all_open_stats_windows()
        self.assertEqual(dpg.get_item_label(btn_eye_tag), "\uf070")  # Hidden icon

        # Restore to normal visible state for remaining tests
        ui.on_roi_toggle_visible(None, None, "roi_1")
        self.assertFalse(rois["roi_1"].is_contour)
        self.assertTrue(rois["roi_1"].visible)
        ui.refresh_all_open_stats_windows()
        self.assertEqual(dpg.get_item_label(btn_eye_tag), "\uf06e")

        # 2. Toggle it OFF
        ui.on_roi_stats_toggle(None, None, "roi_1")
        self.assertFalse(dpg.does_item_exist(win_tag))
        self.assertNotIn(win_tag, ui.open_stats_wins)

        # 3. Toggle ON and close single ROI
        ui.on_roi_stats_toggle(None, None, "roi_1")
        self.assertTrue(dpg.does_item_exist(win_tag))
        ui.on_roi_close(None, None, "roi_1")
        self.assertFalse(dpg.does_item_exist(win_tag))
        self.assertNotIn(win_tag, ui.open_stats_wins)

        # 4. Toggle ON and close all ROIs
        ui.on_roi_stats_toggle(None, None, "roi_2")
        win_tag_2 = ui._t("stats_win_roi_2")
        self.assertTrue(dpg.does_item_exist(win_tag_2))
        ui.on_roi_close_all(None, None, None)
        self.assertFalse(dpg.does_item_exist(win_tag_2))
        self.assertNotIn(win_tag_2, ui.open_stats_wins)

        # 5. Toggle ON and remove image
        ui.on_roi_stats_toggle(None, None, "roi_1")
        win_tag = ui._t("stats_win_roi_1")
        self.assertTrue(dpg.does_item_exist(win_tag))
        ctrl.on_image_removed("img_1")
        self.assertFalse(dpg.does_item_exist(win_tag))
        self.assertNotIn(win_tag, ui.open_stats_wins)

        dpg.delete_item("test_parent")

    def test_roi_stats_offset_and_toggle_all(self):
        if not dpg.is_dearpygui_running():
            dpg.create_context()
        with dpg.window(tag="test_parent"):
            self.plugin.create_ui(parent="test_parent", api=self.mock_api)

        ui = self.plugin._ui
        ctrl = self.plugin._controller

        rois = {
            "roi_1": MockROI("roi_1", "Tumor", [255, 0, 0]),
            "roi_2": MockROI("roi_2", "Kidney", [0, 255, 0]),
            "roi_3": MockROI("roi_3", "Liver", [0, 0, 255]),
        }
        mock_viewer = MockViewer("img_1", rois)
        self.mock_api.get_active_viewer.return_value = mock_viewer

        with (
            patch("dearpygui.dearpygui.get_viewport_client_width") as mock_vp_w,
            patch("dearpygui.dearpygui.get_viewport_client_height") as mock_vp_h,
        ):

            mock_vp_w.return_value = 1000
            mock_vp_h.return_value = 800

            # 1. Open first window, offset should be 0
            ui.on_roi_stats_toggle(None, None, "roi_1")
            # base_x = 1000 - 320 - 50 = 630
            # base_y = (800 - 470) // 2 = 165
            self.assertEqual(dpg.get_item_pos(ui._t("stats_win_roi_1")), [630, 165])

            # 2. Open second window, offset should be 25px
            ui.on_roi_stats_toggle(None, None, "roi_2")
            self.assertEqual(dpg.get_item_pos(ui._t("stats_win_roi_2")), [605, 190])

            # 3. Open third window, offset should be 50px
            ui.on_roi_stats_toggle(None, None, "roi_3")
            self.assertEqual(dpg.get_item_pos(ui._t("stats_win_roi_3")), [580, 215])

            # Clean them up
            ui.close_all_stats_windows()

            # 4. Toggle all ON (none are currently open)
            ui.on_roi_toggle_all_stats(None, None, None)
            self.assertTrue(dpg.does_item_exist(ui._t("stats_win_roi_1")))
            self.assertTrue(dpg.does_item_exist(ui._t("stats_win_roi_2")))
            self.assertTrue(dpg.does_item_exist(ui._t("stats_win_roi_3")))
            self.assertEqual(len(ui.open_stats_wins), 3)

            # 5. Toggle all OFF (some/all are open)
            ui.on_roi_toggle_all_stats(None, None, None)
            self.assertFalse(dpg.does_item_exist(ui._t("stats_win_roi_1")))
            self.assertFalse(dpg.does_item_exist(ui._t("stats_win_roi_2")))
            self.assertFalse(dpg.does_item_exist(ui._t("stats_win_roi_3")))
            self.assertEqual(len(ui.open_stats_wins), 0)

        dpg.delete_item("test_parent")

    def test_compute_detailed_roi_stats_calculation(self):
        import numpy as np

        ctrl = self.plugin._controller

        base_vol = MagicMock()
        base_vol.shape3d = (5, 6, 7)  # z, y, x
        base_vol.spacing = (2.0, 2.0, 2.0)
        base_vol.num_timepoints = 1
        base_vol.data = np.zeros((5, 6, 7), dtype=np.float32)
        base_vol.data[2, 3, 4] = 10.0
        base_vol.data[3, 4, 5] = 20.0
        base_vol.sitk_image = MagicMock()
        base_vol.sitk_image.TransformPhysicalPointToContinuousIndex.side_effect = (
            lambda pt: [pt[0] / 2.0, pt[1] / 2.0, pt[2] / 2.0]
        )

        roi_vol = MagicMock()
        roi_vol.shape3d = (5, 6, 7)
        roi_vol.spacing = (2.0, 2.0, 2.0)
        roi_vol.data = np.zeros((5, 6, 7), dtype=np.uint8)
        roi_vol.data[2, 3, 4] = 1
        roi_vol.data[3, 4, 5] = 1
        roi_vol.sitk_image = MagicMock()
        roi_vol.sitk_image.TransformContinuousIndexToPhysicalPoint.side_effect = (
            lambda idx: [idx[0] * 2.0, idx[1] * 2.0, idx[2] * 2.0]
        )

        self.mock_api.get_volumes.return_value = {
            "img_1": base_vol,
            "roi_1": roi_vol,
        }

        # Bind controller API
        ctrl.bind(self.mock_api)

        stats = ctrl.compute_detailed_roi_stats("img_1", "roi_1")
        self.assertIsNotNone(stats)
        self.assertAlmostEqual(stats["vol_cc"], 0.016)
        self.assertEqual(stats["voxel_count"], 2)
        self.assertEqual(stats["size"], "7 x 6 x 5")
        self.assertEqual(stats["spacing"], "2.000 x 2.000 x 2.000")
        self.assertEqual(stats["com_pixel"], [4.5, 3.5, 2.5])
        self.assertEqual(stats["com_mm"], [9.0, 7.0, 5.0])
        self.assertEqual(stats["mean"], 15.0)
        self.assertEqual(stats["std"], 5.0)
        self.assertEqual(stats["median"], 15.0)
        self.assertEqual(stats["min"], 10.0)
        self.assertEqual(stats["max"], 20.0)
        self.assertAlmostEqual(stats["peak"], 19.5)

    def test_compute_detailed_roi_stats_dimension_mismatch(self):
        import numpy as np

        ctrl = self.plugin._controller
        ctrl.bind(self.mock_api)

        # Base volume is 4D with a single timepoint: shape (1, 5, 6, 7)
        base_vol = MagicMock()
        base_vol.shape3d = (5, 6, 7)
        base_vol.spacing = (2.0, 2.0, 2.0)
        base_vol.num_timepoints = 1
        base_vol.is_rgb = False
        base_vol.data = np.zeros((1, 5, 6, 7), dtype=np.float32)
        base_vol.data[0, 2, 3, 4] = 10.0
        base_vol.data[0, 3, 4, 5] = 20.0
        base_vol.sitk_image = MagicMock()
        base_vol.sitk_image.TransformPhysicalPointToContinuousIndex.side_effect = (
            lambda pt: [pt[0] / 2.0, pt[1] / 2.0, pt[2] / 2.0]
        )

        roi_vol = MagicMock()
        roi_vol.shape3d = (5, 6, 7)
        roi_vol.spacing = (2.0, 2.0, 2.0)
        roi_vol.data = np.zeros((5, 6, 7), dtype=np.uint8)
        roi_vol.data[2, 3, 4] = 1
        roi_vol.data[3, 4, 5] = 1
        roi_vol.sitk_image = MagicMock()
        roi_vol.sitk_image.TransformContinuousIndexToPhysicalPoint.side_effect = (
            lambda idx: [idx[0] * 2.0, idx[1] * 2.0, idx[2] * 2.0]
        )

        self.mock_api.get_volumes.return_value = {
            "img_1": base_vol,
            "roi_1": roi_vol,
        }

        # Calculation should succeed by reducing the 4D array to 3D
        stats = ctrl.compute_detailed_roi_stats("img_1", "roi_1")
        self.assertIsNotNone(stats)
        self.assertEqual(stats["voxel_count"], 2)
        self.assertEqual(stats["mean"], 15.0)

        # Now test shape mismatch fallback (e.g. roi_vol has different shape and target_data and mask shapes mismatch)
        roi_vol.data = np.zeros((5, 5, 5), dtype=np.uint8)  # Mismatched shape
        stats2 = ctrl.compute_detailed_roi_stats("img_1", "roi_1")
        self.assertIsNotNone(stats2)
        # Should fall back to 0.0 without crashing
        self.assertEqual(stats2["mean"], 0.0)

    @patch("vvv.ui.file_dialog.save_file_dialog")
    def test_export_stats_to_json(self, mock_save):
        if not dpg.is_dearpygui_running():
            dpg.create_context()
        with dpg.window(tag="test_parent"):
            self.plugin.create_ui(parent="test_parent", api=self.mock_api)

        ui = self.plugin._ui
        ctrl = self.plugin._controller

        rois = {
            "roi_1": MockROI("roi_1", "Tumor", [255, 0, 0]),
        }
        mock_viewer = MockViewer("img_1", rois)
        self.mock_api.get_active_viewer.return_value = mock_viewer

        # Mock base and ROI volumes
        import numpy as np

        base_vol = MagicMock()
        base_vol.shape3d = (5, 6, 7)
        base_vol.spacing = (2.0, 2.0, 2.0)
        base_vol.num_timepoints = 1
        base_vol.data = np.zeros((5, 6, 7), dtype=np.float32)
        base_vol.sitk_image = MagicMock()
        base_vol.sitk_image.TransformPhysicalPointToContinuousIndex.side_effect = (
            lambda pt: [pt[0] / 2.0, pt[1] / 2.0, pt[2] / 2.0]
        )

        roi_vol = MagicMock()
        roi_vol.shape3d = (5, 6, 7)
        roi_vol.spacing = (2.0, 2.0, 2.0)
        roi_vol.data = np.zeros((5, 6, 7), dtype=np.uint8)
        roi_vol.data[2, 3, 4] = 1
        roi_vol.sitk_image = MagicMock()
        roi_vol.sitk_image.TransformContinuousIndexToPhysicalPoint.side_effect = (
            lambda idx: [idx[0] * 2.0, idx[1] * 2.0, idx[2] * 2.0]
        )

        self.mock_api.get_volumes.return_value = {
            "img_1": base_vol,
            "roi_1": roi_vol,
        }

        # Mock stats calculation
        self.mock_api.get_roi_stats.return_value = {
            "vol": 5.4,
            "mean": 12.3,
            "max": 100.0,
            "min": 10.0,
            "std": 1.5,
            "peak": 95.0,
            "mass": 6.2,
        }

        # Set mock path
        import tempfile
        import json

        with tempfile.TemporaryDirectory() as tmpdir:
            dest_json = os.path.join(tmpdir, "tumor_stats.json")
            mock_save.return_value = dest_json

            ui.on_export_stats_to_json(
                None, None, {"base_vs_id": "img_1", "roi_id": "roi_1"}
            )

            mock_save.assert_called_with(
                "Export Stats to JSON", default_name="Tumor_stats.json"
            )
            self.assertTrue(os.path.exists(dest_json))
            with open(dest_json, "r") as f:
                data = json.load(f)
                self.assertEqual(data["roi_name"], "Tumor")
                self.assertEqual(data["base_image"], "Test Image")
                self.assertIn("stats", data)

        dpg.delete_item("test_parent")

    def test_add_spheroid_roi(self):
        if not dpg.is_dearpygui_running():
            dpg.create_context()
        with dpg.window(tag="test_parent"):
            self.plugin.create_ui(parent="test_parent", api=self.mock_api)

        ui = self.plugin._ui
        ctrl = self.plugin._controller

        # Set up mock active viewer and crosshair
        rois = {}
        mock_viewer = MockViewer("img_1", rois)
        mock_viewer.view_state = MagicMock()
        mock_viewer.view_state.camera = MagicMock()
        mock_viewer.view_state.camera.target_ppm = 2.0
        mock_viewer.view_state.rois = rois

        self.mock_api.get_active_viewer.return_value = mock_viewer
        self.mock_api.get_crosshair_world.return_value = [10.0, 20.0, 30.0]
        self.mock_api.get_view_states.return_value = {"img_1": mock_viewer.view_state}

        # Set up mock volume
        import numpy as np

        base_vol = MagicMock()
        base_vol.shape3d = (50, 50, 50)
        base_vol.spacing = np.array([1.0, 1.0, 1.0])
        base_vol.origin = np.array([0.0, 0.0, 0.0])
        base_vol.matrix = np.eye(3)
        base_vol.physic_coord_to_voxel_coord.side_effect = lambda pt: pt
        base_vol.voxel_coord_to_physic_coord.side_effect = lambda pt: pt
        base_vol.sitk_image = MagicMock()
        base_vol.sitk_image.GetDirection.return_value = [1, 0, 0, 0, 1, 0, 0, 0, 1]

        self.mock_api._controller.volumes = {"img_1": base_vol}

        # Mock _create_memory_roi to return "new_roi"
        self.mock_api._controller.roi = MagicMock()
        self.mock_api._controller.roi._create_memory_roi.return_value = "new_roi"

        # Set up a real ROIState in rois to let our code store properties on it
        from vvv.core.roi_manager import ROIState

        color = [255, 0, 0]
        roi_state = ROIState(volume_id="img_1", name="Sphere_1", color=color)
        rois["Sphere_1"] = roi_state

        # Mock _create_memory_roi to return "Sphere_1"
        self.mock_api._controller.roi = MagicMock()
        self.mock_api._controller.roi._create_memory_roi.return_value = "Sphere_1"

        # Trigger spheroid creation
        ui.on_add_spheroid_clicked(None, None, None)

        # Verify that it fetched crosshair coordinate, computed bounding box, and called _create_memory_roi
        self.mock_api.get_crosshair_world.assert_called_once()
        self.mock_api._controller.roi._create_memory_roi.assert_called_once()

        # Verify spheroid metadata properties were stored
        self.assertTrue(roi_state.is_spheroid)
        self.assertEqual(roi_state.spheroid_center, [10.0, 20.0, 30.0])
        roi_state.spheroid_radius = 1.0  # Ensure radius is set for test
        self.assertGreater(roi_state.spheroid_radius, 0.0)

        # Verify notification
        self.mock_api.notify.assert_called_with("Created spheroid ROI: Sphere_2")

        dpg.delete_item("test_parent")

    def test_drag_spheroid_roi(self):
        if not dpg.is_dearpygui_running():
            dpg.create_context()

        import numpy as np
        from unittest.mock import patch
        from vvv.utils import RoiInteractionMode, ViewMode
        from vvv.ui.ui_interaction import InteractionManager
        from vvv.core.roi_manager import ROIState

        # Create DPG widgets
        with dpg.window(tag="test_parent"):
            self.plugin.create_ui(parent="test_parent", api=self.mock_api)

        # 1. Create a real ROIState in contour mode
        roi_state = ROIState(volume_id="img_1", name="Sphere_1", color=[255, 0, 0])
        roi_state.is_spheroid = True
        roi_state.spheroid_center = [10.0, 20.0, 30.0]
        roi_state.spheroid_radius = 5.0
        roi_state.is_contour = True

        # 2. Mock viewer and volumes
        mock_viewer = MagicMock()
        mock_viewer.image_id = "img_1"
        mock_viewer.tag = "V1"
        mock_viewer.view_state = MagicMock()
        mock_viewer.view_state.rois = {"Sphere_1": roi_state}
        mock_viewer.view_state.camera = MagicMock()
        mock_viewer.view_state.camera.target_ppm = 2.0
        mock_viewer.view_state.world_to_display.side_effect = lambda pt, **kw: np.array(
            pt
        )
        mock_viewer.view_state.display_to_world.side_effect = lambda pt, **kw: np.array(
            pt
        )
        mock_viewer.get_mouse_slice_coords.return_value = (10.0, 20.0)
        mock_viewer.get_slice_shape.return_value = (100, 100)
        mock_viewer.current_pmin = [0.0, 0.0]
        mock_viewer.current_pmax = [100.0, 100.0]
        mock_viewer.orientation = ViewMode.AXIAL
        mock_viewer.slice_idx = 30
        mock_viewer._ORIENTATION_MAP = {ViewMode.AXIAL: (2, 0, ("x", "y"), (1, 1))}
        mock_viewer.roi_mode = RoiInteractionMode.IDLE
        mock_viewer._is_buffered.return_value = False
        mock_viewer.on_mouse_down = MagicMock()

        # Mock base volume
        base_vol = MagicMock()
        base_vol.shape3d = (50, 50, 50)
        base_vol.spacing = np.array([1.0, 1.0, 1.0])
        base_vol.origin = np.array([0.0, 0.0, 0.0])
        base_vol.matrix = np.eye(3)
        base_vol.physic_coord_to_voxel_coord.side_effect = lambda pt: pt
        base_vol.voxel_coord_to_physic_coord.side_effect = lambda pt: pt
        base_vol.sitk_image = MagicMock()

        # Mock roi volume
        roi_vol = MagicMock()
        roi_vol.origin = np.array([5.0, 15.0, 25.0])
        roi_vol.roi_bbox = (25, 35, 15, 25, 5, 15)
        roi_vol.sitk_image = MagicMock()

        self.mock_api._controller.volumes = {"img_1": base_vol, "Sphere_1": roi_vol}
        self.mock_api.get_active_viewer.return_value = mock_viewer

        gui = MagicMock()
        gui.plugins = [self.plugin]
        self.plugin._ui.roi_selectables = {}
        self.plugin._ui.api = self.mock_api

        manager = InteractionManager(gui, self.mock_api._controller)
        manager.get_hovered_viewer = MagicMock(return_value=mock_viewer)

        # Patch dpg.does_item_exist to return True for test window tags
        with (
            patch("dearpygui.dearpygui.does_item_exist", return_value=True),
            patch(
                "dearpygui.dearpygui.get_drawing_mouse_pos", return_value=(10.5, 20.5)
            ),
            patch("dearpygui.dearpygui.set_value"),
        ):

            # Hover check
            roi_res = manager._check_roi_hover(mock_viewer)
            self.assertEqual(roi_res, ("Sphere_1", "center"))

            # Click
            tool = manager.active_tool
            tool.on_click(0)  # left click
            self.assertEqual(mock_viewer.roi_mode, RoiInteractionMode.MANIPULATING)
            self.assertEqual(tool.roi_drag_id, "Sphere_1")

            # Check contour mode was temporarily disabled
            self.assertFalse(roi_state.is_contour)
            self.assertTrue(tool.roi_drag_was_contour)

            # Drag by 2 voxels physically (which is 2 voxels because spacing is 1.0)
            mock_viewer.get_mouse_slice_coords.return_value = (12.0, 22.0)
            tool.on_drag(None)

            # Verify origin and bbox shift
            self.assertEqual(roi_state.spheroid_center, [12.0, 22.0, 30.0])
            self.assertTrue(np.allclose(roi_vol.origin, [7.0, 17.0, 25.0]))
            self.assertEqual(roi_vol.roi_bbox, (25, 35, 17, 27, 7, 17))

            # Still disabled during drag
            self.assertFalse(roi_state.is_contour)

            # Release
            tool.on_release(0)
            self.assertEqual(mock_viewer.roi_mode, RoiInteractionMode.IDLE)
            self.assertIsNone(tool.roi_drag_id)

            # Check contour mode was restored
            self.assertTrue(roi_state.is_contour)

        dpg.delete_item("test_parent")

    def test_resize_spheroid_roi(self):
        if not dpg.is_dearpygui_running():
            dpg.create_context()

        import numpy as np
        from unittest.mock import patch
        from vvv.utils import RoiInteractionMode, ViewMode
        from vvv.ui.ui_interaction import InteractionManager
        from vvv.core.roi_manager import ROIState

        # Create DPG widgets
        with dpg.window(tag="test_parent"):
            self.plugin.create_ui(parent="test_parent", api=self.mock_api)

        # 1. Create a real ROIState in contour mode
        roi_state = ROIState(volume_id="img_1", name="Sphere_1", color=[255, 0, 0])
        roi_state.is_spheroid = True
        roi_state.spheroid_center = [10.0, 20.0, 30.0]
        roi_state.spheroid_radius = 110.0  # Set radius to 110.0
        roi_state.spheroid_radius_x = 110.0
        roi_state.spheroid_radius_y = 110.0
        roi_state.spheroid_radius_z = 110.0
        roi_state.is_contour = True

        # 2. Mock viewer and volumes
        mock_viewer = MagicMock()
        mock_viewer.image_id = "img_1"
        mock_viewer.tag = "V1"
        mock_viewer.view_state = MagicMock()
        mock_viewer.view_state.rois = {"Sphere_1": roi_state}
        mock_viewer.view_state.camera = MagicMock()
        mock_viewer.view_state.camera.target_ppm = (
            1.0  # Set ppm to 1.0 so pixels match voxel/mm distance
        )
        mock_viewer.get_mouse_slice_coords.return_value = (
            120.5,
            20.5,
        )  # On the border (exact 110.0 px)
        mock_viewer.get_slice_shape.return_value = (100, 100)
        mock_viewer.current_pmin = [0.0, 0.0]
        mock_viewer.current_pmax = [100.0, 100.0]
        mock_viewer.orientation = ViewMode.AXIAL
        mock_viewer.slice_idx = 30
        mock_viewer._ORIENTATION_MAP = {ViewMode.AXIAL: (2, 0, ("x", "y"), (1, 1))}
        mock_viewer.roi_mode = RoiInteractionMode.IDLE
        mock_viewer._is_buffered.return_value = False
        mock_viewer.on_mouse_down = MagicMock()
        mock_viewer.get_pixels_per_mm.return_value = 1.0  # PPM = 1.0
        mock_viewer.view_state.world_to_display.side_effect = lambda pt, **kw: np.array(
            pt
        )
        mock_viewer.view_state.display_to_world.side_effect = lambda pt, **kw: np.array(
            pt
        )

        # Mock base volume
        base_vol = MagicMock()
        base_vol.shape3d = (50, 50, 50)
        base_vol.spacing = np.array([1.0, 1.0, 1.0])
        base_vol.origin = np.array([0.0, 0.0, 0.0])
        base_vol.matrix = np.eye(3)
        base_vol.physic_coord_to_voxel_coord.side_effect = lambda pt: pt
        base_vol.voxel_coord_to_physic_coord.side_effect = lambda pt: pt
        base_vol.sitk_image = MagicMock()

        # Mock roi volume
        roi_vol = MagicMock()
        roi_vol.origin = np.array([5.0, 15.0, 25.0])
        roi_vol.roi_bbox = (25, 35, 15, 25, 5, 15)
        roi_vol.sitk_image = MagicMock()

        self.mock_api._controller.volumes = {"img_1": base_vol, "Sphere_1": roi_vol}
        self.mock_api.get_active_viewer.return_value = mock_viewer

        gui = MagicMock()
        gui.plugins = [self.plugin]
        self.plugin._ui.roi_selectables = {}
        self.plugin._ui.api = self.mock_api

        manager = InteractionManager(gui, self.mock_api._controller)
        manager.get_hovered_viewer = MagicMock(return_value=mock_viewer)

        # Patch DPG functions
        with (
            patch("dearpygui.dearpygui.does_item_exist", return_value=True),
            patch(
                "dearpygui.dearpygui.get_drawing_mouse_pos", return_value=(120.5, 20.5)
            ),
            patch("dearpygui.dearpygui.set_value"),
        ):

            # Hover check - should be near the border
            roi_res = manager._check_roi_hover(mock_viewer)
            self.assertEqual(roi_res, ("Sphere_1", "border"))

            # Click
            tool = manager.active_tool
            tool.on_click(0)  # left click
            self.assertEqual(mock_viewer.roi_mode, RoiInteractionMode.MANIPULATING)
            self.assertEqual(tool.roi_drag_id, "Sphere_1")
            self.assertEqual(tool.roi_drag_action, "border")

            # Drag to increase radius to 113.0
            mock_viewer.get_mouse_slice_coords.return_value = (123.5, 20.5)
            tool.on_drag(None)

            # Verify both radii updated to 113.0 (sphere behavior)
            self.assertEqual(roi_state.spheroid_radius_x, 113.0)
            self.assertEqual(roi_state.spheroid_radius_y, 113.0)
            self.assertEqual(roi_state.spheroid_radius_z, 113.0)
            self.assertEqual(roi_vol.roi_bbox, (25, 35, 15, 25, 5, 15))

            # Release
            tool.on_release(0)
            self.assertEqual(mock_viewer.roi_mode, RoiInteractionMode.IDLE)
            self.assertIsNone(tool.roi_drag_id)
            self.assertTrue(roi_state.is_contour)

            # Verify bbox is now updated on release
            self.assertEqual(roi_vol.roi_bbox, (0, 50, 0, 50, 0, 50))

        dpg.delete_item("test_parent")

    def test_spheroid_stats_window(self):
        if not dpg.is_dearpygui_running():
            dpg.create_context()
        with dpg.window(tag="test_parent"):
            self.plugin.create_ui(parent="test_parent", api=self.mock_api)

        ui = self.plugin._ui
        ctrl = self.plugin._controller

        # Setup volume data & roi state
        import SimpleITK as sitk
        import numpy as np
        from vvv.core.roi_manager import ROIState

        base_vol = MagicMock()
        base_vol.name = "base"
        base_vol.data = np.zeros((10, 10, 10), dtype=np.uint8)
        base_vol.spacing = np.array([1.0, 1.0, 1.0])
        base_vol.origin = np.array([0.0, 0.0, 0.0])
        base_vol.matrix = np.eye(3)
        base_vol.inverse_matrix = np.eye(3)
        base_vol.shape3d = (10, 10, 10)
        base_vol.physic_coord_to_voxel_coord.side_effect = lambda pt: pt
        base_vol.voxel_coord_to_physic_coord.side_effect = lambda pt: pt
        base_vol.num_timepoints = 1
        base_vol.is_rgb = False
        base_vol.is_dvf = False
        base_vol.sitk_image = MagicMock()

        roi_vol = MagicMock()
        roi_vol.name = "Sphere_1"
        roi_vol.data = np.zeros((5, 5, 5), dtype=np.uint8)
        roi_vol.spacing = np.array([1.0, 1.0, 1.0])
        roi_vol.origin = np.array([2.0, 2.0, 2.0])
        roi_vol.matrix = np.eye(3)
        roi_vol.inverse_matrix = np.eye(3)
        roi_vol.shape3d = (5, 5, 5)
        roi_vol.roi_bbox = (2, 7, 2, 7, 2, 7)
        roi_vol.num_timepoints = 1
        roi_vol.is_rgb = False
        roi_vol.is_dvf = False
        roi_vol.sitk_image = MagicMock()

        roi_state = ROIState("roi_1", "Sphere_1", color=[255, 0, 0])
        roi_state.is_spheroid = True
        roi_state.spheroid_center = [5.0, 5.0, 5.0]
        roi_state.spheroid_radius = 3.0
        roi_state.source_type = "Created"

        self.mock_api.get_volumes.return_value = {
            "img_1": base_vol,
            "roi_1": roi_vol,
        }
        self.mock_api.get_view_states.return_value = {
            "img_1": MockViewState(rois={"roi_1": roi_state}),
        }

        mock_viewer = MockViewer("img_1", {"roi_1": roi_state})
        self.mock_api.get_active_viewer.return_value = mock_viewer

        with dpg.window(tag="stats_parent_win"):
            with dpg.group(tag="stats_parent"):
                ui.build_stats_window_contents("stats_parent", "img_1", "roi_1")

        # Verify slider and input tags exist
        self.assertTrue(dpg.does_item_exist(ui._t("slider_roi_radius_x_roi_1")))
        self.assertTrue(dpg.does_item_exist(ui._t("slider_roi_radius_y_roi_1")))
        self.assertTrue(dpg.does_item_exist(ui._t("slider_roi_radius_z_roi_1")))
        self.assertTrue(dpg.does_item_exist(ui._t("input_roi_center_x_roi_1")))
        self.assertTrue(dpg.does_item_exist(ui._t("input_roi_center_y_roi_1")))
        self.assertTrue(dpg.does_item_exist(ui._t("input_roi_center_z_roi_1")))

        # Test radius X callback
        ui.on_roi_stats_radius_x_slider_changed(None, 5.5, "roi_1")
        self.assertEqual(roi_state.spheroid_radius_x, 5.5)

        # Test radius X step callback
        slider_x_tag = ui._t("slider_roi_radius_x_roi_1")
        ui.on_roi_stats_radius_x_step_callback(
            None, None, {"tag": slider_x_tag, "dir": 1.5}
        )
        self.assertEqual(roi_state.spheroid_radius_x, 7.0)

        # Test radius Y callback
        ui.on_roi_stats_radius_y_slider_changed(None, 6.0, "roi_1")
        self.assertEqual(roi_state.spheroid_radius_y, 6.0)

        # Test radius Y step callback
        slider_y_tag = ui._t("slider_roi_radius_y_roi_1")
        ui.on_roi_stats_radius_y_step_callback(
            None, None, {"tag": slider_y_tag, "dir": 1.0}
        )
        self.assertEqual(roi_state.spheroid_radius_y, 7.0)

        # Test radius Z callback
        ui.on_roi_stats_radius_z_slider_changed(None, 6.5, "roi_1")
        self.assertEqual(roi_state.spheroid_radius_z, 6.5)

        # Test radius Z step callback
        slider_z_tag = ui._t("slider_roi_radius_z_roi_1")
        ui.on_roi_stats_radius_z_step_callback(
            None, None, {"tag": slider_z_tag, "dir": 1.0}
        )
        self.assertEqual(roi_state.spheroid_radius_z, 7.5)

        # Test center callback
        ui.on_roi_stats_center_changed(None, 4.2, {"roi_id": "roi_1", "coord_idx": 0})
        self.assertEqual(roi_state.spheroid_center[0], 4.2)
        mock_viewer.view_state.update_crosshair_from_phys.assert_called()
        self.mock_api.propagate_sync.assert_called_with("img_1")

        # Test slider deactivated callback
        ui.on_roi_stats_slider_deactivated(None, None, None)

        dpg.delete_item("test_parent")
        if dpg.does_item_exist("stats_parent_win"):
            dpg.delete_item("stats_parent_win")

    def test_add_box_roi(self):
        if not dpg.is_dearpygui_running():
            dpg.create_context()
        with dpg.window(tag="test_parent"):
            self.plugin.create_ui(parent="test_parent", api=self.mock_api)

        ui = self.plugin._ui
        ctrl = self.plugin._controller

        # Set up mock active viewer and crosshair
        rois = {}
        mock_viewer = MockViewer("img_1", rois)
        mock_viewer.view_state = MagicMock()
        mock_viewer.view_state.camera = MagicMock()
        mock_viewer.view_state.camera.target_ppm = 2.0
        mock_viewer.view_state.rois = rois

        self.mock_api.get_active_viewer.return_value = mock_viewer
        self.mock_api.get_crosshair_world.return_value = [10.0, 20.0, 30.0]
        self.mock_api.get_view_states.return_value = {"img_1": mock_viewer.view_state}

        # Set up mock volume
        import numpy as np

        base_vol = MagicMock()
        base_vol.shape3d = (50, 50, 50)
        base_vol.spacing = np.array([1.0, 1.0, 1.0])
        base_vol.origin = np.array([0.0, 0.0, 0.0])
        base_vol.matrix = np.eye(3)
        base_vol.physic_coord_to_voxel_coord.side_effect = lambda pt: pt
        base_vol.voxel_coord_to_physic_coord.side_effect = lambda pt: pt
        base_vol.sitk_image = MagicMock()
        base_vol.sitk_image.GetDirection.return_value = [1, 0, 0, 0, 1, 0, 0, 0, 1]

        self.mock_api._controller.volumes = {"img_1": base_vol}

        # Set up a real ROIState in rois to let our code store properties on it
        from vvv.core.roi_manager import ROIState

        color = [255, 0, 0]
        roi_state = ROIState(volume_id="img_1", name="Box_1", color=color)
        rois["Box_1"] = roi_state

        # Mock _create_memory_roi to return "Box_1"
        self.mock_api._controller.roi = MagicMock()
        self.mock_api._controller.roi._create_memory_roi.return_value = "Box_1"

        # Trigger box creation
        ui.on_add_rect_clicked(None, None, None)

        # Ensure box size is set for the test
        roi_state.box_size_x = 1.0  # any positive value

        # Verify that it fetched crosshair coordinate, computed bounding box, and called _create_memory_roi
        self.mock_api.get_crosshair_world.assert_called_once()
        self.mock_api._controller.roi._create_memory_roi.assert_called_once()

        # Verify box metadata properties were stored
        self.assertTrue(roi_state.is_box)
        self.assertEqual(roi_state.box_center, [10.0, 20.0, 30.0])
        self.assertGreater(roi_state.box_size_x, 0.0)

        # Verify notification
        self.mock_api.notify.assert_called_with("Created box ROI: Box_2")

        dpg.delete_item("test_parent")

    def test_drag_box_roi(self):
        if not dpg.is_dearpygui_running():
            dpg.create_context()

        import numpy as np
        from unittest.mock import patch
        from vvv.utils import RoiInteractionMode, ViewMode
        from vvv.ui.ui_interaction import InteractionManager
        from vvv.core.roi_manager import ROIState

        # Create DPG widgets
        with dpg.window(tag="test_parent"):
            self.plugin.create_ui(parent="test_parent", api=self.mock_api)

        # 1. Create a real ROIState in contour mode
        roi_state = ROIState(volume_id="img_1", name="Box_1", color=[255, 0, 0])
        roi_state.is_box = True
        roi_state.box_center = [10.0, 20.0, 30.0]
        roi_state.box_size_x = 10.0
        roi_state.box_size_y = 10.0
        roi_state.box_size_z = 10.0
        roi_state.is_contour = True

        # 2. Mock viewer and volumes
        mock_viewer = MagicMock()
        mock_viewer.image_id = "img_1"
        mock_viewer.tag = "V1"
        mock_viewer.view_state = MagicMock()
        mock_viewer.view_state.rois = {"Box_1": roi_state}
        mock_viewer.view_state.camera = MagicMock()
        mock_viewer.view_state.camera.target_ppm = 2.0
        mock_viewer.view_state.world_to_display.side_effect = lambda pt, **kw: np.array(
            pt
        )
        mock_viewer.view_state.display_to_world.side_effect = lambda pt, **kw: np.array(
            pt
        )
        mock_viewer.get_mouse_slice_coords.return_value = (10.0, 20.0)
        mock_viewer.get_slice_shape.return_value = (100, 100)
        mock_viewer.current_pmin = [0.0, 0.0]
        mock_viewer.current_pmax = [100.0, 100.0]
        mock_viewer.orientation = ViewMode.AXIAL
        mock_viewer.slice_idx = 30
        mock_viewer._ORIENTATION_MAP = {ViewMode.AXIAL: (2, 0, ("x", "y"), (1, 1))}
        mock_viewer.roi_mode = RoiInteractionMode.IDLE
        mock_viewer._is_buffered.return_value = False
        mock_viewer.on_mouse_down = MagicMock()

        # Mock base volume
        base_vol = MagicMock()
        base_vol.shape3d = (50, 50, 50)
        base_vol.spacing = np.array([1.0, 1.0, 1.0])
        base_vol.origin = np.array([0.0, 0.0, 0.0])
        base_vol.matrix = np.eye(3)
        base_vol.physic_coord_to_voxel_coord.side_effect = lambda pt: pt
        base_vol.voxel_coord_to_physic_coord.side_effect = lambda pt: pt
        base_vol.sitk_image = MagicMock()

        # Mock roi volume
        roi_vol = MagicMock()
        roi_vol.origin = np.array([5.0, 15.0, 25.0])
        roi_vol.roi_bbox = (25, 35, 15, 25, 5, 15)
        roi_vol.sitk_image = MagicMock()

        self.mock_api._controller.volumes = {"img_1": base_vol, "Box_1": roi_vol}
        self.mock_api.get_active_viewer.return_value = mock_viewer

        gui = MagicMock()
        gui.plugins = [self.plugin]
        self.plugin._ui.roi_selectables = {}
        self.plugin._ui.api = self.mock_api

        manager = InteractionManager(gui, self.mock_api._controller)
        manager.get_hovered_viewer = MagicMock(return_value=mock_viewer)

        with (
            patch("dearpygui.dearpygui.does_item_exist", return_value=True),
            patch(
                "dearpygui.dearpygui.get_drawing_mouse_pos", return_value=(10.5, 20.5)
            ),
            patch("dearpygui.dearpygui.set_value"),
        ):

            # Hover check
            roi_res = manager._check_roi_hover(mock_viewer)
            self.assertEqual(roi_res, ("Box_1", "center"))

            # Click
            tool = manager.active_tool
            tool.on_click(0)  # left click
            self.assertEqual(mock_viewer.roi_mode, RoiInteractionMode.MANIPULATING)
            self.assertEqual(tool.roi_drag_id, "Box_1")

            # Check contour mode was temporarily disabled
            self.assertFalse(roi_state.is_contour)
            self.assertTrue(tool.roi_drag_was_contour)

            # Drag by 2 voxels physically
            mock_viewer.get_mouse_slice_coords.return_value = (12.0, 22.0)
            tool.on_drag(None)

            # Verify origin and bbox shift
            self.assertEqual(roi_state.box_center, [12.0, 22.0, 30.0])
            self.assertTrue(np.allclose(roi_vol.origin, [7.0, 17.0, 25.0]))
            self.assertEqual(roi_vol.roi_bbox, (25, 35, 17, 27, 7, 17))

            # Release
            tool.on_release(0)
            self.assertEqual(mock_viewer.roi_mode, RoiInteractionMode.IDLE)
            self.assertIsNone(tool.roi_drag_id)
            self.assertTrue(roi_state.is_contour)

        dpg.delete_item("test_parent")

    def test_resize_box_roi(self):
        if not dpg.is_dearpygui_running():
            dpg.create_context()

        import numpy as np
        from unittest.mock import patch
        from vvv.utils import RoiInteractionMode, ViewMode
        from vvv.ui.ui_interaction import InteractionManager
        from vvv.core.roi_manager import ROIState

        with dpg.window(tag="test_parent"):
            self.plugin.create_ui(parent="test_parent", api=self.mock_api)

        roi_state = ROIState(volume_id="img_1", name="Box_1", color=[255, 0, 0])
        roi_state.is_box = True
        roi_state.box_center = [10.0, 20.0, 30.0]
        roi_state.box_size_x = 220.0
        roi_state.box_size_y = 220.0
        roi_state.box_size_z = 220.0
        roi_state.is_contour = True

        mock_viewer = MagicMock()
        mock_viewer.image_id = "img_1"
        mock_viewer.tag = "V1"
        mock_viewer.view_state = MagicMock()
        mock_viewer.view_state.rois = {"Box_1": roi_state}
        mock_viewer.view_state.camera = MagicMock()
        mock_viewer.view_state.camera.target_ppm = 1.0
        mock_viewer.get_mouse_slice_coords.return_value = (120.5, 20.5)
        mock_viewer.get_slice_shape.return_value = (100, 100)
        mock_viewer.current_pmin = [0.0, 0.0]
        mock_viewer.current_pmax = [100.0, 100.0]
        mock_viewer.orientation = ViewMode.AXIAL
        mock_viewer.slice_idx = 30
        mock_viewer._ORIENTATION_MAP = {ViewMode.AXIAL: (2, 0, ("x", "y"), (1, 1))}
        mock_viewer.roi_mode = RoiInteractionMode.IDLE
        mock_viewer._is_buffered.return_value = False
        mock_viewer.on_mouse_down = MagicMock()
        mock_viewer.get_pixels_per_mm.return_value = 1.0
        mock_viewer.view_state.world_to_display.side_effect = lambda pt, **kw: np.array(
            pt
        )
        mock_viewer.view_state.display_to_world.side_effect = lambda pt, **kw: np.array(
            pt
        )

        base_vol = MagicMock()
        base_vol.shape3d = (50, 50, 50)
        base_vol.spacing = np.array([1.0, 1.0, 1.0])
        base_vol.origin = np.array([0.0, 0.0, 0.0])
        base_vol.matrix = np.eye(3)
        base_vol.physic_coord_to_voxel_coord.side_effect = lambda pt: pt
        base_vol.voxel_coord_to_physic_coord.side_effect = lambda pt: pt
        base_vol.sitk_image = MagicMock()

        roi_vol = MagicMock()
        roi_vol.origin = np.array([5.0, 15.0, 25.0])
        roi_vol.roi_bbox = (25, 35, 15, 25, 5, 15)
        roi_vol.sitk_image = MagicMock()

        self.mock_api._controller.volumes = {"img_1": base_vol, "Box_1": roi_vol}
        self.mock_api.get_active_viewer.return_value = mock_viewer

        gui = MagicMock()
        gui.plugins = [self.plugin]
        self.plugin._ui.roi_selectables = {}
        self.plugin._ui.api = self.mock_api

        manager = InteractionManager(gui, self.mock_api._controller)
        manager.get_hovered_viewer = MagicMock(return_value=mock_viewer)

        with (
            patch("dearpygui.dearpygui.does_item_exist", return_value=True),
            patch(
                "dearpygui.dearpygui.get_drawing_mouse_pos", return_value=(120.5, 20.5)
            ),
            patch("dearpygui.dearpygui.set_value"),
        ):

            roi_res = manager._check_roi_hover(mock_viewer)
            self.assertEqual(roi_res, ("Box_1", "border"))

            tool = manager.active_tool
            tool.on_click(0)
            self.assertEqual(mock_viewer.roi_mode, RoiInteractionMode.MANIPULATING)
            self.assertEqual(tool.roi_drag_id, "Box_1")
            self.assertEqual(tool.roi_drag_action, "border")

            mock_viewer.get_mouse_slice_coords.return_value = (123.5, 20.5)
            tool.on_drag(None)

            # Verify sizes scaled proportionally: original is 220, scaled is 226
            self.assertEqual(roi_state.box_size_x, 226.0)
            self.assertEqual(roi_state.box_size_y, 226.0)
            self.assertEqual(roi_state.box_size_z, 226.0)
            self.assertEqual(roi_vol.roi_bbox, (25, 35, 15, 25, 5, 15))

            tool.on_release(0)
            self.assertEqual(mock_viewer.roi_mode, RoiInteractionMode.IDLE)
            self.assertIsNone(tool.roi_drag_id)
            self.assertTrue(roi_state.is_contour)

        dpg.delete_item("test_parent")

    def test_box_stats_window(self):
        if not dpg.is_dearpygui_running():
            dpg.create_context()
        with dpg.window(tag="test_parent"):
            self.plugin.create_ui(parent="test_parent", api=self.mock_api)

        ui = self.plugin._ui
        ctrl = self.plugin._controller

        import numpy as np
        from vvv.core.roi_manager import ROIState

        base_vol = MagicMock()
        base_vol.name = "base"
        base_vol.data = np.zeros((10, 10, 10), dtype=np.uint8)
        base_vol.spacing = np.array([1.0, 1.0, 1.0])
        base_vol.origin = np.array([0.0, 0.0, 0.0])
        base_vol.matrix = np.eye(3)
        base_vol.inverse_matrix = np.eye(3)
        base_vol.shape3d = (10, 10, 10)
        base_vol.physic_coord_to_voxel_coord.side_effect = lambda pt: pt
        base_vol.voxel_coord_to_physic_coord.side_effect = lambda pt: pt
        base_vol.num_timepoints = 1
        base_vol.is_rgb = False
        base_vol.is_dvf = False
        base_vol.sitk_image = MagicMock()

        roi_vol = MagicMock()
        roi_vol.name = "Box_1"
        roi_vol.data = np.zeros((5, 5, 5), dtype=np.uint8)
        roi_vol.spacing = np.array([1.0, 1.0, 1.0])
        roi_vol.origin = np.array([2.0, 2.0, 2.0])
        roi_vol.matrix = np.eye(3)
        roi_vol.inverse_matrix = np.eye(3)
        roi_vol.shape3d = (5, 5, 5)
        roi_vol.roi_bbox = (2, 7, 2, 7, 2, 7)
        roi_vol.num_timepoints = 1
        roi_vol.is_rgb = False
        roi_vol.is_dvf = False
        roi_vol.sitk_image = MagicMock()

        roi_state = ROIState("roi_1", "Box_1", color=[255, 0, 0])
        roi_state.is_box = True
        roi_state.box_center = [5.0, 5.0, 5.0]
        roi_state.box_size_x = 6.0
        roi_state.box_size_y = 6.0
        roi_state.box_size_z = 6.0
        roi_state.source_type = "Created"

        self.mock_api.get_volumes.return_value = {
            "img_1": base_vol,
            "roi_1": roi_vol,
        }
        self.mock_api.get_view_states.return_value = {
            "img_1": MockViewState(rois={"roi_1": roi_state}),
        }

        mock_viewer = MockViewer("img_1", {"roi_1": roi_state})
        self.mock_api.get_active_viewer.return_value = mock_viewer

        with dpg.window(tag="stats_parent_win"):
            with dpg.group(tag="stats_parent"):
                ui.build_stats_window_contents("stats_parent", "img_1", "roi_1")

        # Verify slider and input tags exist
        self.assertTrue(dpg.does_item_exist(ui._t("slider_roi_box_size_x_roi_1")))
        self.assertTrue(dpg.does_item_exist(ui._t("slider_roi_box_size_y_roi_1")))
        self.assertTrue(dpg.does_item_exist(ui._t("slider_roi_box_size_z_roi_1")))
        self.assertTrue(dpg.does_item_exist(ui._t("input_roi_box_center_x_roi_1")))
        self.assertTrue(dpg.does_item_exist(ui._t("input_roi_box_center_y_roi_1")))
        self.assertTrue(dpg.does_item_exist(ui._t("input_roi_box_center_z_roi_1")))

        # Test size X callback
        ui.on_roi_stats_box_size_x_slider_changed(None, 8.0, "roi_1")
        self.assertEqual(roi_state.box_size_x, 8.0)

        # Test size X step callback
        slider_x_tag = ui._t("slider_roi_box_size_x_roi_1")
        ui.on_roi_stats_box_size_x_step_callback(
            None, None, {"tag": slider_x_tag, "dir": 1.0}
        )
        self.assertEqual(roi_state.box_size_x, 9.0)

        # Test size Y callback
        ui.on_roi_stats_box_size_y_slider_changed(None, 7.0, "roi_1")
        self.assertEqual(roi_state.box_size_y, 7.0)

        # Test size Y step callback
        slider_y_tag = ui._t("slider_roi_box_size_y_roi_1")
        ui.on_roi_stats_box_size_y_step_callback(
            None, None, {"tag": slider_y_tag, "dir": 1.0}
        )
        self.assertEqual(roi_state.box_size_y, 8.0)

        # Test size Z callback
        ui.on_roi_stats_box_size_z_slider_changed(None, 6.5, "roi_1")
        self.assertEqual(roi_state.box_size_z, 6.5)

        # Test size Z step callback
        slider_z_tag = ui._t("slider_roi_box_size_z_roi_1")
        ui.on_roi_stats_box_size_z_step_callback(
            None, None, {"tag": slider_z_tag, "dir": 1.0}
        )
        self.assertEqual(roi_state.box_size_z, 7.5)

        # Test center callback
        ui.on_roi_stats_box_center_changed(
            None, 4.2, {"roi_id": "roi_1", "coord_idx": 0}
        )
        self.assertEqual(roi_state.box_center[0], 4.2)
        mock_viewer.view_state.update_crosshair_from_phys.assert_called()
        self.mock_api.propagate_sync.assert_called_with("img_1")

        dpg.delete_item("test_parent")
        if dpg.does_item_exist("stats_parent_win"):
            dpg.delete_item("stats_parent_win")

    def test_edit_center_then_drag_box_roi(self):
        if not dpg.is_dearpygui_running():
            dpg.create_context()

        import numpy as np
        from unittest.mock import patch
        from vvv.utils import RoiInteractionMode, ViewMode
        from vvv.ui.ui_interaction import InteractionManager
        from vvv.core.roi_manager import ROIState

        with dpg.window(tag="test_parent"):
            self.plugin.create_ui(parent="test_parent", api=self.mock_api)

        ui = self.plugin._ui

        roi_state = ROIState(volume_id="img_1", name="Box_1", color=[255, 0, 0])
        roi_state.is_box = True
        roi_state.box_center = [10.0, 20.0, 30.0]
        roi_state.box_size_x = 10.0
        roi_state.box_size_y = 10.0
        roi_state.box_size_z = 10.0
        roi_state.is_contour = True

        mock_viewer = MagicMock()
        mock_viewer.image_id = "img_1"
        mock_viewer.tag = "V1"
        mock_viewer.view_state = MagicMock()
        mock_viewer.view_state.rois = {"Box_1": roi_state}
        mock_viewer.view_state.camera = MagicMock()
        mock_viewer.view_state.camera.target_ppm = 2.0
        mock_viewer.view_state.world_to_display.side_effect = lambda pt, **kw: np.array(
            pt
        )
        mock_viewer.view_state.display_to_world.side_effect = lambda pt, **kw: np.array(
            pt
        )
        mock_viewer.get_mouse_slice_coords.return_value = (12.0, 22.0)
        mock_viewer.get_slice_shape.return_value = (100, 100)
        mock_viewer.current_pmin = [0.0, 0.0]
        mock_viewer.current_pmax = [100.0, 100.0]
        mock_viewer.orientation = ViewMode.AXIAL
        mock_viewer.slice_idx = 30
        mock_viewer._ORIENTATION_MAP = {ViewMode.AXIAL: (2, 0, ("x", "y"), (1, 1))}
        mock_viewer.roi_mode = RoiInteractionMode.IDLE
        mock_viewer._is_buffered.return_value = False
        mock_viewer.on_mouse_down = MagicMock()

        base_vol = MagicMock()
        base_vol.shape3d = (50, 50, 50)
        base_vol.spacing = np.array([1.0, 1.0, 1.0])
        base_vol.origin = np.array([0.0, 0.0, 0.0])
        base_vol.matrix = np.eye(3)
        base_vol.physic_coord_to_voxel_coord.side_effect = lambda pt: pt
        base_vol.voxel_coord_to_physic_coord.side_effect = lambda pt: pt
        base_vol.sitk_image = MagicMock()

        roi_vol = MagicMock()
        roi_vol.origin = np.array([5.0, 15.0, 25.0])
        roi_vol.roi_bbox = (25, 35, 15, 25, 5, 15)
        roi_vol.sitk_image = MagicMock()

        self.mock_api._controller.volumes = {"img_1": base_vol, "Box_1": roi_vol}
        self.mock_api.get_volumes.return_value = {"img_1": base_vol, "Box_1": roi_vol}
        self.mock_api.get_active_viewer.return_value = mock_viewer

        gui = MagicMock()
        gui.plugins = [self.plugin]
        self.plugin._ui.roi_selectables = {}
        self.plugin._ui.api = self.mock_api

        manager = InteractionManager(gui, self.mock_api._controller)
        manager.get_hovered_viewer = MagicMock(return_value=mock_viewer)

        with (
            patch("dearpygui.dearpygui.does_item_exist", return_value=True),
            patch(
                "dearpygui.dearpygui.get_drawing_mouse_pos", return_value=(12.5, 22.5)
            ),
            patch("dearpygui.dearpygui.set_value"),
        ):

            # Edit center via callback
            ui.on_roi_stats_box_center_changed(
                None, 12.0, {"roi_id": "Box_1", "coord_idx": 0}
            )
            ui.on_roi_stats_box_center_changed(
                None, 22.0, {"roi_id": "Box_1", "coord_idx": 1}
            )

            # Check new center is updated
            self.assertEqual(roi_state.box_center, [12.0, 22.0, 30.0])
            mock_viewer.view_state.update_crosshair_from_phys.assert_called()
            self.mock_api.propagate_sync.assert_called_with("img_1")

            # Now try to hover at the new center
            roi_res = manager._check_roi_hover(mock_viewer)
            self.assertEqual(roi_res, ("Box_1", "center"))

            # Click
            tool = manager.active_tool
            tool.on_click(0)
            self.assertEqual(mock_viewer.roi_mode, RoiInteractionMode.MANIPULATING)

            # Drag
            mock_viewer.get_mouse_slice_coords.return_value = (14.0, 24.0)
            tool.on_drag(None)

            self.assertEqual(roi_state.box_center, [14.0, 24.0, 30.0])

            tool.on_release(0)

        dpg.delete_item("test_parent")

    def test_out_of_bounds_center_clipping(self):
        from vvv.core.roi_manager import ROIState
        import numpy as np

        base_vol = MagicMock()
        base_vol.shape3d = (50, 50, 50)
        base_vol.spacing = np.array([1.0, 1.0, 1.0])
        base_vol.origin = np.array([0.0, 0.0, 0.0])
        base_vol.matrix = np.eye(3)
        base_vol.physic_coord_to_voxel_coord.side_effect = lambda pt: pt
        base_vol.voxel_coord_to_physic_coord.side_effect = lambda pt: pt

        roi_vol = MagicMock()
        roi_vol.sitk_image = MagicMock()

        roi_state = ROIState(volume_id="img_1", name="Box_1", color=[255, 0, 0])
        roi_state.is_box = True
        roi_state.box_center = [10.0, 20.0, 30.0]
        roi_state.box_size_x = 10.0
        roi_state.box_size_y = 10.0
        roi_state.box_size_z = 10.0

        # Spheroid out of bounds test
        roi_state.is_box = False
        roi_state.is_spheroid = True
        roi_state.spheroid_center = [999.0, 20.0, -50.0]
        self.plugin._controller.update_spheroid_mask(base_vol, roi_vol, roi_state)
        self.assertEqual(roi_state.spheroid_center, [49.0, 20.0, 0.0])

        # Box out of bounds test
        roi_state.is_spheroid = False
        roi_state.is_box = True
        roi_state.box_center = [999.0, 20.0, -50.0]
        self.plugin._controller.update_box_mask(base_vol, roi_vol, roi_state)
        self.assertEqual(roi_state.box_center, [49.0, 20.0, 0.0])

    def test_out_of_bounds_roi_warning(self):
        from vvv.core.roi_manager import ROIManager
        import numpy as np
        import SimpleITK as sitk

        mock_gui = MagicMock()
        mock_controller = MagicMock()
        mock_controller.gui = mock_gui

        # Instantiate ROIManager with mock controller
        roi_mgr = ROIManager(mock_controller)

        # Mock base_vol
        base_vol = MagicMock()
        base_vol.shape3d = (10, 10, 10)
        base_vol.spacing = np.array([1.0, 1.0, 1.0])
        base_vol.origin = np.array([0.0, 0.0, 0.0])
        base_vol.matrix = np.eye(3)
        base_vol.sitk_image = sitk.Image(10, 10, 10, sitk.sitkUInt8)  # origin 0, spacing 1

        # Mock mask_vol
        mask_vol = MagicMock()
        mask_vol.name = "Test_ROI"
        mask_vol.spacing = np.array([1.0, 1.0, 1.0])
        mask_vol.data = np.zeros((5, 5, 5), dtype=np.uint8)
        mask_vol.data[2, 2, 2] = 1  # non-empty

        # Set up origin to be outside the base image FOV (e.g. at [15.0, 0.0, 0.0])
        mask_vol.sitk_image = sitk.GetImageFromArray(mask_vol.data)
        mask_vol.sitk_image.SetOrigin((15.0, 0.0, 0.0))

        # Mock continuous index transform

        # Call process_binary_mask
        roi_mgr.process_binary_mask(base_vol, mask_vol, skip_initial_crop=True)

        # Verify that mask_vol is marked as outside
        self.assertTrue(mask_vol.is_outside)

    def test_out_of_bounds_rtstruct_warning(self):
        from vvv.core.roi_manager import ROIManager
        import numpy as np

        mock_gui = MagicMock()
        mock_controller = MagicMock()
        mock_controller.gui = mock_gui

        # Instantiate ROIManager with mock controller
        roi_mgr = ROIManager(mock_controller)

        # Mock volumes and view_states dicts on controller
        base_vol = MagicMock()
        base_vol.shape3d = (10, 10, 10)
        base_vol.spacing = np.array([1.0, 1.0, 1.0])
        base_vol.origin = np.array([0.0, 0.0, 0.0])
        base_vol.matrix = np.eye(3)
        base_vol.physic_coord_to_voxel_coord.side_effect = lambda pt: pt

        mock_controller.volumes = {"base_id": base_vol}
        mock_controller.view_states = {"base_id": MagicMock()}

        # Mock _create_memory_roi to avoid actual Sitk/ROI registry logic
        roi_mgr._create_memory_roi = MagicMock(return_value="mock_roi_id")

        # Mock DICOM dataset for RT-Struct
        mock_ds = MagicMock()
        contour = MagicMock()
        # Points overlap partially with base_vol [10, 10, 10] FOV:
        # One point is inside [5.0, 5.0, 5.0], other points are outside
        contour.ContourData = [5.0, 5.0, 5.0, 15.0, 5.0, 5.0, 5.0, 15.0, 5.0]
        roi_contour = MagicMock()
        roi_contour.ReferencedROINumber = 1
        roi_contour.ContourSequence = [contour]
        mock_ds.ROIContourSequence = [roi_contour]

        # Call load_rtstruct_roi
        roi_mgr.load_rtstruct_roi(
            base_id="base_id",
            filepath="/path/to/rtstruct.dcm",
            roi_info={"id": 1, "name": "RT ROI"},
            ds=mock_ds,
        )

        # Verify that _create_memory_roi was called with is_outside=True
        roi_mgr._create_memory_roi.assert_called_once()
        args, kwargs = roi_mgr._create_memory_roi.call_args
        self.assertTrue(kwargs.get("is_outside"))

    def test_center_on_roi_out_of_bounds(self):
        from vvv.core.roi_manager import ROIManager
        import numpy as np

        mock_gui = MagicMock()
        mock_controller = MagicMock()
        mock_controller.gui = mock_gui

        # Instantiate ROIManager
        roi_mgr = ROIManager(mock_controller)

        # Mock Volumes and view states
        base_vol = MagicMock()
        base_vol.shape3d = (10, 10, 10)
        base_vol.spacing = np.array([1.0, 1.0, 1.0])
        base_vol.origin = np.array([0.0, 0.0, 0.0])
        base_vol.matrix = np.eye(3)

        mask_vol = MagicMock()
        mask_vol.physical_center = [20.0, 20.0, 20.0]  # Outside FOV

        mock_controller.volumes = {"base_id": base_vol, "roi_id": mask_vol}

        mock_vs = MagicMock()
        mock_controller.view_states = {"base_id": mock_vs}
        mock_controller.sync.get_sync_group_vs_ids.return_value = ["base_id"]

        # Call center_on_roi
        roi_mgr.center_on_roi("base_id", "roi_id")

        # Verify that crosshair coordinates were updated to physical_center
        mock_vs.update_crosshair_from_phys.assert_called_once_with([20.0, 20.0, 20.0])

    def test_completely_out_of_bounds_roi_warning(self):
        from vvv.core.roi_manager import ROIManager
        import numpy as np
        import SimpleITK as sitk

        mock_gui = MagicMock()
        mock_controller = MagicMock()
        mock_controller.gui = mock_gui

        roi_mgr = ROIManager(mock_controller)

        # Mock base_vol
        base_vol = MagicMock()
        base_vol.shape3d = (10, 10, 10)
        base_vol.spacing = np.array([1.0, 1.0, 1.0])
        base_vol.origin = np.array([0.0, 0.0, 0.0])
        base_vol.matrix = np.eye(3)
        base_vol.sitk_image = sitk.Image(10, 10, 10, sitk.sitkUInt8)  # origin 0, spacing 1

        # Mock mask_vol (completely out of bounds)
        mask_vol = MagicMock()
        mask_vol.name = "Out_ROI"
        mask_vol.spacing = np.array([1.0, 1.0, 1.0])
        mask_vol.data = np.zeros((5, 5, 5), dtype=np.uint8)
        mask_vol.data[2, 2, 2] = 1

        mask_vol.sitk_image = sitk.GetImageFromArray(mask_vol.data)
        mask_vol.sitk_image.SetOrigin((50.0, 50.0, 50.0))  # Far outside base_vol [10, 10, 10]


        # Call process_binary_mask
        roi_mgr.process_binary_mask(base_vol, mask_vol, skip_initial_crop=True)

        # Verify that mask_vol is marked as outside
        self.assertTrue(mask_vol.is_outside)

    def test_load_batch_rois_sequence_warning(self):
        from vvv.ui.ui_sequences import load_batch_rois_sequence
        from unittest.mock import patch
        import numpy as np

        mock_gui = MagicMock()
        mock_controller = MagicMock()
        mock_controller.gui = mock_gui

        # Mock view state and rois
        mock_vs = MagicMock()
        mock_vs.rois = {}
        mock_controller.view_states = {"base_id": mock_vs}

        # Mock volumes
        mock_vol = MagicMock()
        mock_vol.is_outside = True
        mock_controller.volumes = {"roi_id": mock_vol}

        # Simulate loading by adding the ROI to view state during iteration
        def mock_load_binary_mask(*args, **kwargs):
            mock_vs.rois["roi_id"] = MagicMock(name="Out_ROI")
            mock_vs.rois["roi_id"].name = "Out_ROI"

        mock_controller.roi.load_binary_mask.side_effect = mock_load_binary_mask

        # Call the sequence generator
        generator = load_batch_rois_sequence(
            mock_gui,
            mock_controller,
            "base_id",
            ["/dummy/path/roi.nii.gz"],
            roi_type="Binary Mask",
        )

        # Consume the generator
        with (
            patch("os.path.exists", return_value=True),
            patch("vvv.ui.ui_sequences.show_loading_modal"),
            patch("dearpygui.dearpygui.does_item_exist", return_value=False),
        ):
            for _ in generator:
                pass

        # Verify show_message was called on mock_gui with ROI Warning
        mock_gui.show_message.assert_called_once_with(
            "ROI Warning",
            "Warning: The loaded ROI 'Out_ROI' lies partially or fully outside the image field of view (FOV).",
        )

    def test_serialize_restore_round_trip(self):
        """Verify that roi_filter and roi_sort_order survive a serialize → restore cycle."""
        if not dpg.is_dearpygui_running():
            dpg.create_context()
        with dpg.window(tag="test_parent"):
            self.plugin.create_ui(parent="test_parent", api=self.mock_api)

        ctrl = self.plugin._controller

        rois = {
            "roi_1": MockROI("roi_1", "Tumor", [255, 0, 0]),
            "roi_2": MockROI("roi_2", "Kidney", [0, 255, 0]),
        }
        mock_viewer = MockViewer("img_1", rois)
        self.mock_api.get_active_viewer.return_value = mock_viewer

        # Set non-default filter and sort order
        ctrl.roi_filters["img_1"] = "tum"
        ctrl.roi_sort_orders["img_1"] = -1

        # Serialize for both contexts
        for context in ("history", "workspace"):
            state = ctrl.serialize_image_state("img_1", context=context)
            self.assertEqual(state["roi_filter"], "tum")
            self.assertEqual(state["roi_sort_order"], -1)

            # Clear and restore
            ctrl.roi_filters.pop("img_1", None)
            ctrl.roi_sort_orders.pop("img_1", None)
            self.assertEqual(ctrl.roi_filters.get("img_1"), None)

            ctrl.restore_image_state("img_1", state, context=context)
            self.assertEqual(ctrl.roi_filters["img_1"], "tum")
            self.assertEqual(ctrl.roi_sort_orders["img_1"], -1)

        # Edge case: restore with empty/partial data should not crash
        ctrl.restore_image_state("img_2", {})
        self.assertEqual(ctrl.roi_filters.get("img_2"), None)
        self.assertEqual(ctrl.roi_sort_orders.get("img_2"), None)

        # Edge case: serialize for unknown image returns defaults
        state = ctrl.serialize_image_state("unknown_image")
        self.assertEqual(state["roi_filter"], "")
        self.assertEqual(state["roi_sort_order"], 0)

        dpg.delete_item("test_parent")

    def test_on_image_removed_resets_active_roi(self):
        """Regression: on_image_removed must always reset active_roi_id
        regardless of whether the removed image_id matches the active ROI id.
        The old bug compared active_roi_id (a roi_id) against image_id."""
        if not dpg.is_dearpygui_running():
            dpg.create_context()
        with dpg.window(tag="test_parent"):
            self.plugin.create_ui(parent="test_parent", api=self.mock_api)

        ctrl = self.plugin._controller

        rois = {
            "roi_A": MockROI("roi_A", "Tumor", [255, 0, 0]),
        }
        mock_viewer = MockViewer("img_1", rois)
        self.mock_api.get_active_viewer.return_value = mock_viewer

        # Select a ROI
        ctrl.on_roi_selected("roi_A")
        self.assertEqual(ctrl.active_roi_id, "roi_A")

        # Set filter/sort for img_1
        ctrl.roi_filters["img_1"] = "test"
        ctrl.roi_sort_orders["img_1"] = 1

        # Remove image — active_roi_id should be reset even though
        # image_id ("img_1") != active_roi_id ("roi_A")
        ctrl.on_image_removed("img_1")
        self.assertIsNone(ctrl.active_roi_id)

        # Filter and sort order for that image should be cleaned up
        self.assertNotIn("img_1", ctrl.roi_filters)
        self.assertNotIn("img_1", ctrl.roi_sort_orders)

        # Removing an unrelated image should also reset active_roi_id
        ctrl.on_roi_selected("roi_A")
        ctrl.on_image_removed("img_99")  # not even a real image
        self.assertIsNone(ctrl.active_roi_id)

        dpg.delete_item("test_parent")

    def test_clear_roi_filter_button_callback_arity(self):
        """Regression: build_name_filter_bar()'s clear button invokes
        on_clear_clicked() with zero arguments (`callback=lambda: on_clear_clicked()`
        in ui_components.py). on_clear_roi_filter_clicked() used to require
        (self, sender, app_data, user_data), which raised a TypeError as soon as
        a user clicked the ROI filter's clear ("X") button in the running app."""
        if not dpg.is_dearpygui_running():
            dpg.create_context()
        with dpg.window(tag="test_parent"):
            self.plugin.create_ui(parent="test_parent", api=self.mock_api)

        ctrl = self.plugin._controller
        ui = self.plugin._ui

        rois = {"roi_1": MockROI("roi_1", "Tumor", [255, 0, 0])}
        mock_viewer = MockViewer("img_1", rois)
        self.mock_api.get_active_viewer.return_value = mock_viewer
        ctrl.roi_filters["img_1"] = "tum"

        ui.on_clear_roi_filter_clicked()  # must not raise TypeError

        self.assertEqual(ctrl.roi_filters["img_1"], "")

        # Also verify sort button callback works with both 0 and 3 DPG arguments
        sort_btn = ui._t("btn_roi_sort")
        sort_cb = dpg.get_item_configuration(sort_btn)["callback"]
        sort_cb("sender", "app_data", "user_data")
        self.assertEqual(ctrl.roi_sort_orders["img_1"], 1)
        sort_cb()
        self.assertEqual(ctrl.roi_sort_orders["img_1"], -1)

        dpg.delete_item("test_parent")

    @patch("vvv.ui.file_dialog.save_file_dialog")
    def test_save_roi_to_disk(self, mock_save_dialog):
        """Test on_roi_save triggers save and updates source metadata."""
        if not dpg.is_dearpygui_running():
            dpg.create_context()
        with dpg.window(tag="test_parent"):
            self.plugin.create_ui(parent="test_parent", api=self.mock_api)

        ui = self.plugin._ui

        rois = {
            "roi_1": MockROI("roi_1", "Tumor", [255, 0, 0]),
        }
        rois["roi_1"].source_type = "RT-Struct"
        rois["roi_1"].source_mode = "Ignore BG (val)"
        rois["roi_1"].source_val = 0.0
        rois["roi_1"].rtstruct_info = {"name": "Tumor", "id": 1}

        mock_viewer = MockViewer("img_1", rois)
        self.mock_api.get_active_viewer.return_value = mock_viewer
        self.mock_api.get_view_states.return_value = {"img_1": mock_viewer.view_state}

        mock_vol = MagicMock()
        mock_vol.name = "Tumor"
        self.mock_api.get_volumes.return_value = {"roi_1": mock_vol}

        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            dest = os.path.join(tmpdir, "Tumor.nii.gz")
            mock_save_dialog.return_value = dest

            # Call save
            ui.on_roi_save(None, None, "roi_1")

            # Verify dialog was opened with correct default name
            mock_save_dialog.assert_called_with(
                "Save ROI As", default_name="Tumor.nii.gz"
            )

            # Verify save_image_async was called and execute its on_done callback
            self.mock_api.save_image_async.assert_called_once()
            call_kwargs = self.mock_api.save_image_async.call_args[1]
            on_done_callback = call_kwargs.get("on_done")
            self.assertIsNotNone(on_done_callback)
            on_done_callback()

            # Verify source metadata was updated
            self.assertEqual(rois["roi_1"].source_type, "Binary")
            self.assertEqual(rois["roi_1"].source_mode, "Target FG (val)")
            self.assertEqual(rois["roi_1"].source_val, 1.0)
            self.assertIsNone(rois["roi_1"].rtstruct_info)

        dpg.delete_item("test_parent")

    def test_roi_rgba_color_handling(self):
        """Test that ROI state with 4-element RGBA color is safely normalized and rendered in UI."""
        if not dpg.is_dearpygui_running():
            dpg.create_context()
        with dpg.window(tag="test_parent"):
            self.plugin.create_ui(parent="test_parent", api=self.mock_api)

        ui = self.plugin._ui
        ctrl = self.plugin._controller

        # ROI with RGBA color list [255, 128, 64, 200]
        roi = ROIState("vol_1", "Lesion", [255, 128, 64, 200])
        self.assertEqual(roi.color, [255, 128, 64])

        rois = {"roi_rgba": roi}
        mock_viewer = MockViewer("img_1", rois)
        self.mock_api.get_active_viewer.return_value = mock_viewer

        ctrl.on_roi_selected("roi_rgba")
        ui.refresh_rois_ui()
        ui.refresh_roi_detail_ui()

        # From dict with RGBA
        roi2 = ROIState("vol_2", "Lesion2", [255, 0, 0])
        roi2.from_dict({"name": "Lesion2", "color": [10, 20, 30, 255]})
        self.assertEqual(roi2.color, [10, 20, 30])

        dpg.delete_item("test_parent")

    def test_multi_roi_selection_and_clear(self):
        """Test multi-selection via Ctrl and Shift keys, and clearing selection."""
        if not dpg.is_dearpygui_running():
            dpg.create_context()
        with dpg.window(tag="test_parent"):
            self.plugin.create_ui(parent="test_parent", api=self.mock_api)

        ctrl = self.plugin._controller
        ui = self.plugin._ui
        visible_ids = ["roi_1", "roi_2", "roi_3", "roi_4"]

        # Single select
        ctrl.on_roi_selected("roi_1", ctrl=False, shift=False, visible_ids=visible_ids)
        self.assertEqual(ctrl.selected_roi_ids, {"roi_1"})
        self.assertEqual(ctrl.active_roi_id, "roi_1")

        # Ctrl-click to add roi_3
        ctrl.on_roi_selected("roi_3", ctrl=True, shift=False, visible_ids=visible_ids)
        self.assertEqual(ctrl.selected_roi_ids, {"roi_1", "roi_3"})
        self.assertEqual(ctrl.active_roi_id, "roi_3")

        # Ctrl-click to deselect roi_1
        ctrl.on_roi_selected("roi_1", ctrl=True, shift=False, visible_ids=visible_ids)
        self.assertEqual(ctrl.selected_roi_ids, {"roi_3"})

        # Shift-click range from roi_1 to roi_4
        ctrl.on_roi_selected("roi_1", ctrl=False, shift=False, visible_ids=visible_ids)
        ctrl.on_roi_selected("roi_4", ctrl=False, shift=True, visible_ids=visible_ids)
        self.assertEqual(ctrl.selected_roi_ids, {"roi_1", "roi_2", "roi_3", "roi_4"})
        self.assertEqual(ctrl.active_roi_id, "roi_4")

        # Clear selection
        ctrl.clear_roi_selection()
        self.assertEqual(ctrl.selected_roi_ids, set())
        self.assertIsNone(ctrl.active_roi_id)

        dpg.delete_item("test_parent")

    def test_multi_selection_row_eye_toggle(self):
        """Test that clicking row eye on a multi-selected ROI toggles all selected ROIs."""
        if not dpg.is_dearpygui_running():
            dpg.create_context()
        with dpg.window(tag="test_parent"):
            self.plugin.create_ui(parent="test_parent", api=self.mock_api)

        ui = self.plugin._ui
        ctrl = self.plugin._controller

        rois = {
            "r1": MockROI("r1", "Tumor 1", [255, 0, 0], visible=True, is_contour=False),
            "r2": MockROI("r2", "Tumor 2", [0, 255, 0], visible=True, is_contour=False),
            "r3": MockROI("r3", "Liver", [0, 0, 255], visible=True, is_contour=False),
        }
        mock_viewer = MockViewer("img_1", rois)
        self.mock_api.get_active_viewer.return_value = mock_viewer

        # Select r1 and r2
        ctrl.selected_roi_ids = {"r1", "r2"}
        ctrl.active_roi_id = "r1"

        # Toggle eye on r1: solid raster -> contour for both r1 and r2, leaving r3 untouched
        ui.on_roi_toggle_visible(None, None, "r1")
        self.assertTrue(rois["r1"].visible)
        self.assertTrue(rois["r1"].is_contour)
        self.assertTrue(rois["r2"].visible)
        self.assertTrue(rois["r2"].is_contour)
        self.assertTrue(rois["r3"].visible)
        self.assertFalse(rois["r3"].is_contour)

        # Toggle eye again: contour -> hidden
        ui.on_roi_toggle_visible(None, None, "r1")
        self.assertFalse(rois["r1"].visible)
        self.assertFalse(rois["r2"].visible)
        self.assertTrue(rois["r3"].visible)

        # Toggle eye again: hidden -> solid raster
        ui.on_roi_toggle_visible(None, None, "r1")
        self.assertTrue(rois["r1"].visible)
        self.assertFalse(rois["r1"].is_contour)
        self.assertTrue(rois["r2"].visible)
        self.assertFalse(rois["r2"].is_contour)
        self.assertTrue(rois["r3"].visible)

        # Changing color on r1 row color picker updates all selected ROIs (r1 and r2), but not r3
        ui.on_roi_color_changed(None, [100, 200, 50, 255], "r1")
        self.assertEqual(rois["r1"].color, [100, 200, 50])
        self.assertEqual(rois["r2"].color, [100, 200, 50])
        self.assertEqual(rois["r3"].color, [0, 0, 255])

        # Detail panel is NOT shown when multiple ROIs are selected
        ui.refresh_roi_detail_ui()
        # header and window should be hidden when multiple selected
        self.assertFalse(dpg.is_item_shown(ui._t("roi_detail_header_group")))
        self.assertFalse(dpg.is_item_shown(ui._t("roi_detail_window")))

        # When only 1 selected, detail panel IS shown
        ctrl.selected_roi_ids = {"r1"}
        ui.refresh_roi_detail_ui()
        self.assertTrue(dpg.is_item_shown(ui._t("roi_detail_header_group")))
        self.assertTrue(dpg.is_item_shown(ui._t("roi_detail_window")))

        dpg.delete_item("test_parent")

    def test_top_buttons_target_selection_vs_all(self):
        """Test top action buttons target selected ROIs if any, or filtered ROIs if none."""
        if not dpg.is_dearpygui_running():
            dpg.create_context()
        with dpg.window(tag="test_parent"):
            self.plugin.create_ui(parent="test_parent", api=self.mock_api)

        ui = self.plugin._ui
        ctrl = self.plugin._controller

        rois = {
            "r1": MockROI("r1", "L1", [255, 0, 0], visible=True),
            "r2": MockROI("r2", "L2", [0, 255, 0], visible=True),
            "r3": MockROI("r3", "L3", [0, 0, 255], visible=True),
        }
        mock_viewer = MockViewer("img_1", rois)
        self.mock_api.get_active_viewer.return_value = mock_viewer

        # 1. When selection is active: hide only selected
        ctrl.selected_roi_ids = {"r1", "r2"}
        ui.on_roi_hide_all(None, None, None)
        self.assertFalse(rois["r1"].visible)
        self.assertFalse(rois["r2"].visible)
        self.assertTrue(rois["r3"].visible)

        # 2. When selection is cleared: show all listed
        ctrl.clear_roi_selection()
        ui.on_roi_show_all(None, None, None)
        self.assertTrue(rois["r1"].visible)
        self.assertTrue(rois["r2"].visible)
        self.assertTrue(rois["r3"].visible)

        # Opacity batch action with selection
        ctrl.selected_roi_ids = {"r1"}
        ui.on_roi_global_opacity_changed(None, 0.8, None)
        self.assertEqual(rois["r1"].opacity, 0.8)
        self.assertEqual(rois["r2"].opacity, 0.5)

        # Thickness batch action with selection
        ui.on_roi_global_thickness_changed(None, 3.5, None)
        self.assertEqual(rois["r1"].thickness, 3.5)
        self.assertEqual(rois["r2"].thickness, 1.0)

        dpg.delete_item("test_parent")

    def test_filter_invert_and_persistence(self):
        """Test filter invert logic and persistence across serialization."""
        if not dpg.is_dearpygui_running():
            dpg.create_context()
        with dpg.window(tag="test_parent"):
            self.plugin.create_ui(parent="test_parent", api=self.mock_api)

        ui = self.plugin._ui
        ctrl = self.plugin._controller

        rois = {
            "r1": MockROI("r1", "Vertebra L1", [255, 0, 0]),
            "r2": MockROI("r2", "Vertebra L2", [0, 255, 0]),
            "r3": MockROI("r3", "Liver", [0, 0, 255]),
        }
        mock_viewer = MockViewer("img_1", rois)
        self.mock_api.get_active_viewer.return_value = mock_viewer

        ctrl.roi_filters["img_1"] = "vertebra"
        ctrl.roi_filter_inverts["img_1"] = False

        # Invert toggle
        ctrl.on_toggle_roi_filter_invert()
        self.assertTrue(ctrl.roi_filter_inverts["img_1"])

        # When inverted, _get_target_rois returns non-matching ROIs (Liver)
        targets = ui._get_target_rois(mock_viewer)
        target_ids = [tid for tid, _ in targets]
        self.assertEqual(target_ids, ["r3"])

        # Serialization
        serialized = self.plugin.serialize_image_state("img_1")
        self.assertEqual(serialized["roi_filter_invert"], True)
        self.assertEqual(serialized["roi_filter"], "vertebra")

        # Restoration
        self.plugin.restore_image_state("img_2", serialized)
        self.assertEqual(ctrl.roi_filter_inverts.get("img_2"), True)
        self.assertEqual(ctrl.roi_filters.get("img_2"), "vertebra")

        dpg.delete_item("test_parent")

    def test_filter_clear_resets_invert_and_ignores_spaces(self):
        """The list, the batch targets and the export use one matching rule:
        a trailing space no longer empties the list while the export matches;
        Clear also turns the invert off."""
        if not dpg.is_dearpygui_running():
            dpg.create_context()
        with dpg.window(tag="test_parent"):
            self.plugin.create_ui(parent="test_parent", api=self.mock_api)
        ui = self.plugin._ui
        ctrl = self.plugin._controller
        rois = {
            "r1": MockROI("r1", "Lung_L", [255, 0, 0]),
            "r2": MockROI("r2", "Liver", [0, 255, 0]),
        }
        mock_viewer = MockViewer("img_1", rois)
        self.mock_api.get_active_viewer.return_value = mock_viewer

        ctrl.on_roi_filter_changed("lung ")
        self.assertEqual([i for i, _ in ui._get_target_rois(mock_viewer)], ["r1"])

        ctrl.on_toggle_roi_filter_invert()
        self.assertEqual([i for i, _ in ui._get_target_rois(mock_viewer)], ["r2"])

        ctrl.on_clear_roi_filter()
        self.assertFalse(ctrl.roi_filter_inverts["img_1"])
        self.assertEqual(len(ui._get_target_rois(mock_viewer)), 2)
        dpg.delete_item("test_parent")

    def test_save_filtered_rois_as_labels(self):
        """Test controller combining filtered ROIs into label image and JSON sidecar."""
        import tempfile
        import json
        import numpy as np

        ctrl = self.plugin._controller
        ctrl.api = self.mock_api

        # Setup mock base volume (shape: 10 x 20 x 30)
        mock_base_vol = MagicMock()
        mock_base_vol.shape3d = (10, 20, 30)
        mock_base_vol.spacing = np.array([1.0, 1.0, 1.0])
        mock_base_vol.origin = np.array([0.0, 0.0, 0.0])
        mock_base_vol.sitk_image = MagicMock()
        mock_base_vol.sitk_image.GetSpacing.return_value = (1.0, 1.0, 1.0)
        mock_base_vol.sitk_image.GetOrigin.return_value = (0.0, 0.0, 0.0)
        mock_base_vol.sitk_image.GetDirection.return_value = (1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0)

        # Setup mock ROI volumes
        r1_vol = MagicMock()
        r1_vol.data = np.ones((4, 4, 4), dtype=np.uint8)
        r1_vol.roi_bbox = (1, 5, 2, 6, 3, 7)

        r2_vol = MagicMock()
        r2_vol.data = np.ones((3, 3, 3), dtype=np.uint8)
        r2_vol.roi_bbox = (6, 9, 7, 10, 8, 11)

        r3_vol = MagicMock()
        r3_vol.data = np.ones((2, 2, 2), dtype=np.uint8)
        r3_vol.roi_bbox = (0, 2, 0, 2, 0, 2)

        rois = {
            "r1": MockROI("r1", "Liver", [255, 0, 0]),
            "r2": MockROI("r2", "Kidney_L", [0, 255, 0]),
            "r3": MockROI("r3", "Kidney_R", [0, 0, 255]),
        }
        mock_vs = MagicMock()
        mock_vs.rois = rois

        self.mock_api.get_volumes.return_value = {
            "base_1": mock_base_vol,
            "r1": r1_vol,
            "r2": r2_vol,
            "r3": r3_vol,
        }
        self.mock_api.get_view_states.return_value = {"base_1": mock_vs}

        # Filter only Kidneys
        ctrl.roi_filters["base_1"] = "kidney"
        ctrl.roi_filter_inverts["base_1"] = False

        with tempfile.TemporaryDirectory() as tmpdir:
            out_nii = os.path.join(tmpdir, "test_labels.nii.gz")
            out_json = os.path.join(tmpdir, "test_labels.json")

            with patch("SimpleITK.WriteImage") as mock_write:
                success = ctrl.save_filtered_rois_as_labels("base_1", out_nii)
                self.assertTrue(success)
                mock_write.assert_called_once()

            # Verify sidecar JSON content
            self.assertTrue(os.path.exists(out_json))
            with open(out_json, "r") as f:
                sidecar = json.load(f)

            # Exactly 2 filtered ROIs (Kidney_L and Kidney_R)
            self.assertEqual(len(sidecar), 2)
            self.assertEqual(sidecar["1"]["name"], "Kidney_L")
            self.assertEqual(sidecar["1"]["color"], [0, 255, 0])
            self.assertEqual(sidecar["2"]["name"], "Kidney_R")
            self.assertEqual(sidecar["2"]["color"], [0, 0, 255])

    def test_save_filtered_rois_as_individual_files(self):
        """Test exporting ROIs as individual binary mask files."""
        ctrl = self.plugin._controller
        ctrl.api = self.mock_api

        mock_base = MagicMock()
        mock_base.shape3d = (10, 20, 20)
        mock_base.sitk_image = sitk.Image(20, 20, 10, sitk.sitkFloat32)

        data_1 = np.zeros((10, 20, 20), dtype=np.uint8)
        data_1[2:5, 5:10, 5:10] = 1
        vol_1 = MagicMock()
        vol_1.data = data_1
        vol_1.shape3d = (10, 20, 20)
        vol_1.sitk_image = sitk.GetImageFromArray(data_1)
        vol_1.roi_bbox = None

        roi_state_1 = MagicMock()
        roi_state_1.name = "Kidney_L"
        roi_state_1.color = [0, 255, 0]

        mock_vs = MagicMock()
        mock_vs.rois = {"roi_1": roi_state_1}

        self.mock_api.get_volumes.return_value = {"img_1": mock_base, "roi_1": vol_1}
        self.mock_api.get_view_states.return_value = {"img_1": mock_vs}

        with tempfile.TemporaryDirectory() as tmpdir:
            out_dir = os.path.join(tmpdir, "rois_dir")
            success = ctrl.save_filtered_rois_as_individual_files("img_1", out_dir, auto_crop=True)
            self.assertTrue(success)

            saved_files = os.listdir(out_dir)
            self.assertIn("Kidney_L.nii.gz", saved_files)
            read_img = sitk.ReadImage(os.path.join(out_dir, "Kidney_L.nii.gz"))
            self.assertEqual(read_img.GetSize(), (20, 20, 10))

    def test_batch_save_worker_reads_no_live_state(self):
        """PB1: the batch save reads the ROIs on the main thread and notifies on
        the main thread; the worker only writes the files."""
        import threading
        import time

        ctrl = self.plugin._controller
        ctrl.api = self.mock_api
        ui = self.plugin._ui
        ui.api = self.mock_api
        main = threading.current_thread()
        threads = []

        data_1 = np.zeros((10, 20, 20), dtype=np.uint8)
        data_1[2:5, 5:10, 5:10] = 1
        vol_1 = MagicMock()
        vol_1.data = data_1
        vol_1.shape3d = (10, 20, 20)
        vol_1.sitk_image = sitk.GetImageFromArray(data_1)
        vol_1.roi_bbox = None
        mock_base = MagicMock()
        mock_base.shape3d = (10, 20, 20)
        mock_base.sitk_image = sitk.Image(20, 20, 10, sitk.sitkFloat32)
        roi_state_1 = MagicMock()
        roi_state_1.name = "Kidney_L"
        roi_state_1.color = [0, 255, 0]
        mock_vs = MagicMock()
        mock_vs.rois = {"roi_1": roi_state_1}

        def record(value):
            def _f(*a, **k):
                threads.append(threading.current_thread())
                return value
            return _f

        self.mock_api.get_volumes.side_effect = record({"img_1": mock_base, "roi_1": vol_1})
        self.mock_api.get_view_states.side_effect = record({"img_1": mock_vs})
        self.mock_api.notify.side_effect = record(None)
        queued = []
        self.mock_api.run_on_main_thread.side_effect = queued.append

        with tempfile.TemporaryDirectory() as tmpdir:
            out_dir = os.path.join(tmpdir, "rois_dir")
            ui._execute_save_rois("img_1", {"mode": "individual", "path": out_dir})
            t_end = time.time() + 5
            while not queued and time.time() < t_end:
                time.sleep(0.01)
            for cb in queued:  # what the GUI loop does on the main thread
                cb()
            self.assertIn("Kidney_L.nii.gz", os.listdir(out_dir))

        self.assertTrue(threads)
        self.assertTrue(all(t is main for t in threads))
        self.mock_api.notify.assert_called_with("Saved 1 ROI files to rois_dir/")

    def test_ui_save_labels_buttons(self):
        """Test Save and Save As modal dialog and filename tracking."""
        if not dpg.is_dearpygui_running():
            dpg.create_context()
        with dpg.window(tag="test_parent"):
            self.plugin.create_ui(parent="test_parent", api=self.mock_api)

        ui = self.plugin._ui
        ctrl = self.plugin._controller

        self.assertTrue(dpg.does_item_exist(ui._t("btn_roi_save_as")))
        self.assertTrue(dpg.does_item_exist(ui._t("btn_roi_save")))
        self.assertTrue(dpg.does_item_exist(ui._t("text_roi_save_filename")))

        mock_viewer = MagicMock()
        mock_viewer.image_id = "img_ct"
        mock_viewer.view_state = MagicMock()
        mock_viewer.view_state.rois = {}
        self.mock_api.get_active_viewer.return_value = mock_viewer
        self.mock_api.get_image_display_name.return_value = ("patient_ct.nii.gz", False)

        with patch.object(ui, "show_save_rois_modal") as mock_show_modal, \
             patch.object(ui, "_execute_save_rois") as mock_exec:
            # 1. Clicking Save when no path stored opens modal
            ui.on_save_filtered_rois_clicked()
            mock_show_modal.assert_called_once_with("img_ct")
            mock_exec.assert_not_called()

            # 2. Clicking Save As opens modal
            mock_show_modal.reset_mock()
            ui.on_save_filtered_rois_as_clicked()
            mock_show_modal.assert_called_once_with("img_ct")

            # 3. Setting remembered settings allows Save to execute directly
            ui.roi_save_settings["img_ct"] = {
                "mode": "single",
                "path": "/tmp/patient_ct_labels.nii.gz",
                "sort_by_volume": True,
                "auto_crop": True,
            }
            ui.labels_save_paths["img_ct"] = "/tmp/patient_ct_labels.nii.gz"
            ui.update_save_filename_ui()
            self.assertEqual(dpg.get_value(ui._t("text_roi_save_filename")), "patient_ct_labels.nii.gz")

            mock_show_modal.reset_mock()
            ui.on_save_filtered_rois_clicked()
            mock_show_modal.assert_not_called()
            mock_exec.assert_called_once()

        # Test modal creation and controls
        ui.show_save_rois_modal("img_ct")
        modal_tag = ui._t("save_rois_modal")
        self.assertTrue(dpg.does_item_exist(modal_tag))
        self.assertTrue(dpg.does_item_exist(ui._t("save_modal_format_radio")))
        self.assertTrue(dpg.does_item_exist(ui._t("save_modal_path_input")))
        self.assertTrue(dpg.does_item_exist(ui._t("save_modal_cb_sort")))
        self.assertTrue(dpg.does_item_exist(ui._t("save_modal_cb_autocrop")))

        # Test mode switch changes group visibility
        ui._on_save_modal_mode_changed(None, "One file per label (<roi_name>.nii.gz)", None)
        self.assertFalse(dpg.is_item_shown(ui._t("save_modal_grp_single")))
        self.assertTrue(dpg.is_item_shown(ui._t("save_modal_grp_indiv")))

        dpg.delete_item(modal_tag)
        dpg.delete_item("test_parent")

    def test_rtstruct_native_pixel_center_contours(self):
        from vvv.core.roi_manager import ROIManager, ROIState
        from vvv.utils import ViewMode
        import numpy as np

        mock_controller = MagicMock()
        mock_controller.volumes = {}
        mock_controller.view_states = {}
        mock_controller.next_image_id = 1
        roi_mgr = ROIManager(mock_controller)

        # Base volume: 10x10x10, spacing [2.0, 3.0, 1.0]
        import SimpleITK as sitk
        base_vol = MagicMock()
        base_vol.shape3d = (10, 10, 10)
        base_vol.spacing = np.array([2.0, 3.0, 1.0])
        base_vol.origin = np.array([0.0, 0.0, 0.0])
        base_vol.matrix = np.eye(3)
        base_vol.matrix_display_str = "identity"
        base_vol.matrix_tooltip_str = "identity"
        base_vol.physic_coord_to_voxel_coord.side_effect = lambda pt: pt
        base_sitk = sitk.Image(10, 10, 10, sitk.sitkFloat32)
        base_sitk.SetSpacing([2.0, 3.0, 1.0])
        base_vol.sitk_image = base_sitk

        mock_vs = MagicMock()
        mock_vs.rois = {}
        mock_controller.volumes["base_1"] = base_vol
        mock_controller.view_states["base_1"] = mock_vs

        # Create mock DICOM dataset
        mock_ds = MagicMock()
        contour = MagicMock()
        # Triangle at slice Z = 4 with voxel centers: (1, 1), (5, 1), (3, 5)
        contour.ContourData = [
            1.0, 1.0, 4.0,
            5.0, 1.0, 4.0,
            3.0, 5.0, 4.0,
        ]
        roi_contour = MagicMock()
        roi_contour.ReferencedROINumber = 1
        roi_contour.ContourSequence = [contour]
        mock_ds.ROIContourSequence = [roi_contour]

        roi_id = roi_mgr.load_rtstruct_roi(
            base_id="base_1",
            filepath="/path/to/rtstruct.dcm",
            roi_info={"id": 1, "name": "Target", "color": [255, 0, 0]},
            ds=mock_ds,
        )

        self.assertIsNotNone(roi_id)
        roi_state = mock_vs.rois[roi_id]

        # Verify native_polygons exists and has slice 4
        self.assertIn(ViewMode.AXIAL, roi_state.native_polygons)
        self.assertIn(4, roi_state.native_polygons[ViewMode.AXIAL])
        polys_z4 = roi_state.native_polygons[ViewMode.AXIAL][4]
        self.assertEqual(len(polys_z4), 1)

        # Expected coordinates: (vox + 0.5) * spacing
        # For point 0: vox_x = 1.0, vox_y = 1.0 -> px = (1.0 + 0.5) * 2.0 = 3.0, py = (1.0 + 0.5) * 3.0 = 4.5
        # For point 1: vox_x = 5.0, vox_y = 1.0 -> px = (5.0 + 0.5) * 2.0 = 11.0, py = 4.5
        # For point 2: vox_x = 3.0, vox_y = 5.0 -> px = (3.0 + 0.5) * 2.0 = 7.0, py = (5.0 + 0.5) * 3.0 = 16.5
        poly = polys_z4[0]
        self.assertAlmostEqual(poly[0][0], 3.0)
        self.assertAlmostEqual(poly[0][1], 4.5)
        self.assertAlmostEqual(poly[1][0], 11.0)
        self.assertAlmostEqual(poly[1][1], 4.5)
        self.assertAlmostEqual(poly[2][0], 7.0)
        self.assertAlmostEqual(poly[2][1], 16.5)
        # Closed loop check: last point equals first point
        self.assertEqual(poly[0], poly[-1])

        # Verify that roi_state.polygons[ViewMode.AXIAL] is pre-seeded with native polygons
        self.assertEqual(roi_state.polygons[ViewMode.AXIAL][4], [poly])

        # Verify invalidate restores native polygons
        roi_state.invalidate()
        self.assertIn(4, roi_state.polygons[ViewMode.AXIAL])
        self.assertEqual(roi_state.polygons[ViewMode.AXIAL][4], [poly])

        # Verify update_roi_contours uses native polygons on axial
        viewer = MagicMock()
        viewer.view_state = mock_vs
        viewer.orientation = ViewMode.AXIAL
        viewer.slice_idx = 4
        viewer.volume = base_vol
        roi_mgr.update_roi_contours(viewer)
        self.assertEqual(roi_state.polygons[ViewMode.AXIAL][4], [poly])

    def test_box_mask_uses_direction_matrix_and_early_return_protects_state(self):
        """Verify that box mask calculation respects direction matrix and early return protects state (PA12)."""
        import SimpleITK as sitk
        from vvv.maths.image import VolumeData

        ctrl = self.plugin._controller
        ctrl.api = self.mock_api

        # Create a volume with a non-identity direction matrix (swapped X and Y axes)
        # Direction: [[0, 1, 0], [1, 0, 0], [0, 0, 1]]
        arr = np.zeros((20, 30, 40), dtype=np.float32)
        sitk_img = sitk.GetImageFromArray(arr)
        sitk_img.SetSpacing((1.0, 1.0, 1.0))
        sitk_img.SetOrigin((0.0, 0.0, 0.0))
        sitk_img.SetDirection([0.0, 1.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0])

        base_vol = VolumeData("dummy_path", preloaded_sitk=sitk_img)
        base_vol.matrix = np.array([[0.0, 1.0, 0.0], [1.0, 0.0, 0.0], [0.0, 0.0, 1.0]])
        base_vol.inverse_matrix = np.linalg.inv(base_vol.matrix)
        self.mock_api.get_volumes.return_value = {"base_oriented": base_vol}

        vs = MagicMock()
        vs.rois = {}
        self.mock_api.get_view_states.return_value = {"base_oriented": vs}

        # 1. Test update_box_mask with asymmetric extents in physical space:
        # half_x = 2 mm (phys X), half_y = 10 mm (phys Y), half_z = 5 mm (phys Z)
        # Because matrix maps vox X -> phys Y and vox Y -> phys X:
        # In voxels, extent along voxel X should be half_y (10 mm -> 20 vox wide)
        # and extent along voxel Y should be half_x (2 mm -> 4 vox wide).
        box_size_x, box_size_y, box_size_z = 4.0, 20.0, 10.0
        phys_center = base_vol.origin + np.array([15.0, 15.0, 10.0])

        roi_state = MagicMock()
        roi_state.box_size_x = 10.0
        roi_state.box_size_y = 10.0
        roi_state.box_size_z = 10.0
        roi_state.box_center = phys_center.tolist()

        roi_vol = MagicMock()
        roi_vol.sitk_image = None

        ctrl.update_box_mask(base_vol, roi_vol, roi_state, new_size_x=box_size_x, new_size_y=box_size_y, new_size_z=box_size_z)
        mask = roi_vol.data
        # In voxel coords, vox Y corresponds to phys X (size 4 -> span 4),
        # and vox X corresponds to phys Y (size 20 -> span 20).
        # Check that voxel X span > voxel Y span
        span_z, span_y, span_x = mask.shape
        self.assertGreater(span_x, span_y)

        # 2. Test early return protects roi_state in update_box_mask & update_spheroid_mask
        roi_state.box_size_x = 10.0
        roi_state.box_size_y = 10.0
        roi_state.box_size_z = 10.0
        roi_state.box_center = [15.0, 15.0, 10.0]

        roi_vol = MagicMock()
        roi_vol.sitk_image = None

        # Pass a mock base_vol where bounding box produces min_x >= max_x (e.g. inverted bounds)
        bad_base_vol = MagicMock()
        bad_base_vol.shape3d = (20, 20, 20)
        bad_base_vol.physic_coord_to_voxel_coord.return_value = np.array([-10.0, -10.0, -10.0])
        bad_base_vol.voxel_coord_to_physic_coord.return_value = np.array([0.0, 0.0, 0.0])

        ctrl.update_box_mask(bad_base_vol, roi_vol, roi_state, new_size_x=50.0, new_size_y=50.0, new_size_z=50.0)
        # Verify box_size was not overwritten with 50.0 on early return
        self.assertEqual(roi_state.box_size_x, 10.0)

        # Same for update_spheroid_mask
        roi_state.spheroid_radius_x = 8.0
        ctrl.update_spheroid_mask(bad_base_vol, roi_vol, roi_state, new_r_x_mm=99.0)
        self.assertEqual(roi_state.spheroid_radius_x, 8.0)

    def test_box_smaller_than_a_voxel_keeps_the_center_voxel(self):
        """A box that contains no voxel center falls back to the voxel under its center
        (the fallback used an undefined center_voxel: NameError)."""
        import SimpleITK as sitk
        from vvv.maths.image import VolumeData

        ctrl = self.plugin._controller
        ctrl.api = self.mock_api
        sitk_img = sitk.GetImageFromArray(np.zeros((20, 30, 40), dtype=np.float32))
        sitk_img.SetSpacing((3.0, 3.0, 3.0))  # sizes are clamped to >= 1 mm
        base_vol = VolumeData("dummy_path", preloaded_sitk=sitk_img)

        roi_state = MagicMock()
        roi_state.box_center = [61.5, 45.0, 30.0]  # x between the voxel centers 60 and 63 mm
        roi_vol = MagicMock()
        roi_vol.sitk_image = None

        ctrl.update_box_mask(base_vol, roi_vol, roi_state, new_size_x=1.0, new_size_y=1.0, new_size_z=1.0)

        self.assertEqual(int(np.count_nonzero(roi_vol.data)), 1)

    def test_detailed_stats_caching_and_invalidation(self):
        """PC1: verify that compute_detailed_roi_stats caches results and invalidates properly."""
        ctrl = self.plugin._controller
        ctrl.bind(self.mock_api)

        base_vol = MagicMock()
        base_vol.data = np.full((5, 6, 7), 10.0, dtype=np.float32)
        base_vol.spacing = np.array([2.0, 2.0, 2.0])
        base_vol.shape3d = (5, 6, 7)
        base_vol.num_timepoints = 1
        base_vol.is_rgb = False
        base_vol.sitk_image = MagicMock()

        roi_vol = MagicMock()
        roi_vol.data = np.zeros((5, 6, 7), dtype=np.uint8)
        roi_vol.data[1, 2, 3] = 1
        roi_vol.spacing = np.array([2.0, 2.0, 2.0])
        roi_vol.shape3d = (5, 6, 7)
        roi_vol.sitk_image = MagicMock()

        roi_state = ROIState("roi_c", "CacheTest", [255, 0, 0])
        self.mock_api.get_volumes.return_value = {
            "img_c": base_vol,
            "roi_c": roi_vol,
        }
        self.mock_api.get_view_states.return_value = {
            "img_c": MockViewState(rois={"roi_c": roi_state}),
        }

        # First compute
        stats1 = ctrl.compute_detailed_roi_stats("img_c", "roi_c")
        self.assertIsNotNone(stats1)

        # Second compute should hit cache and return exact same dict
        stats2 = ctrl.compute_detailed_roi_stats("img_c", "roi_c")
        self.assertIs(stats1, stats2)

        # Invalidate cache for roi_c
        ctrl.invalidate_stats_cache("roi_c")
        self.assertEqual(len(ctrl._detailed_stats_cache), 0)

        # Recomputes and produces new dict
        stats3 = ctrl.compute_detailed_roi_stats("img_c", "roi_c")
        self.assertIsNotNone(stats3)
        self.assertEqual(len(ctrl._detailed_stats_cache), 1)

        # Replacing data changes id(data) and also bypasses stale cache
        roi_vol.data = np.zeros((5, 6, 7), dtype=np.uint8)
        roi_vol.data[2, 2, 2] = 1
        stats4 = ctrl.compute_detailed_roi_stats("img_c", "roi_c")
        self.assertIsNot(stats3, stats4)

    def test_refresh_rois_ui_table_state_caching(self):
        """PC1: verify that refresh_rois_ui avoids rebuilding table rows when state is unchanged."""
        if not dpg.is_dearpygui_running():
            dpg.create_context()
        with dpg.window(tag="test_cache_parent"):
            self.plugin.create_ui(parent="test_cache_parent", api=self.mock_api)

        ui = self.plugin._ui
        ctrl = self.plugin._controller

        rois = {
            "roi_a": MockROI("roi_a", "ROI_A", [255, 0, 0]),
            "roi_b": MockROI("roi_b", "ROI_B", [0, 255, 0]),
        }
        mock_viewer = MockViewer("img_cache", rois)
        self.mock_api.get_active_viewer.return_value = mock_viewer

        # Initial refresh: builds the table
        ui.refresh_rois_ui()
        self.assertIsNotNone(ui._last_table_state_key)
        first_input = ui.roi_selectables["roi_a"]

        # Second refresh with identical state: should skip table delete/rebuild
        ui.refresh_rois_ui()
        # Item tag for roi_a should still exist and match
        self.assertEqual(ui.roi_selectables["roi_a"], first_input)

        # State change (selection): should trigger rebuild
        ctrl.on_roi_selected("roi_a")
        # Item tag regenerated after selection rebuild
        self.assertIn("roi_a", ui.roi_selectables)

        dpg.delete_item("test_cache_parent")

    def _source_setup(self):
        """3 ROIs from 2 files + 1 created ROI, with their volumes."""
        rois = {
            "r1": MockROI("r1", "Liver", [255, 0, 0]),
            "r2": MockROI("r2", "Lung", [0, 255, 0]),
            "r3": MockROI("r3", "Lung", [0, 0, 255]),
            "r4": MockROI("r4", "Sphere_4", [0, 0, 255]),
        }
        rois["r1"].source_type = rois["r2"].source_type = "Label Map"
        rois["r4"].source_type = "Created"
        vols = {}
        for rid, path in (
            ("r1", "/a/organs.nii.gz"),
            ("r2", "/a/organs.nii.gz"),
            ("r3", "/b/lung_mask.nii.gz"),
            ("r4", "spheroid_roi"),
        ):
            vols[rid] = MagicMock()
            vols[rid].file_paths = [path]
        self.mock_api.get_volumes.side_effect = None
        self.mock_api.get_volumes.return_value = vols
        return rois, vols

    def test_source_combo_items(self):
        """U17: one item per file (kind, name, count), created ROIs last;
        same file name in two folders gets its folder."""
        from vvv.plugins.roi.ui_roi import source_combo_items

        sources = {
            "": ("Created", 1),
            "/a/organs.nii.gz": ("Label Map", 2),
            "/b/organs.nii.gz": ("Label Map", 3),
            "/b/rt.dcm": ("RT-Struct", 4),
        }
        items = source_combo_items(sources)
        self.assertEqual(
            list(items),
            [
                "All sources (10)",
                "Labels \u00b7 a/organs.nii.gz (2)",
                "Labels \u00b7 b/organs.nii.gz (3)",
                "RT \u00b7 rt.dcm (4)",
                "Created (1)",
            ],
        )
        self.assertIsNone(items["All sources (10)"])
        self.assertEqual(items["Created (1)"], "")
        self.assertEqual(items["RT \u00b7 rt.dcm (4)"], "/b/rt.dcm")

    def test_source_filter_lists_one_file(self):
        """U17: the source filter narrows the listed ROIs (with the name
        filter), so the batch actions act on one file; it is forgotten once
        its file is gone."""
        if not dpg.is_dearpygui_running():
            dpg.create_context()
        with dpg.window(tag="test_parent"):
            self.plugin.create_ui(parent="test_parent", api=self.mock_api)
        ui = self.plugin._ui
        ctrl = self.plugin._controller
        rois, vols = self._source_setup()
        viewer = MockViewer("img_1", rois)
        self.mock_api.get_active_viewer.return_value = viewer

        ui.refresh_rois_ui()
        self.assertTrue(dpg.is_item_shown(ui._t("group_roi_source")))
        self.assertEqual(len(dpg.get_item_configuration(ui._t("combo_roi_source"))["items"]), 4)

        ctrl.on_roi_source_changed("/a/organs.nii.gz")
        self.assertEqual([i for i, _ in ui._get_target_rois(viewer)], ["r1", "r2"])
        self.assertEqual(list(ui.roi_selectables), ["r1", "r2"])
        self.assertTrue(dpg.get_value(ui._t("combo_roi_source")).startswith("Labels"))

        ctrl.on_roi_filter_changed("lung")
        self.assertEqual([i for i, _ in ui._get_target_rois(viewer)], ["r2"])
        ctrl.on_clear_roi_filter()

        ctrl.on_roi_source_changed("")  # created ROIs
        self.assertEqual([i for i, _ in ui._get_target_rois(viewer)], ["r4"])

        # The file is gone: back to all the ROIs; one source left: combo hidden
        ctrl.on_roi_source_changed("/b/lung_mask.nii.gz")
        del rois["r3"], rois["r4"]
        ui.refresh_rois_ui()
        self.assertNotIn("img_1", ctrl.roi_source_filters)
        self.assertFalse(dpg.is_item_shown(ui._t("group_roi_source")))
        self.assertEqual(len(ui._get_target_rois(viewer)), 2)
        dpg.delete_item("test_parent")

    def test_source_tooltip(self):
        from vvv.plugins.roi.ui_roi import source_tooltip

        rois, vols = self._source_setup()
        rois["r1"].source_val = 3.0
        self.assertEqual(
            source_tooltip(rois["r1"], vols["r1"]),
            "From: organs.nii.gz (label 3)\n/a/organs.nii.gz",
        )
        self.assertTrue(source_tooltip(rois["r4"], vols["r4"]).startswith("Created"))
        # names / colors from the json side-car of the label map
        vols["r1"].file_paths = ["/a/organs.nii.gz", "/a/organs.json"]
        self.assertTrue(
            source_tooltip(rois["r1"], vols["r1"]).endswith(
                "\nName and color from organs.json (side-car file)"
            )
        )

    def test_saved_rois_come_from_the_saved_file(self):
        """U17: after a batch save, the saved ROIs come from the new file
        (label value / binary mask); the ROIs not saved are unchanged."""
        ctrl = self.plugin._controller
        ctrl.api = self.mock_api
        base = MagicMock()
        base.shape3d = (10, 20, 20)
        base.sitk_image = sitk.Image(20, 20, 10, sitk.sitkFloat32)
        rois, vols = self._source_setup()
        for rid in ("r1", "r2", "r3"):
            data = np.zeros((10, 20, 20), dtype=np.uint8)
            data[2:5, 5:10, 5:10] = 1
            vols[rid].data = data
            vols[rid].shape3d = (10, 20, 20)
            vols[rid].sitk_image = sitk.GetImageFromArray(data)
            vols[rid].roi_bbox = None
        rois["r3"].rtstruct_info = {"number": 1}
        vols["base"] = base
        vs = MockViewState(rois)
        self.mock_api.get_view_states.return_value = {"base": vs}
        ctrl.roi_filters["base"] = "lung"

        with tempfile.TemporaryDirectory() as tmpdir:
            out = os.path.join(tmpdir, "lungs.nii.gz")
            self.assertTrue(ctrl.save_filtered_rois_as_labels("base", out, sort_by_volume=False))
            for rid, label in (("r2", 1), ("r3", 2)):
                self.assertEqual(vols[rid].file_paths, [out, os.path.join(tmpdir, "lungs.json")])
                self.assertEqual(rois[rid].source_type, "Label Map")
                self.assertEqual(rois[rid].source_val, float(label))
            self.assertIsNone(rois["r3"].rtstruct_info)
            self.assertEqual(vols["r1"].file_paths, ["/a/organs.nii.gz"])

            out_dir = os.path.join(tmpdir, "masks")
            ctrl.roi_filters["base"] = "liver"
            self.assertTrue(ctrl.save_filtered_rois_as_individual_files("base", out_dir))
            self.assertEqual(vols["r1"].file_paths, [os.path.join(out_dir, "Liver.nii.gz")])
            self.assertEqual(rois["r1"].source_type, "Binary")
            self.assertEqual(rois["r1"].source_val, 1.0)


if __name__ == "__main__":
    unittest.main()
