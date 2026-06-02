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


class MockViewer:
    def __init__(self, image_id, rois):
        self.image_id = image_id
        self.tag = "V1"
        self.view_state = MockViewState(rois)


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

        # 2. Test analyze dropdown change
        dpg.set_value(ui._t("combo_roi_image"), "Active Overlay")
        ui.on_roi_stat_dropdown_changed(None, "Active Overlay", None)
        self.mock_api.get_roi_stats.assert_called_with(
            base_vs_id="img_1", roi_id="roi_1", is_overlay=True
        )

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


if __name__ == "__main__":
    unittest.main()
