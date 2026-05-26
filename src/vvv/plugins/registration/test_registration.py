import unittest
from unittest.mock import MagicMock
import numpy as np
import dearpygui.dearpygui as dpg
from vvv.plugins.registration.plugin_registration import RegistrationPlugin


class TestRegistrationPlugin(unittest.TestCase):
    def setUp(self):
        self.plugin = RegistrationPlugin()
        self.mock_api = MagicMock()
        self.mock_api.is_beginner_mode = False
        self.mock_api.get_ui_config.return_value = {
            "colors": {
                "text_header": [255, 255, 255],
                "text_active": [255, 255, 255],
                "text_dim": [128, 128, 128],
                "outdated": [255, 165, 0],
            }
        }
        self.mock_api.get_active_viewer.return_value = None

    def test_metadata(self):
        self.assertEqual(self.plugin.plugin_id, "registration_plugin")
        self.assertEqual(self.plugin.label, "Registration Plugin")
        self.assertIsNotNone(self.plugin.description)
        self.assertEqual(self.plugin.order, 40)

    def test_state_lifecycle(self):
        self.assertEqual(self.plugin.serialize_image_state("image1"), {})
        self.plugin.restore_image_state("image1", {})

    def test_create_ui(self):
        if not dpg.is_dearpygui_running():
            dpg.create_context()
        with dpg.window(tag="test_parent"):
            self.plugin.create_ui(parent="test_parent", api=self.mock_api)
        self.assertTrue(dpg.does_item_exist("registration_plugin"))
        dpg.delete_item("test_parent")

    def test_update_ui(self):
        if not dpg.is_dearpygui_running():
            dpg.create_context()
        with dpg.window(tag="test_parent"):
            self.plugin.create_ui(parent="test_parent", api=self.mock_api)

        # Update when no viewer active
        self.plugin.update(self.mock_api)

        # Update when viewer is active
        viewer = MagicMock()
        viewer.image_id = "image_abc"
        viewer.view_state = MagicMock()
        viewer.view_state.space = MagicMock()
        viewer.view_state.space.transform_file = "my_matrix.tfm"
        viewer.view_state.space.transform = None
        viewer.volume = MagicMock()
        viewer.volume.shape3d = [100, 100, 100]

        self.mock_api.get_active_viewer.return_value = viewer
        self.mock_api.get_image_display_name.return_value = ("Image ABC", False)

        self.plugin.update(self.mock_api)
        self.assertEqual(dpg.get_value("registration_plugin_text_reg_active_title"), "Image ABC")
        self.assertEqual(dpg.get_value("registration_plugin_text_reg_filename"), "my_matrix.tfm")

        dpg.delete_item("test_parent")

    def test_slider_drag_and_manual_change(self):
        if not dpg.is_dearpygui_running():
            dpg.create_context()
        with dpg.window(tag="test_parent"):
            self.plugin.create_ui(parent="test_parent", api=self.mock_api)

        # Mock an active viewer and volume
        viewer = MagicMock()
        viewer.image_id = "image_abc"
        viewer.view_state = MagicMock()
        viewer.view_state.space = MagicMock()
        viewer.view_state.space.transform_file = "my_matrix.tfm"
        viewer.view_state.space.transform = MagicMock()
        viewer.volume = MagicMock()
        viewer.volume.shape3d = [100, 100, 100]

        self.mock_api.get_active_viewer.return_value = viewer
        self.mock_api.get_view_states.return_value = {"image_abc": viewer.view_state}
        self.mock_api.get_ui_config.return_value = {
            "colors": {
                "text_header": [255, 255, 255],
                "text_active": [255, 255, 255],
                "text_dim": [128, 128, 128],
                "outdated": [255, 165, 0],
                "warning": [255, 0, 0],
                "working": [0, 0, 255],
            }
        }

        # Simulate setting values on the UI sliders
        dpg.set_value("registration_plugin_drag_reg_rx", 10.0)
        dpg.set_value("registration_plugin_drag_reg_ry", 20.0)
        dpg.set_value("registration_plugin_drag_reg_rz", 30.0)
        dpg.set_value("registration_plugin_drag_reg_tx", 40.0)
        dpg.set_value("registration_plugin_drag_reg_ty", 50.0)
        dpg.set_value("registration_plugin_drag_reg_tz", 60.0)

        # Call manual changed callback
        self.plugin._controller.on_reg_manual_changed(None, None, None)

        # Verify that update_transform_manual was called with correct values (Tx, Ty, Tz, Rx, Ry, Rz)
        self.mock_api.update_transform_manual.assert_called_with(
            "image_abc",
            40.0, 50.0, 60.0,
            10.0, 20.0, 30.0
        )

        dpg.delete_item("test_parent")

    def test_reset_clicked(self):
        if not dpg.is_dearpygui_running():
            dpg.create_context()
        with dpg.window(tag="test_parent"):
            self.plugin.create_ui(parent="test_parent", api=self.mock_api)

        viewer = MagicMock()
        viewer.image_id = "image_abc"
        viewer.view_state = MagicMock()
        self.mock_api.get_active_viewer.return_value = viewer
        self.mock_api.get_view_states.return_value = {"image_abc": viewer.view_state}

        # Set some slider values first
        dpg.set_value("registration_plugin_drag_reg_rx", 10.0)

        # Click Reset
        self.plugin._controller.on_reg_reset_clicked(None, None, None)

        # Check that sliders are reset to 0.0
        self.assertEqual(dpg.get_value("registration_plugin_drag_reg_rx"), 0.0)
        self.mock_api.update_transform_manual.assert_called_with("image_abc", 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
        self.mock_api.resample_image.assert_called_with("image_abc")

        dpg.delete_item("test_parent")

    def test_cor_to_crosshair(self):
        if not dpg.is_dearpygui_running():
            dpg.create_context()
        with dpg.window(tag="test_parent"):
            self.plugin.create_ui(parent="test_parent", api=self.mock_api)

        viewer = MagicMock()
        viewer.image_id = "image_abc"
        viewer.view_state = MagicMock()
        viewer.view_state.camera.crosshair_phys_coord = [10.0, 20.0, 30.0]
        
        # We need to mock space.transform with a mock that supports TransformPoint returning a sequence
        mock_transform = MagicMock()
        mock_transform.TransformPoint.return_value = [15.0, 25.0, 35.0]
        viewer.view_state.space.transform = mock_transform
        
        self.mock_api.get_active_viewer.return_value = viewer

        # Click Snap to Crosshair
        self.plugin._controller.on_reg_cor_to_crosshair_clicked(None, None, None)

        # Verify that SetCenter was called with the physical crosshair coordinates
        mock_transform.SetCenter.assert_called_with((10.0, 20.0, 30.0))
        # Verify that SetTranslation was called with the translation difference (15-10, 25-20, 35-30)
        mock_transform.SetTranslation.assert_called_with((5.0, 5.0, 5.0))

        dpg.delete_item("test_parent")


if __name__ == "__main__":
    unittest.main()
