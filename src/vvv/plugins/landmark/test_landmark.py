import unittest
import unittest.mock
import numpy as np
import SimpleITK as sitk

from vvv.maths.image import VolumeData
from vvv.core.view_state import ViewState
from vvv.plugins.landmark.landmark_state import Landmark
from vvv.plugins.landmark.control_landmark import LandmarkPluginController
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


if __name__ == "__main__":
    unittest.main()
