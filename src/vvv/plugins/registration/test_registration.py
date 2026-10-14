import unittest
from unittest.mock import MagicMock, patch
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
        self.assertEqual(self.plugin.label, "Transform")
        self.assertIsNotNone(self.plugin.description)
        self.assertEqual(self.plugin.order, 40)

    def test_state_lifecycle(self):
        # 1. Standard call (should be ignored, return {})
        self.assertEqual(self.plugin.serialize_image_state("image1", context="history"), {})

        # Setup mock ViewState and space
        self.plugin._controller.bind(self.mock_api)
        vs = MagicMock()
        vs.space.is_active = True
        vs.space.transform_file = "test.tfm"
        vs.space.full_transform_path = "/path/to/test.tfm"
        mock_transform = MagicMock()
        mock_transform.GetParameters.return_value = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]
        mock_transform.GetCenter.return_value = [10.0, 20.0, 30.0]
        vs.space.transform = mock_transform
        self.mock_api.get_view_states.return_value = {"image1": vs}

        # 2. Call with workspace context
        state = self.plugin.serialize_image_state("image1", context="workspace")
        self.assertTrue(state.get("is_active"))
        self.assertEqual(state.get("transform_file"), "test.tfm")
        self.assertEqual(state.get("full_transform_path"), "/path/to/test.tfm")
        self.assertEqual(state.get("transform_params"), [1.0, 2.0, 3.0, 4.0, 5.0, 6.0])
        self.assertEqual(state.get("transform_center"), [10.0, 20.0, 30.0])

        # 3. Call restore_image_state with workspace context
        # Reset vs.space
        vs.space.transform = None
        
        self.plugin.restore_image_state("image1", state, context="workspace")
        
        self.assertTrue(vs.space.is_active)
        self.assertEqual(vs.space.transform_file, "test.tfm")
        self.assertEqual(vs.space.full_transform_path, "/path/to/test.tfm")
        self.assertIsNotNone(vs.space.transform)
        # Euler3DTransform is created from SimpleITK:
        self.assertEqual(list(vs.space.transform.GetParameters()), [1.0, 2.0, 3.0, 4.0, 5.0, 6.0])
        self.assertEqual(list(vs.space.transform.GetCenter()), [10.0, 20.0, 30.0])
        
        self.mock_api.resample_image.assert_called_with("image1")

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

    def test_preview_worker_thread_lifecycle(self):
        controller = self.plugin._controller
        self.assertIsNotNone(controller._preview_queue)
        self.assertIsNotNone(controller._preview_lock)
        controller.destroy()
        self.assertIsNone(controller._preview_queue.get())

    def test_check_preview_slice_needed(self):
        controller = self.plugin._controller
        controller.bind(self.mock_api)
        
        vs = MagicMock()
        vs._preview_R = None
        vs._preview_slice_needed = False
        self.mock_api.get_view_states.return_value = {"image_abc": vs}
        
        controller._check_preview_slice_needed("image_abc")
        self.assertFalse(vs._preview_slice_needed)

        vs._preview_R = MagicMock()
        vs._preview_slice_needed = True
        vs.space.has_rotation.return_value = False
        
        controller._check_preview_slice_needed("image_abc")
        self.assertFalse(vs._preview_slice_needed)
        
        vs._preview_slice_needed = True
        vs.space.has_rotation.return_value = True
        
        rot_mock = MagicMock()
        rot_mock.GetMatrix.return_value = [1, 0, 0, 0, 1, 0, 0, 0, 1]
        rot_mock.GetCenter.return_value = [0, 0, 0]
        vs.space.get_rotation_only_transform.return_value = rot_mock
        
        viewer1 = MagicMock()
        viewer1.image_id = "image_abc"
        viewer1.orientation = 0
        viewer1.slice_idx = 5
        self.mock_api.get_viewers.return_value = {"v1": viewer1}

        controller._check_preview_slice_needed("image_abc")
        req = controller._preview_queue.get()
        self.assertEqual(req[0], "image_abc")
        controller.destroy()

    def test_auto_resample_schedule(self):
        controller = self.plugin._controller
        controller.bind(self.mock_api)
        
        # Setup mock active viewer and view state
        viewer = MagicMock()
        viewer.image_id = "image_abc"
        vs = MagicMock()
        vs.needs_resample = True
        self.mock_api.get_active_viewer.return_value = viewer
        self.mock_api.get_view_states.return_value = {"image_abc": vs}

        # Mock the auto-resample checkbox to be True
        if not dpg.is_dearpygui_running():
            dpg.create_context()
        with dpg.window(tag="test_parent"):
            self.plugin.create_ui(parent="test_parent", api=self.mock_api)

        dpg.set_value("registration_plugin_check_reg_auto_resample", True)

        # Call on_reg_manual_changed
        controller.on_reg_manual_changed(None, None, None)

        # The timer should be scheduled
        self.assertIsNotNone(controller._auto_timer)
        self.assertEqual(controller._auto_timer_vs_id, "image_abc")

        # Clean up
        controller.destroy()
        dpg.delete_item("test_parent")

    def test_empty_state_and_reload(self):
        controller = self.plugin._controller
        controller.bind(self.mock_api)
        
        # 1. Test Empty State UI hiding
        if not dpg.is_dearpygui_running():
            dpg.create_context()
        with dpg.window(tag="test_parent"):
            self.plugin.create_ui(parent="test_parent", api=self.mock_api)
            
        self.mock_api.get_active_viewer.return_value = None
        self.plugin.update(self.mock_api)
        
        # group_registration_controls should be hidden
        self.assertFalse(dpg.is_item_shown("registration_plugin_group_registration_controls"))
        
        # 2. Test Reload Detection
        vol = MagicMock()
        vol.data = np.zeros((10, 10, 10))
        self.mock_api.get_volumes.return_value = {"image_abc": vol}

        vs = MagicMock()
        vs.space.is_active = True
        self.mock_api.get_view_states.return_value = {"image_abc": vs}

        # Registration now happens explicitly when a transform is activated
        # (via callbacks or restore_image_state), not lazily in update().
        controller._ensure_tracked("image_abc")
        self.plugin.update(self.mock_api)
        self.mock_api.resample_image.assert_not_called()
        
        # Simulate reload by replacing data array
        vol.data = np.zeros((10, 10, 10))  # different id()
        self.plugin.update(self.mock_api)
        
        # resample_image should be called
        self.mock_api.resample_image.assert_called_with("image_abc")
        self.assertTrue(vs.needs_resample)
        
        dpg.delete_item("test_parent")

    def test_beginner_mode(self):
        if not dpg.is_dearpygui_running():
            dpg.create_context()
        with dpg.window(tag="test_parent"):
            self.plugin.create_ui(parent="test_parent", api=self.mock_api)
            
        viewer = MagicMock()
        viewer.image_id = "image_abc"
        viewer.view_state = MagicMock()
        viewer.view_state.space.transform = None
        viewer.volume = MagicMock()
        viewer.volume.shape3d = [100, 100, 100]
        self.mock_api.get_active_viewer.return_value = viewer
        self.mock_api.get_image_display_name.return_value = ("Image ABC", False)
        
        # 1. Test is_beginner_mode = True
        self.mock_api.is_beginner_mode = True
        self.plugin.update(self.mock_api)
        self.assertTrue(dpg.is_item_shown("registration_plugin_group_reg_cor"))
        self.assertTrue(dpg.is_item_shown("registration_plugin_group_reg_matrix_section"))
        
        # 2. Test is_beginner_mode = False
        self.mock_api.is_beginner_mode = False
        self.plugin.update(self.mock_api)
        self.assertTrue(dpg.is_item_shown("registration_plugin_group_reg_cor"))
        self.assertTrue(dpg.is_item_shown("registration_plugin_group_reg_matrix_section"))
        
        dpg.delete_item("test_parent")

    def test_on_image_loaded_auto_applies_tfm(self):
        import tempfile, os
        import SimpleITK as sitk
        from unittest.mock import patch

        controller = self.plugin._controller
        controller.bind(self.mock_api)

        with tempfile.TemporaryDirectory() as tmp_dir:
            img_path = os.path.join(tmp_dir, "patient_scan.nii.gz")
            tfm_path = os.path.join(tmp_dir, "patient_scan.tfm")

            # Write a valid dummy ITK transform
            t = sitk.Euler3DTransform()
            t.SetTranslation((12.0, -5.0, 3.5))
            sitk.WriteTransform(t, tfm_path)

            vol = MagicMock()
            vol.file_paths = [img_path]
            vol.name = "patient_scan"

            vs = MagicMock()
            vs.space.transform = None
            vs.camera.crosshair_phys_coord = [10.0, 20.0, 30.0]

            self.mock_api.get_volumes.return_value = {"img1": vol}
            self.mock_api.get_view_states.return_value = {"img1": vs}
            self.mock_api.load_transform.return_value = True

            controller.on_image_loaded("img1")

            self.mock_api.load_transform.assert_called_with("img1", tfm_path)
            self.assertEqual(vs.space.full_transform_path, tfm_path)
            self.assertTrue(vs.space.is_active)
            self.mock_api.resample_image.assert_called_with("img1")
            self.mock_api.update_all_viewers_of_image.assert_called_with("img1")
            self.mock_api.notify.assert_called_with("Auto-applied transform: patient_scan.tfm")

    def test_on_image_loaded_no_tfm(self):
        controller = self.plugin._controller
        controller.bind(self.mock_api)

        vol = MagicMock()
        vol.file_paths = ["/non/existent/path/scan.mha"]
        vol.name = "scan"

        vs = MagicMock()
        vs.space.transform = None

        self.mock_api.get_volumes.return_value = {"img1": vol}
        self.mock_api.get_view_states.return_value = {"img1": vs}

        controller.on_image_loaded("img1")

        self.mock_api.load_transform.assert_not_called()
        self.mock_api.resample_image.assert_not_called()

    @patch("vvv.plugins.registration.control_registration.save_file_dialog")
    def test_save_as_indicates_tfm_and_appends_extension(self, mock_save_dialog):
        controller = self.plugin._controller
        controller.bind(self.mock_api)

        viewer = MagicMock()
        viewer.image_id = "img1"
        vs = MagicMock()
        vs.space.transform = MagicMock()
        vs.space.transform_file = "None"
        vs.space.full_transform_path = None
        viewer.view_state = vs

        vol = MagicMock()
        vol.file_paths = ["/data/study/brain.nii.gz"]
        vol.name = "brain"

        self.mock_api.get_active_viewer.return_value = viewer
        self.mock_api.get_volumes.return_value = {"img1": vol}

        # Simulate user entering name without extension in save dialog
        mock_save_dialog.return_value = "/data/study/custom_reg"

        controller.on_reg_save_as_clicked(None, None, None)

        # Dialog should have title indicating (Base) and (.tfm) and default_name based on image
        mock_save_dialog.assert_called_once_with(
            "Save Transform As (Base) (.tfm)",
            default_name="brain.tfm",
            start_dir="/data/study",
        )

        # .tfm should have been appended automatically
        self.mock_api.save_transform.assert_called_once_with("img1", "/data/study/custom_reg.tfm")
        self.assertEqual(vs.space.full_transform_path, "/data/study/custom_reg.tfm")

    def test_target_switching_base_and_fusion(self):
        controller = self.plugin._controller
        controller.bind(self.mock_api)

        # Base image
        base_vs = MagicMock()
        base_vs.display.overlay.image_id = "img_fusion"
        base_vs.space.transform = None
        base_vol = MagicMock()
        base_vol.name = "base_scan"

        # Fusion overlay image
        ov_vs = MagicMock()
        ov_vs.display.overlay.image_id = None
        ov_vs.space.transform = None
        ov_vol = MagicMock()
        ov_vol.name = "fusion_scan"

        viewer = MagicMock()
        viewer.image_id = "img_base"
        viewer.view_state = base_vs
        viewer.volume = base_vol

        self.mock_api.get_active_viewer.return_value = viewer
        self.mock_api.get_view_states.return_value = {"img_base": base_vs, "img_fusion": ov_vs}
        self.mock_api.get_volumes.return_value = {"img_base": base_vol, "img_fusion": ov_vol}

        # Initially defaults to Base
        tid, tvs, tvol, role = controller.get_target_info()
        self.assertEqual(tid, "img_base")
        self.assertEqual(role, "Base")
        self.assertEqual(tvs, base_vs)

        # Switch to Fusion
        controller.on_reg_target_changed(None, "Fusion", None)
        tid, tvs, tvol, role = controller.get_target_info()
        self.assertEqual(tid, "img_fusion")
        self.assertEqual(role, "Fusion")
        self.assertEqual(tvs, ov_vs)

        # Switch back to Base
        controller.on_reg_target_changed(None, "Base", None)
        tid, tvs, tvol, role = controller.get_target_info()
        self.assertEqual(tid, "img_base")
        self.assertEqual(role, "Base")

    def test_invert_transform(self):
        import SimpleITK as sitk

        controller = self.plugin._controller
        controller.bind(self.mock_api)

        t = sitk.Euler3DTransform()
        t.SetTranslation((15.0, -10.0, 5.0))

        vs = MagicMock()
        vs.space.transform = t
        vs.space.has_rotation.return_value = False

        viewer = MagicMock()
        viewer.image_id = "img1"
        viewer.view_state = vs
        viewer.volume = MagicMock()

        self.mock_api.get_active_viewer.return_value = viewer
        self.mock_api.get_view_states.return_value = {"img1": vs}
        self.mock_api.get_volumes.return_value = {"img1": viewer.volume}

        controller.on_reg_invert_clicked(None, None, None)

        # Verify update_transform_manual was called with inverted translation (-15, 10, -5)
        call_args = self.mock_api.update_transform_manual.call_args[0]
        self.assertEqual(call_args[0], "img1")
        self.assertAlmostEqual(call_args[1], -15.0)
        self.assertAlmostEqual(call_args[2], 10.0)
        self.assertAlmostEqual(call_args[3], -5.0)
        self.mock_api.notify.assert_called_with("Inverted transform (Base)")


if __name__ == "__main__":
    unittest.main()
