import unittest
import numpy as np
from unittest.mock import MagicMock
from vvv.core.profile_manager import ProfileManager
from vvv.core.view_state import ProfileLineState
from vvv.utils import ViewMode


def make_profile(pt1, pt2) -> ProfileLineState:
    p = ProfileLineState()
    p.pt1_phys = np.array(pt1, dtype=float)
    p.pt2_phys = np.array(pt2, dtype=float)
    return p


class TestProfileExtraction(unittest.TestCase):
    def setUp(self):
        self.controller = MagicMock()
        self.pm = ProfileManager(self.controller)

        # 10x10x10 volume with a linear gradient: value at (z, y, x) = z*100 + y*10 + x
        # This lets us analytically verify every interpolated value.
        self.shape = (10, 10, 10)  # Z, Y, X
        self.data = np.arange(1000, dtype=np.float32).reshape(self.shape)

        self.vol = MagicMock()
        self.vol.shape3d = self.shape
        self.vol.data = self.data
        self.vol.spacing = np.array([1.0, 1.0, 1.0])  # X, Y, Z in mm
        self.vol.num_timepoints = 1
        self.vol.name = "TestVol"
        self.vol.is_dvf = False
        self.vol.is_rgb = False
        self.vol.physic_coord_to_voxel_coord.side_effect = lambda p: p  # identity

        self.vs = MagicMock()
        self.vs.camera.time_idx = 0
        self.vs.world_to_display.return_value = np.array([0.0, 0.0, 0.0])

        self.controller.volumes = {"v1": self.vol}
        self.controller.view_states = {"v1": self.vs}

    def _get_profile(self, pt1, pt2):
        """Return (dist, vals) and assert neither is None."""
        dist, vals = self.pm.get_profile_data("v1", make_profile(pt1, pt2))
        assert dist is not None
        assert vals is not None
        return dist, vals

    def _get_export(self, pt1, pt2, name="p") -> dict:
        """Return export dict and assert it is a dict (not the empty-list sentinel)."""
        p = make_profile(pt1, pt2)
        p.name = name
        result = self.pm.get_full_export_data("v1", p)
        assert isinstance(result, dict)
        return result

    # ------------------------------------------------------------------
    # Axis-aligned accuracy
    # ------------------------------------------------------------------

    def test_x_axis_accuracy(self):
        """Horizontal profile along X: values must match z*100 + y*10 + x exactly."""
        dist, vals = self._get_profile([2.0, 5.0, 5.0], [8.0, 5.0, 5.0])

        self.assertEqual(len(dist), 7)   # 6 mm at 1 mm step + 1
        self.assertAlmostEqual(dist[-1], 6.0)

        # z=5, y=5, x=2..8  →  552, 553, ..., 558
        for i, expected_x in enumerate(range(2, 9)):
            self.assertAlmostEqual(vals[i], 5 * 100 + 5 * 10 + expected_x,
                                   msg=f"Wrong value at x={expected_x}")

    def test_y_axis_accuracy(self):
        """Vertical profile along Y: values must match z*100 + y*10 + x exactly."""
        dist, vals = self._get_profile([3.0, 2.0, 4.0], [3.0, 8.0, 4.0])

        self.assertEqual(len(vals), 7)   # 6 mm along Y
        self.assertAlmostEqual(dist[-1], 6.0)

        # z=4, x=3, y=2..8  →  4*100 + y*10 + 3
        for i, expected_y in enumerate(range(2, 9)):
            self.assertAlmostEqual(vals[i], 4 * 100 + expected_y * 10 + 3,
                                   msg=f"Wrong value at y={expected_y}")

    def test_z_axis_accuracy(self):
        """Depth profile along Z: values must match z*100 + y*10 + x exactly."""
        dist, vals = self._get_profile([3.0, 4.0, 1.0], [3.0, 4.0, 7.0])

        self.assertEqual(len(vals), 7)   # 6 mm along Z
        self.assertAlmostEqual(dist[-1], 6.0)

        # y=4, x=3, z=1..7  →  z*100 + 43
        for i, expected_z in enumerate(range(1, 8)):
            self.assertAlmostEqual(vals[i], expected_z * 100 + 4 * 10 + 3,
                                   msg=f"Wrong value at z={expected_z}")

    # ------------------------------------------------------------------
    # Trilinear interpolation per axis
    # ------------------------------------------------------------------

    def _get_profile_fine(self, pt1, pt2):
        """Run a profile with 0.5 mm spacing to force a sub-voxel midpoint."""
        self.vol.spacing = np.array([0.5, 0.5, 0.5])
        dist, vals = self._get_profile(pt1, pt2)
        self.vol.spacing = np.array([1.0, 1.0, 1.0])
        return dist, vals

    def test_trilinear_x_only(self):
        """Midpoint at x=2.5, y=3, z=4: expected = 4*100 + 3*10 + 2.5 = 432.5"""
        _, vals = self._get_profile_fine([2.0, 3.0, 4.0], [3.0, 3.0, 4.0])
        # 1 mm line, 0.5 mm step → 3 points: x = 2.0, 2.5, 3.0
        self.assertEqual(len(vals), 3)
        self.assertAlmostEqual(vals[1], 432.5)

    def test_trilinear_y_only(self):
        """Midpoint at x=2, y=3.5, z=4: expected = 4*100 + 3.5*10 + 2 = 437.0"""
        _, vals = self._get_profile_fine([2.0, 3.0, 4.0], [2.0, 4.0, 4.0])
        self.assertEqual(len(vals), 3)
        self.assertAlmostEqual(vals[1], 437.0)

    def test_trilinear_z_only(self):
        """Midpoint at x=2, y=3, z=4.5: expected = 4.5*100 + 3*10 + 2 = 482.0"""
        _, vals = self._get_profile_fine([2.0, 3.0, 4.0], [2.0, 3.0, 5.0])
        self.assertEqual(len(vals), 3)
        self.assertAlmostEqual(vals[1], 482.0)

    def test_trilinear_diagonal_midpoint(self):
        """Midpoint of (2,2,2)→(3,3,3) at (2.5,2.5,2.5): expected = (222+333)/2 = 277.5"""
        _, vals = self._get_profile_fine([2.0, 2.0, 2.0], [3.0, 3.0, 3.0])
        mid = len(vals) // 2
        self.assertAlmostEqual(vals[mid], 277.5)

    # ------------------------------------------------------------------
    # Distance values
    # ------------------------------------------------------------------

    def test_distance_starts_at_zero(self):
        dist, _ = self._get_profile([1.0, 1.0, 1.0], [4.0, 1.0, 1.0])
        self.assertAlmostEqual(dist[0], 0.0)

    def test_distance_ends_at_physical_length(self):
        """Last distance must equal the 3D Euclidean length of the segment."""
        pt1, pt2 = [1.0, 2.0, 3.0], [4.0, 6.0, 3.0]
        expected = float(np.linalg.norm(np.array(pt2) - np.array(pt1)))  # 5.0 mm
        dist, _ = self._get_profile(pt1, pt2)
        self.assertAlmostEqual(dist[-1], expected)

    def test_distances_monotonically_increasing(self):
        dist, _ = self._get_profile([1.0, 1.0, 1.0], [7.0, 5.0, 3.0])
        arr: np.ndarray = np.asarray(dist, dtype=float)
        diffs: np.ndarray = np.diff(arr)
        self.assertTrue(bool(np.all(diffs > 0.0)), "Distances are not strictly increasing")

    def test_distance_step_matches_spacing(self):
        """With 1 mm isotropic spacing, every step between samples must be 1 mm."""
        dist, _ = self._get_profile([2.0, 5.0, 5.0], [8.0, 5.0, 5.0])
        steps: np.ndarray = np.diff(np.asarray(dist, dtype=float))
        np.testing.assert_allclose(steps, np.ones_like(steps), rtol=1e-6)

    # ------------------------------------------------------------------
    # Sampling density
    # ------------------------------------------------------------------

    def test_fine_spacing_gives_more_samples(self):
        """0.5 mm spacing on a 6 mm line must give more points than 1 mm spacing."""
        _, vals_1mm = self._get_profile([2.0, 5.0, 5.0], [8.0, 5.0, 5.0])

        self.vol.spacing = np.array([0.5, 0.5, 0.5])
        _, vals_05mm = self._get_profile([2.0, 5.0, 5.0], [8.0, 5.0, 5.0])
        self.vol.spacing = np.array([1.0, 1.0, 1.0])

        self.assertGreater(len(vals_05mm), len(vals_1mm))

    def test_anisotropic_spacing_uses_minimum(self):
        """With spacing [1, 1, 0.5], step must be 0.5 (the minimum axis)."""
        self.vol.spacing = np.array([1.0, 1.0, 0.5])
        _, vals = self._get_profile([2.0, 5.0, 5.0], [8.0, 5.0, 5.0])
        self.vol.spacing = np.array([1.0, 1.0, 1.0])
        # step=0.5 → ceil(6/0.5)+1 = 13 points
        self.assertEqual(len(vals), 13)

    # ------------------------------------------------------------------
    # Boundary / in_bounds
    # ------------------------------------------------------------------

    def test_out_of_bounds_clamp_to_zero(self):
        dist, vals = self.pm.get_profile_data("v1", make_profile([-2.0, -2.0, -2.0], [1.0, 1.0, 1.0]))
        assert dist is not None and vals is not None
        self.assertEqual(vals[0], 0.0)
        self.assertGreater(vals[-1], 0.0)

    def test_in_bounds_flag_false_outside_volume(self):
        """Points with any coordinate < 0 or > shape−1 must have in_bounds=False."""
        export = self._get_export([-1.0, -1.0, -1.0], [1.0, 1.0, 1.0])
        pts = export["data"]
        self.assertFalse(pts[0]["in_bounds"])   # (−1,−1,−1) is outside
        self.assertTrue(pts[-1]["in_bounds"])   # (1,1,1) is inside

    def test_in_bounds_flag_true_when_fully_inside(self):
        export = self._get_export([2.0, 2.0, 2.0], [7.0, 7.0, 7.0])
        self.assertTrue(all(pt["in_bounds"] for pt in export["data"]))

    # ------------------------------------------------------------------
    # Export field correctness
    # ------------------------------------------------------------------

    def test_export_voxel_index_contains_ints(self):
        self.vol.spacing = np.array([0.5, 0.5, 0.5])
        export = self._get_export([2.0, 3.0, 4.0], [3.0, 3.0, 4.0])
        self.vol.spacing = np.array([1.0, 1.0, 1.0])
        for pt in export["data"]:
            for v in pt["point_voxel_index"]:
                self.assertIsInstance(v, int)

    def test_export_voxel_coord_fractional_at_midpoint(self):
        """The sub-voxel midpoint must appear in point_voxel_coord but not in point_voxel_index."""
        self.vol.spacing = np.array([0.5, 0.5, 0.5])
        export = self._get_export([2.0, 3.0, 4.0], [3.0, 3.0, 4.0])
        self.vol.spacing = np.array([1.0, 1.0, 1.0])
        mid = export["data"][1]  # x = 2.5
        self.assertAlmostEqual(mid["point_voxel_coord"][0], 2.5)
        self.assertNotEqual(mid["point_voxel_coord"][0], mid["point_voxel_index"][0])

    def test_export_phys_coords_lie_on_segment(self):
        """Every exported physical point must lie exactly on the line pt1→pt2."""
        pt1 = np.array([1.0, 2.0, 3.0])
        pt2 = np.array([7.0, 2.0, 3.0])
        export = self._get_export(pt1.tolist(), pt2.tolist())
        direction = pt2 - pt1
        for pt in export["data"]:
            phys = np.array(pt["point_phys_mm"])
            cross = np.cross(phys - pt1, direction)
            np.testing.assert_allclose(cross, 0.0, atol=1e-10)

    def test_export_distance_matches_phys_coords(self):
        """distance_mm must equal ‖point_phys_mm − pt1_phys‖ for every point."""
        pt1 = np.array([2.0, 3.0, 4.0])
        export = self._get_export(pt1.tolist(), [8.0, 3.0, 4.0])
        for pt in export["data"]:
            phys = np.array(pt["point_phys_mm"])
            self.assertAlmostEqual(pt["distance_mm"],
                                   float(np.linalg.norm(phys - pt1)), places=6)

    def test_export_structure(self):
        """Top-level keys and per-point keys must all be present."""
        export = self._get_export([1.0, 1.0, 1.0], [4.0, 1.0, 1.0], name="TestProfile")
        self.assertEqual(export["profile_name"], "TestProfile")
        self.assertEqual(export["image_name"], "TestVol")
        self.assertIn("coordinate_systems", export)
        self.assertGreaterEqual(len(export["data"]), 2)
        first = export["data"][0]
        for key in ("distance_mm", "intensity", "in_bounds",
                    "point_phys_mm", "point_voxel_coord",
                    "point_voxel_index", "point_display_voxel"):
            self.assertIn(key, first)

    # ------------------------------------------------------------------
    # 4D / DVF / RGB volumes
    # ------------------------------------------------------------------

    def test_4d_uses_correct_time_index(self):
        """With num_timepoints=3 and time_idx=2, must read from data[2, ...]."""
        t0 = np.zeros((10, 10, 10), dtype=np.float32)
        t1 = np.full((10, 10, 10), 50.0, dtype=np.float32)
        t2 = np.full((10, 10, 10), 99.0, dtype=np.float32)
        self.vol.data = np.stack([t0, t1, t2], axis=0)
        self.vol.num_timepoints = 3
        self.vs.camera.time_idx = 2

        _, vals = self._get_profile([2.0, 2.0, 2.0], [6.0, 2.0, 2.0])
        self.assertTrue(all(abs(v - 99.0) < 1e-5 for v in vals))

    def test_4d_clamps_time_index_to_last(self):
        """time_idx beyond num_timepoints must clamp to the last frame."""
        t0 = np.zeros((10, 10, 10), dtype=np.float32)
        t1 = np.full((10, 10, 10), 77.0, dtype=np.float32)
        self.vol.data = np.stack([t0, t1], axis=0)
        self.vol.num_timepoints = 2
        self.vs.camera.time_idx = 99

        _, vals = self._get_profile([2.0, 2.0, 2.0], [6.0, 2.0, 2.0])
        self.assertTrue(all(abs(v - 77.0) < 1e-5 for v in vals))

    def test_dvf_volume_returns_norm(self):
        """DVF voxels are 3-vectors; sampled value must be ‖v‖."""
        dvf = np.zeros((10, 10, 10, 3), dtype=np.float32)
        dvf[5, 5, 5] = [3.0, 4.0, 0.0]  # norm = 5.0
        self.vol.data = dvf
        self.vol.num_timepoints = 1
        self.vol.is_dvf = True

        _, vals = self._get_profile([5.0, 5.0, 5.0], [6.0, 5.0, 5.0])
        self.assertAlmostEqual(vals[0], 5.0, places=4)

    def test_rgb_volume_returns_mean(self):
        """RGB voxels are 3-channel; sampled value must be mean of channels."""
        rgb = np.zeros((10, 10, 10, 3), dtype=np.float32)
        rgb[5, 5, 5] = [10.0, 20.0, 30.0]  # mean = 20.0
        self.vol.data = rgb
        self.vol.num_timepoints = 1
        self.vol.is_rgb = True

        _, vals = self._get_profile([5.0, 5.0, 5.0], [6.0, 5.0, 5.0])
        self.assertAlmostEqual(vals[0], 20.0, places=4)

    # ------------------------------------------------------------------
    # Edge / degenerate cases
    # ------------------------------------------------------------------

    def test_zero_length_profile_returns_none(self):
        dist, vals = self.pm.get_profile_data("v1", make_profile([3.0, 3.0, 3.0], [3.0, 3.0, 3.0]))
        self.assertIsNone(dist)
        self.assertIsNone(vals)

    def test_none_endpoints_returns_none(self):
        p = ProfileLineState()
        p.pt1_phys = None
        p.pt2_phys = None
        dist, vals = self.pm.get_profile_data("v1", p)
        self.assertIsNone(dist)
        self.assertIsNone(vals)

    def test_missing_volume_returns_none(self):
        self.controller.volumes = {}
        dist, vals = self.pm.get_profile_data("v1", make_profile([1.0, 1.0, 1.0], [4.0, 1.0, 1.0]))
        self.assertIsNone(dist)
        self.assertIsNone(vals)


if __name__ == "__main__":
    unittest.main()
