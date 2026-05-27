import unittest
from unittest.mock import MagicMock, patch
import numpy as np
import dearpygui.dearpygui as dpg
from vvv.plugins.threshold.plugin_threshold import ThresholdPlugin
from vvv.plugins.threshold.control_threshold import ThresholdController, ThresholdState


class TestThresholdPlugin(unittest.TestCase):
    def setUp(self):
        if not dpg.does_item_exist("global_texture_registry"):
            dpg.add_texture_registry(tag="global_texture_registry")

        self.plugin = ThresholdPlugin()
        self.mock_api = MagicMock()
        self.mock_api.is_beginner_mode = False
        self.mock_api.beginner_tags = []
        
        self.mock_viewer = MagicMock()
        self.mock_viewer.image_id = "test_img_id"
        self.mock_viewer.volume.is_rgb = False
        self.mock_viewer.volume.num_timepoints = 1
        self.mock_viewer.volume.data = np.array([0.0, 50.0, 100.0])
        self.mock_viewer.volume._cached_min_val = 0.0
        self.mock_viewer.volume._cached_max_val = 100.0
        self.mock_viewer.view_state.display.ww = 100.0
        self.mock_viewer.view_state.display.wl = 50.0

        self.mock_api.get_active_viewer.return_value = self.mock_viewer
        self.mock_api.get_image_display_name.return_value = ("image.nii", False)
        self.mock_api.get_volumes.return_value = {"test_img_id": self.mock_viewer.volume}
        self.mock_api.get_view_states.return_value = {"test_img_id": self.mock_viewer.view_state}
        self.mock_api.get_ui_config.return_value = {
            "colors": {
                "text_header": [255, 255, 255],
                "text_active": [255, 255, 255],
                "text_dim": [150, 150, 150],
                "outdated": [255, 100, 100],
            }
        }

        # Wire state for the mock image (mirrors on_image_loaded)
        c = self.plugin._controller
        c.bind(self.mock_api)
        c.on_image_loaded("test_img_id")

    def _state(self):
        """Shortcut to the ThresholdState for the mock image."""
        return self.plugin._controller._states["test_img_id"]

    def test_plugin_metadata(self):
        self.assertEqual(self.plugin.plugin_id, "threshold_plugin")
        self.assertEqual(self.plugin.label, "Threshold")
        self.assertEqual(self.plugin.order, 30)
        self.assertIsNotNone(self.plugin.description)

    def test_create_ui(self):
        with dpg.window(tag="test_threshold_win"):
            self.plugin.create_ui(parent="test_threshold_win", api=self.mock_api)
        self.assertTrue(dpg.does_item_exist(self.plugin.plugin_id))

    def test_update_lifecycle_no_image(self):
        self.mock_api.get_active_viewer.return_value = None
        with dpg.window(tag="test_update_win_no_img"):
            self.plugin.create_ui(parent="test_update_win_no_img", api=self.mock_api)
        self.plugin.update(self.mock_api)

        active_title = self.plugin._controller._t("active_title")
        self.assertEqual(dpg.get_value(active_title), "No Image Selected")

    def test_update_lifecycle_with_image(self):
        with dpg.window(tag="test_update_win_with_img"):
            self.plugin.create_ui(parent="test_update_win_with_img", api=self.mock_api)
        self.plugin.update(self.mock_api)

        active_title = self.plugin._controller._t("active_title")
        self.assertEqual(dpg.get_value(active_title), "image.nii")

    def test_enable_toggle(self):
        c = self.plugin._controller
        state = self._state()
        self.assertFalse(state.is_enabled)

        c.on_enable_toggle(None, True, None)
        self.assertTrue(state.is_enabled)
        self.mock_api.request_refresh.assert_called()

    def test_threshold_drags(self):
        c = self.plugin._controller
        state = self._state()

        # Test preview toggle
        c.on_threshold_drag(c._t("check_ext_preview"), True, None)
        self.assertTrue(state.show_preview)

        # Test subpixel toggle
        c.on_threshold_drag(c._t("check_ext_subpixel"), True, None)
        self.assertTrue(state.subpixel_accurate)

        # Test thickness
        c.on_threshold_drag(c._t("drag_ext_thickness"), 4.0, None)
        self.assertEqual(state.preview_thickness, 4.0)

        # Test preview colors
        c.on_threshold_drag(c._t("color_ext_preview_min"), [0.5, 0.5, 0.5, 1.0], None)
        self.assertEqual(state.preview_color_min, [127, 127, 127, 255])

        c.on_threshold_drag(c._t("color_ext_preview_max"), [1.0, 0.0, 0.0, 1.0], None)
        self.assertEqual(state.preview_color_max, [255, 0, 0, 255])

    def test_threshold_value_drags(self):
        c = self.plugin._controller
        state = self._state()

        # Set values via dpg mock since the callback reads from dpg for drag_ext_threshold_min/max
        with dpg.window(tag="test_values_win"):
            dpg.add_drag_float(tag=c._t("drag_ext_threshold_min"), default_value=10.0)
            dpg.add_drag_float(tag=c._t("drag_ext_threshold_max"), default_value=90.0)

        c.on_threshold_drag(c._t("drag_ext_threshold_min"), None, None)
        self.assertEqual(state.threshold_min, 10.0)

        c.on_threshold_drag(c._t("drag_ext_threshold_max"), None, None)
        self.assertEqual(state.threshold_max, 90.0)

    def test_step_buttons(self):
        c = self.plugin._controller
        state = self._state()
        state.threshold_min = 20.0
        state.threshold_max = 80.0

        # Step size is max(0.1, ww * 0.02) = max(0.1, 100 * 0.02) = 2.0
        # Step min up
        c.on_step_button_clicked(None, None, {"tag": c._t("drag_ext_threshold_min"), "dir": 1})
        self.assertEqual(state.threshold_min, 22.0)

        # Step max down
        c.on_step_button_clicked(None, None, {"tag": c._t("drag_ext_threshold_max"), "dir": -1})
        self.assertEqual(state.threshold_max, 78.0)

    def test_generation_parameters(self):
        c = self.plugin._controller
        state = self._state()

        c.on_gen_mode_changed(c._t("combo_ext_bg_mode"), "Image", None)
        self.assertEqual(state.gen_bg_mode, "Image")

        c.on_gen_mode_changed(c._t("combo_ext_fg_mode"), "Constant", None)
        self.assertEqual(state.gen_fg_mode, "Constant")

        c.on_gen_mode_changed(c._t("input_ext_bg_val"), -1.0, None)
        self.assertEqual(state.gen_bg_val, -1.0)

        c.on_gen_mode_changed(c._t("input_ext_fg_val"), 2.0, None)
        self.assertEqual(state.gen_fg_val, 2.0)

    @patch("threading.Thread")
    def test_create_image_notification(self, mock_thread):
        c = self.plugin._controller
        c.on_create_image_clicked(None, None, None)
        mock_thread.assert_called_once()

    def test_serialization_roundtrip(self):
        c = self.plugin._controller
        state = self._state()
        state.threshold_min = 12.0
        state.threshold_max = 88.0
        state.is_enabled = True

        serialized = c.serialize_image_state("test_img_id")
        self.assertEqual(serialized["threshold_min"], 12.0)
        self.assertEqual(serialized["threshold_max"], 88.0)
        self.assertTrue(serialized["is_enabled"])

        # Reset state and restore
        state.threshold_min = 0.0
        state.threshold_max = 1.0
        state.is_enabled = False

        c.restore_image_state("test_img_id", serialized)
        self.assertEqual(state.threshold_min, 12.0)
        self.assertEqual(state.threshold_max, 88.0)

    @patch("vvv.maths.contours.extract_2d_contours_from_slice")
    def test_update_preview(self, mock_extract):
        mock_extract.return_value = [[[0.0, 0.0], [1.0, 1.0]]]
        c = self.plugin._controller
        state = self._state()
        state.threshold_min = 20.0
        state.threshold_max = 80.0
        state.subpixel_accurate = False

        self.mock_viewer.view_state.contours = {}
        def mock_add_contour(base_id, contour_roi):
            c_id = f"roi_{len(self.mock_viewer.view_state.contours)}"
            contour_roi.id = c_id
            self.mock_viewer.view_state.contours[c_id] = contour_roi
            return c_id
        self.mock_api._controller.contours.add_contour.side_effect = mock_add_contour

        from vvv.utils import ViewMode
        slice_data = np.zeros((10, 10), dtype=np.float32)
        slice_data[3:7, 3:7] = 50.0  # inside threshold range [20, 80]

        # Mock volume aspect ratio
        self.mock_viewer.volume.get_physical_aspect_ratio.return_value = (1.0, 1.0)
        self.mock_viewer.view_state.space.is_active = False

        c.update_preview(
            "test_img_id",
            self.mock_viewer.volume,
            self.mock_viewer.view_state,
            state,
            ViewMode.AXIAL,
            5,
            slice_data
        )

        self.assertEqual(len(self.mock_viewer.view_state.contours), 2)
        
        # Check that polygons were generated
        roi_min = next(r for r in self.mock_viewer.view_state.contours.values() if getattr(r, "is_plugin_draft_min", False))
        self.assertIn(5, roi_min.polygons[ViewMode.AXIAL])
        polys = roi_min.polygons[ViewMode.AXIAL][5]
        self.assertTrue(len(polys) > 0)

    def test_on_image_removed(self):
        c = self.plugin._controller
        self.assertIn("test_img_id", c._states)
        c.on_image_removed("test_img_id")
        self.assertNotIn("test_img_id", c._states)


if __name__ == "__main__":
    unittest.main()
