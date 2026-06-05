import unittest
from unittest.mock import MagicMock, patch
import dearpygui.dearpygui as dpg
import os
from vvv.plugins.roi.plugin_roi import RoiPlugin


class MockROI:
    def __init__(self, roi_id, name, color, visible=True, is_contour=False):
        self.volume_id = roi_id
        self.name = name
        self.color = color
        self.visible = visible
        self.is_contour = is_contour
        self.opacity = 0.5
        self.thickness = 1.0
        self.source_mode = "Binary"
        self.source_val = 1.0
        self.source_type = "Binary"
        self.polygons = {0: {}, 1: {}, 2: {}}


class MockViewState:
    def __init__(self, rois):
        self.rois = rois
        self.is_data_dirty = False
        self.is_geometry_dirty = False
        self.display = MagicMock()
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
            }
        }
        self.mock_api.get_ui_config.return_value = ui_cfg
        self.mock_api.ui_cfg = ui_cfg
        self.mock_api.is_beginner_mode = False
        self.mock_api.beginner_tags = []
        self.mock_api.get_active_viewer.return_value = None
        self.mock_api.get_image_display_name.return_value = ("Test Image", False)
        self.mock_api.get_volumes.return_value = {}
        self.mock_api.get_roi_stats.return_value = None
        self.mock_api.is_mip_active.return_value = False

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
        self.assertTrue(dpg.does_item_exist(self.plugin._ui._t("text_roi_active_title")))
        self.assertTrue(dpg.does_item_exist(self.plugin._ui._t("btn_roi_load_rtstruct")))
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
        self.assertEqual(self.plugin.serialize_image_state("img1"), {"roi_filter": "", "roi_sort_order": 0})
        self.plugin.restore_image_state("img1", {"roi_filter": "", "roi_sort_order": 0})
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

        # Test mock actions
        ui.on_mock_action("btn_test", None, None)
        self.mock_api.notify.assert_called_with("ROI: Slider or combo callback (sender: btn_test)")

        ui.on_export_roi_stats_clicked(None, None, None)
        self.mock_api.notify.assert_called_with("ROI: Export stats clicked")

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
        ctrl.on_sort_rois() # Sort order = 1
        self.assertEqual(ctrl.roi_sort_orders["img_1"], 1)
        ui.refresh_rois_ui()

        ctrl.on_sort_rois() # Sort order = -1
        self.assertEqual(ctrl.roi_sort_orders["img_1"], -1)
        ui.refresh_rois_ui()

        ctrl.on_sort_rois() # Sort order = 0
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
            "roi_1": MockROI("roi_1", "Tumor", [255, 0, 0], visible=True, is_contour=False),
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

    @patch('vvv.ui.file_dialog.open_file_dialog')
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

    @patch('vvv.ui.file_dialog.open_file_dialog')
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

    @patch('vvv.ui.file_dialog.open_file_dialog')
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
        
        with patch.object(ui, 'show_rtstruct_selection_modal') as mock_show_modal:
            ui.on_load_rtstruct_clicked(None, None, None)
            mock_show_modal.assert_called_once_with(
                "/path/to/rtstruct.dcm",
                [{"name": "ROI 1", "color": [255, 0, 0]}, {"name": "ROI 2", "color": [0, 255, 0]}]
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

        with patch('dearpygui.dearpygui.get_viewport_client_width', return_value=800), \
             patch('dearpygui.dearpygui.get_viewport_client_height', return_value=600):
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
        self.mock_api.update_all_viewers_of_image.assert_called_with("img_1", data_dirty=False)

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
        with patch.object(ui, 'refresh_rois_ui') as mock_refresh:
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

        rois = {f"roi_{i}": MockROI(f"roi_{i}", f"ROI {i}", [255, 0, 0]) for i in range(10)}
        mock_viewer = MockViewer("img_1", rois)
        self.mock_api.get_active_viewer.return_value = mock_viewer

        with patch('dearpygui.dearpygui.get_y_scroll') as mock_get_scroll, \
             patch('dearpygui.dearpygui.set_y_scroll') as mock_set_scroll, \
             patch('dearpygui.dearpygui.get_item_height') as mock_get_height, \
             patch('dearpygui.dearpygui.get_y_scroll_max') as mock_get_scroll_max:

            # Mock scroll values
            mock_get_scroll.return_value = 0.0
            mock_get_height.return_value = 150.0
            mock_get_scroll_max.return_value = 200.0

            # 1. Trigger move_roi_selection (selects first item)
            ctrl.active_roi_id = "roi_0"
            ctrl.move_roi_selection(1)  # should select roi_1 and set _scroll_to_active = True
            
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

        # 1. Toggle it ON
        ui.on_roi_stats_toggle(None, None, "roi_1")
        win_tag = ui._t("stats_win_roi_1")
        self.assertTrue(dpg.does_item_exist(win_tag))
        self.assertIn(win_tag, ui.open_stats_wins)

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

        with patch('dearpygui.dearpygui.get_viewport_client_width') as mock_vp_w, \
             patch('dearpygui.dearpygui.get_viewport_client_height') as mock_vp_h:

            mock_vp_w.return_value = 1000
            mock_vp_h.return_value = 800

            # 1. Open first window, offset should be 0
            ui.on_roi_stats_toggle(None, None, "roi_1")
            # base_x = 1000 - 320 - 50 = 630
            # base_y = (800 - 530) // 2 = 135
            self.assertEqual(dpg.get_item_pos(ui._t("stats_win_roi_1")), [630, 135])

            # 2. Open second window, offset should be 25px
            ui.on_roi_stats_toggle(None, None, "roi_2")
            self.assertEqual(dpg.get_item_pos(ui._t("stats_win_roi_2")), [605, 160])

            # 3. Open third window, offset should be 50px
            ui.on_roi_stats_toggle(None, None, "roi_3")
            self.assertEqual(dpg.get_item_pos(ui._t("stats_win_roi_3")), [580, 185])

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
        base_vol.sitk_image.TransformPhysicalPointToContinuousIndex.side_effect = lambda pt: [pt[0]/2.0, pt[1]/2.0, pt[2]/2.0]

        roi_vol = MagicMock()
        roi_vol.shape3d = (5, 6, 7)
        roi_vol.spacing = (2.0, 2.0, 2.0)
        roi_vol.data = np.zeros((5, 6, 7), dtype=np.uint8)
        roi_vol.data[2, 3, 4] = 1
        roi_vol.data[3, 4, 5] = 1
        roi_vol.sitk_image = MagicMock()
        roi_vol.sitk_image.TransformContinuousIndexToPhysicalPoint.side_effect = lambda idx: [idx[0]*2.0, idx[1]*2.0, idx[2]*2.0]

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
        base_vol.sitk_image.TransformPhysicalPointToContinuousIndex.side_effect = lambda pt: [pt[0]/2.0, pt[1]/2.0, pt[2]/2.0]

        roi_vol = MagicMock()
        roi_vol.shape3d = (5, 6, 7)
        roi_vol.spacing = (2.0, 2.0, 2.0)
        roi_vol.data = np.zeros((5, 6, 7), dtype=np.uint8)
        roi_vol.data[2, 3, 4] = 1
        roi_vol.data[3, 4, 5] = 1
        roi_vol.sitk_image = MagicMock()
        roi_vol.sitk_image.TransformContinuousIndexToPhysicalPoint.side_effect = lambda idx: [idx[0]*2.0, idx[1]*2.0, idx[2]*2.0]

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
        roi_vol.data = np.zeros((5, 5, 5), dtype=np.uint8) # Mismatched shape
        stats2 = ctrl.compute_detailed_roi_stats("img_1", "roi_1")
        self.assertIsNotNone(stats2)
        # Should fall back to 0.0 without crashing
        self.assertEqual(stats2["mean"], 0.0)

    @patch('vvv.ui.file_dialog.save_file_dialog')
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
        base_vol.sitk_image.TransformPhysicalPointToContinuousIndex.side_effect = lambda pt: [pt[0]/2.0, pt[1]/2.0, pt[2]/2.0]

        roi_vol = MagicMock()
        roi_vol.shape3d = (5, 6, 7)
        roi_vol.spacing = (2.0, 2.0, 2.0)
        roi_vol.data = np.zeros((5, 6, 7), dtype=np.uint8)
        roi_vol.data[2, 3, 4] = 1
        roi_vol.sitk_image = MagicMock()
        roi_vol.sitk_image.TransformContinuousIndexToPhysicalPoint.side_effect = lambda idx: [idx[0]*2.0, idx[1]*2.0, idx[2]*2.0]

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

            ui.on_export_stats_to_json(None, None, {"base_vs_id": "img_1", "roi_id": "roi_1"})
            
            mock_save.assert_called_with("Export Stats to JSON", default_name="Tumor_stats.json")
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
        mock_viewer.view_state.world_to_display.side_effect = lambda pt, **kw: np.array(pt)
        mock_viewer.view_state.display_to_world.side_effect = lambda pt, **kw: np.array(pt)
        mock_viewer.get_mouse_slice_coords.return_value = (10.0, 20.0)
        mock_viewer.get_slice_shape.return_value = (100, 100)
        mock_viewer.current_pmin = [0.0, 0.0]
        mock_viewer.current_pmax = [100.0, 100.0]
        mock_viewer.orientation = ViewMode.AXIAL
        mock_viewer.slice_idx = 30
        mock_viewer._ORIENTATION_MAP = {
            ViewMode.AXIAL: (2, 0, ("x", "y"), (1, 1))
        }
        mock_viewer.roi_mode = RoiInteractionMode.IDLE
        mock_viewer._is_buffered.return_value = False
        mock_viewer.is_image_orientation.return_value = True
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
        with patch("dearpygui.dearpygui.does_item_exist", return_value=True), \
             patch("dearpygui.dearpygui.get_drawing_mouse_pos", return_value=(10.5, 20.5)), \
             patch("dearpygui.dearpygui.set_value"):
            
             # Hover check
            roi_res = manager._check_roi_hover(mock_viewer)
            self.assertEqual(roi_res, ("Sphere_1", "center"))
            
            # Click
            tool = manager.active_tool
            tool.on_click(0) # left click
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
        roi_state.spheroid_radius_xy = 110.0
        roi_state.spheroid_radius_z = 110.0
        roi_state.is_contour = True

        # 2. Mock viewer and volumes
        mock_viewer = MagicMock()
        mock_viewer.image_id = "img_1"
        mock_viewer.tag = "V1"
        mock_viewer.view_state = MagicMock()
        mock_viewer.view_state.rois = {"Sphere_1": roi_state}
        mock_viewer.view_state.camera = MagicMock()
        mock_viewer.view_state.camera.target_ppm = 1.0  # Set ppm to 1.0 so pixels match voxel/mm distance
        mock_viewer.get_mouse_slice_coords.return_value = (120.5, 20.5)  # On the border (exact 110.0 px)
        mock_viewer.get_slice_shape.return_value = (100, 100)
        mock_viewer.current_pmin = [0.0, 0.0]
        mock_viewer.current_pmax = [100.0, 100.0]
        mock_viewer.orientation = ViewMode.AXIAL
        mock_viewer.slice_idx = 30
        mock_viewer._ORIENTATION_MAP = {
            ViewMode.AXIAL: (2, 0, ("x", "y"), (1, 1))
        }
        mock_viewer.roi_mode = RoiInteractionMode.IDLE
        mock_viewer._is_buffered.return_value = False
        mock_viewer.is_image_orientation.return_value = True
        mock_viewer.on_mouse_down = MagicMock()
        mock_viewer.get_pixels_per_mm.return_value = 1.0  # PPM = 1.0
        mock_viewer.view_state.world_to_display.side_effect = lambda pt, **kw: np.array(pt)
        mock_viewer.view_state.display_to_world.side_effect = lambda pt, **kw: np.array(pt)

        # Mock base volume
        base_vol = MagicMock()
        base_vol.shape3d = (50, 50, 50)
        base_vol.spacing = np.array([1.0, 1.0, 1.0])
        base_vol.origin = np.array([0.0, 0.0, 0.0])
        base_vol.matrix = np.eye(3)
        base_vol.physic_coord_to_voxel_coord.side_effect = lambda pt: pt
        base_vol.voxel_coord_to_physic_coord.side_effect = lambda pt: pt
        base_vol.sitk_image = MagicMock()
        # Ensure it is treated as mock to avoid SimpleITK initialization
        type(base_vol.sitk_image).__name__ = "MagicMock"

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
        with patch("dearpygui.dearpygui.does_item_exist", return_value=True), \
             patch("dearpygui.dearpygui.get_drawing_mouse_pos", return_value=(120.5, 20.5)), \
             patch("dearpygui.dearpygui.set_value"):
            
            # Hover check - should be near the border
            roi_res = manager._check_roi_hover(mock_viewer)
            self.assertEqual(roi_res, ("Sphere_1", "border"))
            
            # Click
            tool = manager.active_tool
            tool.on_click(0) # left click
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
        ui.on_roi_stats_radius_x_step_callback(None, None, {"tag": slider_x_tag, "dir": 1.5})
        self.assertEqual(roi_state.spheroid_radius_x, 7.0)

        # Test radius Y callback
        ui.on_roi_stats_radius_y_slider_changed(None, 6.0, "roi_1")
        self.assertEqual(roi_state.spheroid_radius_y, 6.0)

        # Test radius Y step callback
        slider_y_tag = ui._t("slider_roi_radius_y_roi_1")
        ui.on_roi_stats_radius_y_step_callback(None, None, {"tag": slider_y_tag, "dir": 1.0})
        self.assertEqual(roi_state.spheroid_radius_y, 7.0)

        # Test radius Z callback
        ui.on_roi_stats_radius_z_slider_changed(None, 6.5, "roi_1")
        self.assertEqual(roi_state.spheroid_radius_z, 6.5)

        # Test radius Z step callback
        slider_z_tag = ui._t("slider_roi_radius_z_roi_1")
        ui.on_roi_stats_radius_z_step_callback(None, None, {"tag": slider_z_tag, "dir": 1.0})
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
        mock_viewer.view_state.world_to_display.side_effect = lambda pt, **kw: np.array(pt)
        mock_viewer.view_state.display_to_world.side_effect = lambda pt, **kw: np.array(pt)
        mock_viewer.get_mouse_slice_coords.return_value = (10.0, 20.0)
        mock_viewer.get_slice_shape.return_value = (100, 100)
        mock_viewer.current_pmin = [0.0, 0.0]
        mock_viewer.current_pmax = [100.0, 100.0]
        mock_viewer.orientation = ViewMode.AXIAL
        mock_viewer.slice_idx = 30
        mock_viewer._ORIENTATION_MAP = {
            ViewMode.AXIAL: (2, 0, ("x", "y"), (1, 1))
        }
        mock_viewer.roi_mode = RoiInteractionMode.IDLE
        mock_viewer._is_buffered.return_value = False
        mock_viewer.is_image_orientation.return_value = True
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
        
        with patch("dearpygui.dearpygui.does_item_exist", return_value=True), \
             patch("dearpygui.dearpygui.get_drawing_mouse_pos", return_value=(10.5, 20.5)), \
             patch("dearpygui.dearpygui.set_value"):
            
             # Hover check
            roi_res = manager._check_roi_hover(mock_viewer)
            self.assertEqual(roi_res, ("Box_1", "center"))
            
            # Click
            tool = manager.active_tool
            tool.on_click(0) # left click
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
        mock_viewer._ORIENTATION_MAP = {
            ViewMode.AXIAL: (2, 0, ("x", "y"), (1, 1))
        }
        mock_viewer.roi_mode = RoiInteractionMode.IDLE
        mock_viewer._is_buffered.return_value = False
        mock_viewer.is_image_orientation.return_value = True
        mock_viewer.on_mouse_down = MagicMock()
        mock_viewer.get_pixels_per_mm.return_value = 1.0
        mock_viewer.view_state.world_to_display.side_effect = lambda pt, **kw: np.array(pt)
        mock_viewer.view_state.display_to_world.side_effect = lambda pt, **kw: np.array(pt)

        base_vol = MagicMock()
        base_vol.shape3d = (50, 50, 50)
        base_vol.spacing = np.array([1.0, 1.0, 1.0])
        base_vol.origin = np.array([0.0, 0.0, 0.0])
        base_vol.matrix = np.eye(3)
        base_vol.physic_coord_to_voxel_coord.side_effect = lambda pt: pt
        base_vol.voxel_coord_to_physic_coord.side_effect = lambda pt: pt
        base_vol.sitk_image = MagicMock()
        type(base_vol.sitk_image).__name__ = "MagicMock"

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
        
        with patch("dearpygui.dearpygui.does_item_exist", return_value=True), \
             patch("dearpygui.dearpygui.get_drawing_mouse_pos", return_value=(120.5, 20.5)), \
             patch("dearpygui.dearpygui.set_value"):
            
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
        ui.on_roi_stats_box_size_x_step_callback(None, None, {"tag": slider_x_tag, "dir": 1.0})
        self.assertEqual(roi_state.box_size_x, 9.0)

        # Test size Y callback
        ui.on_roi_stats_box_size_y_slider_changed(None, 7.0, "roi_1")
        self.assertEqual(roi_state.box_size_y, 7.0)

        # Test size Y step callback
        slider_y_tag = ui._t("slider_roi_box_size_y_roi_1")
        ui.on_roi_stats_box_size_y_step_callback(None, None, {"tag": slider_y_tag, "dir": 1.0})
        self.assertEqual(roi_state.box_size_y, 8.0)

        # Test size Z callback
        ui.on_roi_stats_box_size_z_slider_changed(None, 6.5, "roi_1")
        self.assertEqual(roi_state.box_size_z, 6.5)

        # Test size Z step callback
        slider_z_tag = ui._t("slider_roi_box_size_z_roi_1")
        ui.on_roi_stats_box_size_z_step_callback(None, None, {"tag": slider_z_tag, "dir": 1.0})
        self.assertEqual(roi_state.box_size_z, 7.5)

        # Test center callback
        ui.on_roi_stats_box_center_changed(None, 4.2, {"roi_id": "roi_1", "coord_idx": 0})
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
        mock_viewer.view_state.world_to_display.side_effect = lambda pt, **kw: np.array(pt)
        mock_viewer.view_state.display_to_world.side_effect = lambda pt, **kw: np.array(pt)
        mock_viewer.get_mouse_slice_coords.return_value = (12.0, 22.0)
        mock_viewer.get_slice_shape.return_value = (100, 100)
        mock_viewer.current_pmin = [0.0, 0.0]
        mock_viewer.current_pmax = [100.0, 100.0]
        mock_viewer.orientation = ViewMode.AXIAL
        mock_viewer.slice_idx = 30
        mock_viewer._ORIENTATION_MAP = {
            ViewMode.AXIAL: (2, 0, ("x", "y"), (1, 1))
        }
        mock_viewer.roi_mode = RoiInteractionMode.IDLE
        mock_viewer._is_buffered.return_value = False
        mock_viewer.is_image_orientation.return_value = True
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
        
        with patch("dearpygui.dearpygui.does_item_exist", return_value=True), \
             patch("dearpygui.dearpygui.get_drawing_mouse_pos", return_value=(12.5, 22.5)), \
             patch("dearpygui.dearpygui.set_value"):

            # Edit center via callback
            ui.on_roi_stats_box_center_changed(None, 12.0, {"roi_id": "Box_1", "coord_idx": 0})
            ui.on_roi_stats_box_center_changed(None, 22.0, {"roi_id": "Box_1", "coord_idx": 1})

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


if __name__ == "__main__":
    unittest.main()



