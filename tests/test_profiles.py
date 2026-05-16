import unittest
import numpy as np
from unittest.mock import MagicMock
from vvv.core.profile_manager import ProfileManager
from vvv.core.view_state import ProfileLineState
from vvv.utils import ViewMode


class TestProfileExtraction(unittest.TestCase):
    def setUp(self):
        # 1. Mock the Controller and Data Structures
        self.controller = MagicMock()
        self.pm = ProfileManager(self.controller)

        # 2. Create a 10x10x10 dummy volume with a linear gradient
        # Value at (z, y, x) = z*100 + y*10 + x
        self.shape = (10, 10, 10)  # Z, Y, X
        self.data = np.arange(1000, dtype=np.float32).reshape(self.shape)

        self.vol = MagicMock()
        self.vol.shape3d = self.shape
        self.vol.data = self.data
        self.vol.spacing = np.array([1.0, 1.0, 1.0])  # X, Y, Z in mm
        self.vol.origin = np.array([0.0, 0.0, 0.0])
        self.vol.num_timepoints = 1
        self.vol.name = "TestVol"

        # Identity mapping for coordinate conversion
        def p2v(phys):
            return phys  # Continuous voxel == physical mm

        self.vol.physic_coord_to_voxel_coord.side_effect = p2v

        self.vs = MagicMock()
        self.vs.volume = self.vol

        # Link mocks to controller
        self.controller.volumes = {"v1": self.vol}
        self.controller.view_states = {"v1": self.vs}

    def test_axial_horizontal_accuracy(self):
        """Verify a horizontal line on a specific axial slice."""
        p = ProfileLineState()
        p.orientation = ViewMode.AXIAL
        p.pt1_phys = np.array([2.0, 5.0, 5.0])  # X, Y, Z
        p.pt2_phys = np.array([8.0, 5.0, 5.0])  # 6mm length

        dist, vals = self.pm.get_profile_data("v1", p)

        self.assertIsNotNone(dist)
        self.assertEqual(len(dist), len(vals))

        # Check first and last values (exactly on voxels)
        # z=5, y=5, x=2 -> 5*100 + 5*10 + 2 = 552
        self.assertAlmostEqual(vals[0], 552.0)
        # z=5, y=5, x=8 -> 5*100 + 5*10 + 8 = 558
        self.assertAlmostEqual(vals[-1], 558.0)

        # Check sampling density (should be 1mm intervals + endpoint = 7 points)
        self.assertEqual(len(vals), 7)
        self.assertAlmostEqual(dist[1] - dist[0], 1.0)

    def test_trilinear_interpolation_diagonal(self):
        """Verify diagonal path through the volume using trilinear interpolation."""
        p = ProfileLineState()
        p.orientation = ViewMode.AXIAL
        # From voxel (2,2,2) to (3,3,3)
        p.pt1_phys = np.array([2.0, 2.0, 2.0])
        p.pt2_phys = np.array([3.0, 3.0, 3.0])

        dist, vals = self.pm.get_profile_data("v1", p)

        # Midpoint of the line is at (2.5, 2.5, 2.5)
        # Formula: (222 + 333) / 2 = 277.5
        mid_idx = len(vals) // 2
        self.assertAlmostEqual(vals[mid_idx], 277.5)

    def test_out_of_bounds_handling(self):
        """Ensure out-of-bounds samples return 0.0 without crashing."""
        p = ProfileLineState()
        p.orientation = ViewMode.AXIAL
        p.pt1_phys = np.array([-1.0, -1.0, -1.0])
        p.pt2_phys = np.array([1.0, 1.0, 1.0])

        dist, vals = self.pm.get_profile_data("v1", p)

        # First half should be zero (outside [0, 9]), second half should have data
        self.assertEqual(vals[0], 0.0)
        self.assertGreater(vals[-1], 0.0)

    def test_full_export_structure(self):
        """Verify the JSON export dictionary structure."""
        p = ProfileLineState()
        p.name = "TestProfile"
        p.pt1_phys = np.array([0, 0, 0])
        p.pt2_phys = np.array([1, 1, 1])

        # Mock world_to_display for neutralized voxel reporting
        self.vs.world_to_display.return_value = np.array([0.5, 0.5, 0.5])

        export_data = self.pm.get_full_export_data("v1", p)

        self.assertEqual(export_data["profile_name"], "TestProfile")
        self.assertEqual(export_data["image_name"], "TestVol")
        self.assertTrue(len(export_data["data"]) >= 2)

        first_pt = export_data["data"][0]
        self.assertIn("distance_mm", first_pt)
        self.assertIn("intensity", first_pt)
        self.assertIn("point_phys_mm", first_pt)
        self.assertIn("point_voxel_index", first_pt)
        self.assertIn("point_native_voxel", first_pt)


if __name__ == "__main__":
    unittest.main()
