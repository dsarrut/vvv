import os
import tempfile
import unittest
import numpy as np
import SimpleITK as sitk

from vvv.maths.transform_io import TransformIO


class TestTransformIO(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmpdir.cleanup()

    def _create_sample_transform(self):
        t = sitk.Euler3DTransform()
        t.SetCenter((15.0, 25.0, 35.0))
        t.SetRotation(0.2, -0.3, 0.4)
        t.SetTranslation((10.0, -5.0, 8.0))
        return t

    def test_roundtrip_tfm(self):
        orig = self._create_sample_transform()
        filepath = os.path.join(self.tmpdir.name, "sample.tfm")

        TransformIO.write_transform(orig, filepath)
        loaded = TransformIO.read_transform(filepath, fallback_center=orig.GetCenter())

        pts = [
            (9.2, 3.3, -1.7),
            (0.0, 0.0, 0.0),
            (15.0, 25.0, 35.0),
            (-10.5, 42.0, 100.1),
        ]
        for p in pts:
            np.testing.assert_allclose(
                orig.TransformPoint(p),
                loaded.TransformPoint(p),
                atol=1e-4,
                err_msg=f"Point {p} failed roundtrip for .tfm",
            )

    def test_roundtrip_mat(self):
        orig = self._create_sample_transform()
        filepath = os.path.join(self.tmpdir.name, "sample.mat")

        TransformIO.write_transform(orig, filepath)
        loaded = TransformIO.read_transform(filepath, fallback_center=orig.GetCenter())

        pts = [
            (9.2, 3.3, -1.7),
            (0.0, 0.0, 0.0),
            (15.0, 25.0, 35.0),
            (-10.5, 42.0, 100.1),
        ]
        for p in pts:
            np.testing.assert_allclose(
                orig.TransformPoint(p),
                loaded.TransformPoint(p),
                atol=1e-4,
                err_msg=f"Point {p} failed roundtrip for .mat (PA6)",
            )

    def test_roundtrip_txt(self):
        orig = self._create_sample_transform()
        filepath = os.path.join(self.tmpdir.name, "sample.txt")

        TransformIO.write_transform(orig, filepath)
        loaded = TransformIO.read_transform(filepath, fallback_center=orig.GetCenter())

        pts = [
            (9.2, 3.3, -1.7),
            (0.0, 0.0, 0.0),
            (15.0, 25.0, 35.0),
            (-10.5, 42.0, 100.1),
        ]
        for p in pts:
            np.testing.assert_allclose(
                orig.TransformPoint(p),
                loaded.TransformPoint(p),
                atol=1e-4,
                err_msg=f"Point {p} failed roundtrip for .txt (PA6)",
            )

    def test_coherence_between_formats(self):
        """Verify that .tfm, .mat, and .txt files written from the same transform
        load into identical spatial transformations (PA6).
        """
        orig = self._create_sample_transform()
        tfm_path = os.path.join(self.tmpdir.name, "t.tfm")
        mat_path = os.path.join(self.tmpdir.name, "t.mat")
        txt_path = os.path.join(self.tmpdir.name, "t.txt")

        TransformIO.write_transform(orig, tfm_path)
        TransformIO.write_transform(orig, mat_path)
        TransformIO.write_transform(orig, txt_path)

        tfm_loaded = TransformIO.read_transform(tfm_path, fallback_center=orig.GetCenter())
        mat_loaded = TransformIO.read_transform(mat_path, fallback_center=orig.GetCenter())
        txt_loaded = TransformIO.read_transform(txt_path, fallback_center=orig.GetCenter())

        test_points = [
            (9.2, 3.3, -1.7),
            (-20.0, 10.0, 50.0),
            (100.0, -50.0, 0.0),
        ]
        for p in test_points:
            p_tfm = tfm_loaded.TransformPoint(p)
            p_mat = mat_loaded.TransformPoint(p)
            p_txt = txt_loaded.TransformPoint(p)

            np.testing.assert_allclose(p_tfm, p_mat, atol=1e-4)
            np.testing.assert_allclose(p_tfm, p_txt, atol=1e-4)

    def test_read_legacy_4x3_and_3x3(self):
        """Test reading 12-element (4x3) and 9-element (3x3) matrices from text files."""
        # 12-element format: 9 rotation + 3 offset
        txt12 = os.path.join(self.tmpdir.name, "legacy12.txt")
        with open(txt12, "w") as f:
            f.write("1.0 0.0 0.0\n0.0 1.0 0.0\n0.0 0.0 1.0\n10.0 20.0 30.0\n")

        t12 = TransformIO.read_transform(txt12)
        # Disk offset is (10, 20, 30); inverse to VVV space maps (0,0,0) -> (-10, -20, -30)
        p12 = t12.TransformPoint((0.0, 0.0, 0.0))
        np.testing.assert_allclose(p12, [-10.0, -20.0, -30.0], atol=1e-4)

        # 9-element format: 3x3 rotation only
        txt9 = os.path.join(self.tmpdir.name, "rot9.txt")
        with open(txt9, "w") as f:
            f.write("0.0 -1.0 0.0\n1.0 0.0 0.0\n0.0 0.0 1.0\n")

        t9 = TransformIO.read_transform(txt9)
        # Disk rotates +90 deg around Z. Inverse (VVV) rotates -90 deg around Z.
        # (1, 0, 0) -> (0, -1, 0)
        p9 = t9.TransformPoint((1.0, 0.0, 0.0))
        np.testing.assert_allclose(p9, [0.0, -1.0, 0.0], atol=1e-4)

    def test_read_elastix_parameter_file(self):
        """Test parsing Elastix parameter file format."""
        elastix_path = os.path.join(self.tmpdir.name, "TransformParameters.0.txt")
        content = """
(Transform "EulerTransform")
(NumberOfParameters 6)
(TransformParameters 0.0 0.0 0.0 10.0 20.0 30.0)
(CenterOfRotationPoint 15.0 25.0 35.0)
"""
        with open(elastix_path, "w") as f:
            f.write(content)

        t = TransformIO.read_transform(elastix_path)
        # Elastix translation is (10, 20, 30) (Fixed -> Moving)
        # Inverse to VVV forward space (Moving -> Fixed) should shift by (-10, -20, -30)
        p = t.TransformPoint((15.0, 25.0, 35.0))
        np.testing.assert_allclose(p, [5.0, 5.0, 5.0], atol=1e-4)


if __name__ == "__main__":
    unittest.main()

