import unittest
import unittest.mock
import numpy as np
import SimpleITK as sitk

from vvv.maths.image import VolumeData
from vvv.core.view_state import ViewState
from vvv.plugins.landmark.landmark_state import Landmark
from vvv.plugins.landmark.control_landmark import LandmarkPluginController
from vvv.plugins.landmark.ui_landmark import LandmarkPluginUI
from vvv.plugins.landmark.plugin_landmark import LandmarkPlugin


class TestLandmarkPlugin(unittest.TestCase):
    def setUp(self):
        # Create a synthetic 3D volume for testing
        arr = np.zeros((10, 20, 30), dtype=np.float32)
        sitk_img = sitk.GetImageFromArray(arr)
        sitk_img.SetSpacing((1.0, 1.0, 2.0))
        sitk_img.SetOrigin((0.0, 0.0, 0.0))
        self.volume = VolumeData("test_img.nii", preloaded_sitk=sitk_img)
        self.vs = ViewState(self.volume)

    def test_viewstate_landmarks_initialization(self):
        self.assertTrue(hasattr(self.vs, "landmarks"))
        self.assertEqual(self.vs.landmarks, {})

    def test_landmark_data_model(self):
        lm = Landmark(
            id="lm_1",
            name="Target 1",
            pt_phys=[10.0, 15.0, 20.0],
            color=[255, 0, 0, 255],
            visible=True,
        )
        self.assertEqual(lm.id, "lm_1")
        self.assertEqual(lm.name, "Target 1")
        self.assertEqual(lm.pt_phys, [10.0, 15.0, 20.0])
        self.assertEqual(lm.color, [255, 0, 0, 255])
        self.assertTrue(lm.visible)

        d = lm.to_dict()
        lm_restored = Landmark.from_dict(d)
        self.assertEqual(lm_restored.id, lm.id)
        self.assertEqual(lm_restored.name, lm.name)
        self.assertEqual(lm_restored.pt_phys, lm.pt_phys)
        self.assertEqual(lm_restored.color, lm.color)
        self.assertEqual(lm_restored.visible, lm.visible)

    def test_landmark_controller_crud(self):
        ctrl = LandmarkPluginController("landmark_plugin")

        # Manually add landmark to ViewState
        lm = Landmark(id="lm_001", name="L1", pt_phys=[5.0, 5.0, 5.0])
        self.vs.landmarks[lm.id] = lm

        self.assertEqual(len(self.vs.landmarks), 1)
        self.assertIn("lm_001", self.vs.landmarks)

        # Update name
        lm.name = "L1_Updated"
        self.assertEqual(self.vs.landmarks["lm_001"].name, "L1_Updated")

        # Update color
        lm.color = [0, 255, 0, 255]
        self.assertEqual(self.vs.landmarks["lm_001"].color, [0, 255, 0, 255])

        # Delete
        del self.vs.landmarks["lm_001"]
        self.assertEqual(len(self.vs.landmarks), 0)

    def test_center_on_landmark(self):
        ctrl = LandmarkPluginController("landmark_plugin")
        mock_api = unittest.mock.MagicMock()
        mock_api.get_active_viewer.return_value = unittest.mock.MagicMock(image_id="img1", view_state=self.vs)
        mock_api.get_view_states.return_value = {"img1": self.vs}
        mock_api.get_viewers.return_value = {}
        ctrl.bind(mock_api)

        lm = Landmark(id="lm_002", name="L2", pt_phys=[12.0, 34.0, 56.0])
        self.vs.landmarks[lm.id] = lm

        ctrl.center_on_landmark("lm_002", image_id="img1")
        coords = self.vs.camera.crosshair_phys_coord
        self.assertIsNotNone(coords)
        self.assertEqual(list(coords), [12.0, 34.0, 56.0])

    def test_ui_callbacks_with_none_api(self):
        from vvv.plugins.landmark.ui_landmark import LandmarkPluginUI
        ctrl = LandmarkPluginController("landmark_plugin")
        ui = LandmarkPluginUI("landmark_plugin", ctrl)
        
        lm = Landmark(id="lm_001", name="L1", pt_phys=[10.0, 20.0, 30.0])
        self.vs.landmarks[lm.id] = lm

        mock_api = unittest.mock.MagicMock()
        mock_api.get_active_viewer.return_value = unittest.mock.MagicMock(image_id="img1", view_state=self.vs)
        mock_api.get_view_states.return_value = {"img1": self.vs}
        ctrl.bind(mock_api)

        # ui._api is None at this point. Should not raise AttributeError when toggling visible/show_name
        ui.on_landmark_toggle_visible(None, None, "lm_001")
        self.assertFalse(lm.visible)

        ui.on_landmark_toggle_show_name(None, None, "lm_001")
        self.assertFalse(lm.show_name)

    def test_batch_actions_and_filtering(self):
        ctrl = LandmarkPluginController("landmark_plugin")
        mock_api = unittest.mock.MagicMock()
        mock_api.get_active_viewer.return_value = unittest.mock.MagicMock(image_id="img1", view_state=self.vs)
        mock_api.get_view_states.return_value = {"img1": self.vs}
        ctrl.bind(mock_api)

        # Add 3 landmarks: Tumor_1, Tumor_2, Vessel_1
        lm1 = Landmark(id="lm_1", name="Tumor_1", pt_phys=[1.0, 1.0, 1.0], color=[255, 0, 0, 255])
        lm2 = Landmark(id="lm_2", name="Tumor_2", pt_phys=[2.0, 2.0, 2.0], color=[255, 0, 0, 255])
        lm3 = Landmark(id="lm_3", name="Vessel_1", pt_phys=[3.0, 3.0, 3.0], color=[0, 255, 0, 255])
        self.vs.landmarks = {"lm_1": lm1, "lm_2": lm2, "lm_3": lm3}

        # Filter for 'Tumor'
        ctrl.on_filter_changed("Tumor")
        self.assertEqual(ctrl.landmark_filters["img1"], "tumor")

        # Batch color change (blue) on filtered (Tumor_1 & Tumor_2 only)
        ctrl.on_batch_color_changed([0, 0, 255, 255])
        self.assertEqual(lm1.color, [0, 0, 255, 255])
        self.assertEqual(lm2.color, [0, 0, 255, 255])
        self.assertEqual(lm3.color, [0, 255, 0, 255])

        # Batch toggle visibility on filtered
        ctrl.on_batch_toggle_visible()
        self.assertFalse(lm1.visible)
        self.assertFalse(lm2.visible)
        self.assertTrue(lm3.visible)

        # Batch delete on filtered
        ctrl.on_batch_delete_clicked()
        self.assertNotIn("lm_1", self.vs.landmarks)
        self.assertNotIn("lm_2", self.vs.landmarks)
        self.assertIn("lm_3", self.vs.landmarks)

        # Clear filter
        ctrl.on_clear_filter_clicked()
        self.assertEqual(ctrl.landmark_filters["img1"], "")

    def test_grid_snapping(self):
        ctrl = LandmarkPluginController("landmark_plugin")
        mock_api = unittest.mock.MagicMock()
        mock_api.get_active_viewer.return_value = unittest.mock.MagicMock(image_id="img1", view_state=self.vs)
        mock_api.get_view_states.return_value = {"img1": self.vs}
        mock_api.get_volumes.return_value = {"img1": self.volume}
        ctrl.bind(mock_api)

        # Off-grid physical coordinate: [0.3, 0.7, 1.4] -> spacing [1.0, 1.0, 2.0]
        # Voxel idx = [0.3, 0.7, 0.7] -> round [0, 1, 1] -> phys [0.0, 1.0, 2.0]
        lm = Landmark(id="lm_snap", name="SnapMe", pt_phys=[0.3, 0.7, 1.4])
        self.vs.landmarks["lm_snap"] = lm

        ctrl.snap_landmark_to_grid("lm_snap", image_id="img1")
        self.assertEqual(lm.pt_phys, [0.0, 1.0, 2.0])

    def test_json_and_csv_storage(self):
        import tempfile
        import os

        ctrl = LandmarkPluginController("landmark_plugin")
        mock_api = unittest.mock.MagicMock()
        mock_api.get_active_viewer.return_value = unittest.mock.MagicMock(image_id="img1", view_state=self.vs)
        mock_api.get_view_states.return_value = {"img1": self.vs}
        ctrl.bind(mock_api)

        lm1 = Landmark(id="lm_1", name="Point_A", pt_phys=[10.0, 20.0, 30.0], color=[255, 0, 0, 255])
        lm2 = Landmark(id="lm_2", name="Point_B", pt_phys=[40.0, 50.0, 60.0], color=[0, 255, 0, 255])
        self.vs.landmarks = {"lm_1": lm1, "lm_2": lm2}

        with tempfile.TemporaryDirectory() as tmpdir:
            # 1. Test JSON Save & Load
            json_path = os.path.join(tmpdir, "test_landmarks.json")
            ctrl.save_landmarks(json_path, image_id="img1")
            self.assertTrue(os.path.exists(json_path))

            # Reset viewstate landmarks & reload
            self.vs.landmarks = {}
            ctrl.load_landmarks(json_path, image_id="img1")
            self.assertEqual(len(self.vs.landmarks), 2)
            self.assertIn("lm_1", self.vs.landmarks)
            self.assertEqual(self.vs.landmarks["lm_1"].name, "Point_A")

            # 2. Test CSV Save & Load
            csv_path = os.path.join(tmpdir, "test_landmarks.csv")
            ctrl.save_landmarks(csv_path, image_id="img1")
            self.assertTrue(os.path.exists(csv_path))

            self.vs.landmarks = {}
            ctrl.load_landmarks(csv_path, image_id="img1")
            self.assertEqual(len(self.vs.landmarks), 2)
            self.assertEqual(self.vs.landmarks["lm_1"].name, "Point_A")
            self.assertEqual(self.vs.landmarks["lm_1"].pt_phys, [10.0, 20.0, 30.0])

    def test_workspace_serialization(self):
        ctrl = LandmarkPluginController("landmark_plugin")
        mock_api = unittest.mock.MagicMock()
        mock_api.get_active_viewer.return_value = unittest.mock.MagicMock(image_id="img1", view_state=self.vs)
        mock_api.get_view_states.return_value = {"img1": self.vs}
        ctrl.bind(mock_api)

        lm = Landmark(id="lm_1", name="P1", pt_phys=[5.0, 5.0, 5.0])
        self.vs.landmarks = {"lm_1": lm}

        # History context must return empty dict
        history_state = ctrl.serialize_image_state("img1", context="history")
        self.assertEqual(history_state, {})

        # Workspace context: serializes landmarks list
        ws_state = ctrl.serialize_image_state("img1", context="workspace")
        self.assertIn("landmarks", ws_state)
        self.assertEqual(len(ws_state["landmarks"]), 1)

        # Restore from dict in workspace context
        self.vs.landmarks = {}
        ctrl.restore_image_state("img1", ws_state, context="workspace")
        self.assertEqual(len(self.vs.landmarks), 1)
        self.assertEqual(self.vs.landmarks["lm_1"].name, "P1")

        # Restoring with history context must not restore landmarks
        self.vs.landmarks = {}
        ctrl.restore_image_state("img1", ws_state, context="history")
        self.assertEqual(len(self.vs.landmarks), 0)

    def test_load_landmarks_dialog_extensions(self):
        ctrl = LandmarkPluginController("landmark_plugin")
        with unittest.mock.patch("vvv.plugins.landmark.control_landmark.open_file_dialog") as mock_dialog:
            ctrl.on_btn_load_clicked(None, None, None)
            mock_dialog.assert_called_once_with(
                "Load Landmark File (.json, .csv)",
                multiple=False,
                extensions=["json", "csv"],
            )


    def test_batch_toolbar_dynamic_icons(self):
        ui = LandmarkPluginUI("landmark_plugin", LandmarkPluginController("landmark_plugin"))
        mock_api = unittest.mock.MagicMock()
        mock_viewer = unittest.mock.MagicMock(image_id="img1", view_state=self.vs, volume=unittest.mock.MagicMock())
        mock_api.get_active_viewer.return_value = mock_viewer
        mock_api.get_view_states.return_value = {"img1": self.vs}
        ui._c.bind(mock_api)

        lm1 = Landmark(id="lm_1", name="P1", pt_phys=[1.0, 2.0, 3.0], visible=True, show_name=True)
        lm2 = Landmark(id="lm_2", name="P2", pt_phys=[4.0, 5.0, 6.0], visible=False, show_name=False)
        self.vs.landmarks = {"lm_1": lm1, "lm_2": lm2}

        # Any visible = True -> "\uf06e", Any show_name = True -> "\uf02b"
        with unittest.mock.patch("dearpygui.dearpygui.does_item_exist", return_value=True), \
             unittest.mock.patch("dearpygui.dearpygui.set_item_label") as mock_set_label, \
             unittest.mock.patch("dearpygui.dearpygui.delete_item"):
            ui.update_ui(mock_api)
            mock_set_label.assert_any_call("landmark_plugin_lm_batch_toggle_visible", "\uf06e")
            mock_set_label.assert_any_call("landmark_plugin_lm_batch_toggle_names", "\uf02b")

        # Hide all, hide all names
        lm1.visible = False
        lm1.show_name = False
        ui._last_state_key = None
        with unittest.mock.patch("dearpygui.dearpygui.does_item_exist", return_value=True), \
             unittest.mock.patch("dearpygui.dearpygui.set_item_label") as mock_set_label, \
             unittest.mock.patch("dearpygui.dearpygui.delete_item"):
            ui.update_ui(mock_api)
            mock_set_label.assert_any_call("landmark_plugin_lm_batch_toggle_visible", "\uf070")
    def test_batch_reset_colors(self):
        ctrl = LandmarkPluginController("landmark_plugin")
        mock_api = unittest.mock.MagicMock()
        mock_api.get_active_viewer.return_value = unittest.mock.MagicMock(image_id="img1", view_state=self.vs)
        mock_api.get_view_states.return_value = {"img1": self.vs}
        ctrl.bind(mock_api)

        lm1 = Landmark(id="lm_1", name="P1", pt_phys=[1.0, 2.0, 3.0], color=[255, 255, 255, 255])
        lm2 = Landmark(id="lm_2", name="P2", pt_phys=[4.0, 5.0, 6.0], color=[0, 0, 0, 255])
        self.vs.landmarks = {"lm_1": lm1, "lm_2": lm2}

        ctrl.on_batch_reset_colors()
        from vvv.config import ROI_COLORS
        c0 = ROI_COLORS[0]
        c1 = ROI_COLORS[1]
        self.assertEqual(lm1.color, [c0[0], c0[1], c0[2], 255])
        self.assertEqual(lm2.color, [c1[0], c1[1], c1[2], 255])


if __name__ == "__main__":
    unittest.main()

