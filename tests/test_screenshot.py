import os
import json
import unittest
import tempfile
import shutil
import numpy as np
import SimpleITK as sitk
import dearpygui.dearpygui as dpg
from PIL import Image

from vvv import vvv_screenshot

class TestScreenshot(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp_dir)

    def test_screenshot_generation(self):
        print("Creating synthetic image for testing...")
        # Create a 3D volume with a sphere
        data = np.zeros((30, 40, 50), dtype=np.float32)
        z, y, x = np.ogrid[:30, :40, :50]
        mask = (z - 15)**2 + (y - 20)**2 + (x - 25)**2 <= 8**2
        data[mask] = 100.0
        
        img = sitk.GetImageFromArray(data)
        img.SetSpacing((1.0, 1.0, 1.0))
        img.SetOrigin((0.0, 0.0, 0.0))
        
        img_path = os.path.join(self.tmp_dir, "temp_synthetic.nii.gz")
        sitk.WriteImage(img, img_path)
        
        # Workspace
        ws_data = {
            "images": {
                "img_1": {
                    "path": os.path.abspath(img_path),
                    "is_overlay_only": False,
                    "display": {
                        "colormap": "Grayscale",
                        "window_width": 150.0,
                        "window_level": 50.0
                    }
                }
            },
            "viewers": {
                "V1": {"image_id": "img_1", "orientation": "AXIAL"},
                "V2": {"image_id": "img_1", "orientation": "CORONAL"},
                "V3": {"image_id": "img_1", "orientation": "SAGITTAL"}
            }
        }
        vvw_path = os.path.join(self.tmp_dir, "temp_workspace.vvw")
        with open(vvw_path, "w") as f:
            json.dump(ws_data, f, indent=2)

        # Screenshot config — one entry per orientation
        axial_out = os.path.join(self.tmp_dir, "shot_axial.png")
        coronal_out = os.path.join(self.tmp_dir, "shot_coronal.png")
        sagittal_out = os.path.join(self.tmp_dir, "shot_sagittal.png")

        sc_data = {
            "defaults": {
                "position_mm": [25.0, 20.0, 15.0],
                "image_id": "img_1"
            },
            "screenshots": [
                {"orientation": "XY", "output": axial_out},
                {"orientation": "XZ", "output": coronal_out},
                {"orientation": "YZ", "output": sagittal_out}
            ]
        }
        sc_path = os.path.join(self.tmp_dir, "temp_sc.json")
        with open(sc_path, "w") as f:
            json.dump(sc_data, f, indent=2)

        print("Running vvv_screenshot...")
        vvv_screenshot(vvw_path, sc_path)
        print("Screenshot function finished.")

        for f in [axial_out, coronal_out, sagittal_out]:
            self.assertTrue(os.path.exists(f), f"Missing: {f}")
            self.assertTrue(os.path.getsize(f) > 0, f"Empty: {f}")

    def test_screenshot_orientation_missing_from_workspace_layout(self):
        """Regression: a workspace whose saved viewport layout has no viewer at the
        requested orientation must still produce that screenshot by repurposing an
        existing viewer showing the same image, instead of silently skipping it
        with 'Warning: No viewer with orientation ...'."""
        data = np.zeros((30, 40, 50), dtype=np.float32)
        z, y, x = np.ogrid[:30, :40, :50]
        mask = (z - 15) ** 2 + (y - 20) ** 2 + (x - 25) ** 2 <= 8 ** 2
        data[mask] = 100.0

        img = sitk.GetImageFromArray(data)
        img.SetSpacing((1.0, 1.0, 1.0))
        img.SetOrigin((0.0, 0.0, 0.0))

        img_path = os.path.join(self.tmp_dir, "temp_synthetic2.nii.gz")
        sitk.WriteImage(img, img_path)

        # Only Coronal and Sagittal viewers — no viewer is set to Axial at all.
        ws_data = {
            "images": {
                "img_1": {
                    "path": os.path.abspath(img_path),
                    "is_overlay_only": False,
                    "display": {
                        "colormap": "Grayscale",
                        "window_width": 150.0,
                        "window_level": 50.0
                    }
                }
            },
            "viewers": {
                "V1": {"image_id": "img_1", "orientation": "CORONAL"},
                "V2": {"image_id": "img_1", "orientation": "SAGITTAL"}
            }
        }
        vvw_path = os.path.join(self.tmp_dir, "temp_workspace_no_axial.vvw")
        with open(vvw_path, "w") as f:
            json.dump(ws_data, f, indent=2)

        axial_out = os.path.join(self.tmp_dir, "shot_axial_repurposed.png")
        sc_data = {
            "defaults": {"position_mm": [25.0, 20.0, 15.0], "image_id": "img_1"},
            "screenshots": [{"orientation": "XY", "output": axial_out}],
        }
        sc_path = os.path.join(self.tmp_dir, "temp_sc_no_axial.json")
        with open(sc_path, "w") as f:
            json.dump(sc_data, f, indent=2)

        vvv_screenshot(vvw_path, sc_path)

        self.assertTrue(os.path.exists(axial_out), f"Missing: {axial_out}")
        self.assertTrue(os.path.getsize(axial_out) > 0, f"Empty: {axial_out}")

    def test_screenshot_image_not_assigned_to_any_viewer(self):
        """Regression: a workspace where the target image is loaded but was never
        assigned to any of the 4 viewport slots at all (e.g. only used as an
        overlay elsewhere, or simply not shown in the saved layout — as in a real
        multi-image workspace where some loaded images have no viewer of their
        own) must still produce a screenshot, by assigning the image directly to
        a viewer rather than requiring it to already be on-screen somewhere."""
        data = np.zeros((30, 40, 50), dtype=np.float32)
        z, y, x = np.ogrid[:30, :40, :50]
        mask = (z - 15) ** 2 + (y - 20) ** 2 + (x - 25) ** 2 <= 8 ** 2
        data[mask] = 100.0

        img = sitk.GetImageFromArray(data)
        img.SetSpacing((1.0, 1.0, 1.0))
        img.SetOrigin((0.0, 0.0, 0.0))

        img_path = os.path.join(self.tmp_dir, "temp_synthetic3.nii.gz")
        sitk.WriteImage(img, img_path)

        # No "viewers" section at all — the image is loaded but on-screen nowhere.
        ws_data = {
            "images": {
                "img_1": {
                    "path": os.path.abspath(img_path),
                    "is_overlay_only": False,
                    "display": {
                        "colormap": "Grayscale",
                        "window_width": 150.0,
                        "window_level": 50.0
                    }
                }
            },
            "viewers": {}
        }
        vvw_path = os.path.join(self.tmp_dir, "temp_workspace_no_viewer.vvw")
        with open(vvw_path, "w") as f:
            json.dump(ws_data, f, indent=2)

        axial_out = os.path.join(self.tmp_dir, "shot_axial_unassigned.png")
        sc_data = {
            "defaults": {"position_mm": [25.0, 20.0, 15.0]},
            "screenshots": [{"orientation": "XY", "output": axial_out}],
        }
        sc_path = os.path.join(self.tmp_dir, "temp_sc_no_viewer.json")
        with open(sc_path, "w") as f:
            json.dump(sc_data, f, indent=2)

        vvv_screenshot(vvw_path, sc_path)

        self.assertTrue(os.path.exists(axial_out), f"Missing: {axial_out}")
        self.assertTrue(os.path.getsize(axial_out) > 0, f"Empty: {axial_out}")


def _write(path, data, spacing=(1.0, 1.0, 1.0)):
    img = sitk.GetImageFromArray(data.astype(np.float32))
    img.SetSpacing(spacing)
    sitk.WriteImage(img, path)
    return os.path.abspath(path)


class TestScreenshotF1(unittest.TestCase):
    """F1: --screenshots: images named three ways, defaults from the
    workspace, contours in the PNG, failures counted."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def _p(self, name):
        return os.path.join(self.tmp, name)

    def _run(self, ws, shots):
        with open(self._p("ws.vvw"), "w") as f:
            json.dump(ws, f)
        with open(self._p("shots.json"), "w") as f:
            json.dump({"screenshots": shots}, f)
        return vvv_screenshot(self._p("ws.vvw"), self._p("shots.json"))

    def test_image_named_by_number_file_name_or_workspace_id(self):
        dark = np.zeros((10, 20, 20))
        bright = np.full((10, 20, 20), 100.0)
        a = _write(self._p("a.nii.gz"), dark)
        b = _write(self._p("b.nii.gz"), bright)
        disp = {"ww": 100.0, "wl": 50.0}
        ws = {
            "images": {
                "img_a": {"path": a, "display": dict(disp)},
                "img_b": {"path": b, "display": dict(disp)},
            },
            "viewers": {"V1": {"image_id": "img_a", "orientation": "AXIAL"}},
        }
        pos = [10.0, 10.0, 5.0]
        failures = self._run(ws, [
            {"output": self._p("by_number.png"), "image": 2, "position_mm": pos, "orientation": "XY"},
            {"output": self._p("by_name.png"), "image": "b.nii.gz", "position_mm": pos, "orientation": "XY"},
            {"output": self._p("by_ws_id.png"), "image": "img_b", "position_mm": pos, "orientation": "XY"},
            {"output": self._p("first.png"), "image": "img_a", "position_mm": pos, "orientation": "XY"},
            {"output": self._p("unknown.png"), "image": "nope.nii.gz", "position_mm": pos},
        ])
        self.assertEqual(failures, 1)
        self.assertFalse(os.path.exists(self._p("unknown.png")))
        means = {
            n: np.asarray(Image.open(self._p(n + ".png")).convert("L")).mean()
            for n in ("by_number", "by_name", "by_ws_id", "first")
        }
        for n in ("by_number", "by_name", "by_ws_id"):
            self.assertGreater(means[n], 200, n)  # the bright image
        self.assertLess(means["first"], 50)

    def test_defaults_from_the_workspace_view(self):
        a = _write(self._p("a.nii.gz"), np.zeros((10, 20, 30)))
        ws = {
            "images": {"img_a": {"path": a}},
            "viewers": {"V1": {"image_id": "img_a", "orientation": "SAGITTAL"}},
        }
        self.assertEqual(self._run(ws, [{"output": self._p("default.png")}]), 0)
        # the sagittal slice of a 30 x 20 x 10 (x, y, z) volume: 20 wide, 10 high
        self.assertEqual(Image.open(self._p("default.png")).size, (20, 10))

    def test_contours_are_drawn_in_the_png(self):
        base = _write(self._p("ct.nii.gz"), np.zeros((10, 40, 40)))
        lab = np.zeros((10, 40, 40))
        lab[2:8, 10:30, 10:30] = 1
        lab_path = _write(self._p("labels.nii.gz"), lab)
        ws = {
            "images": {
                "img_a": {
                    "path": base,
                    "label_maps": [{
                        "path": lab_path,
                        "labels": {"1": {
                            "name": "box", "color": [0, 255, 0], "is_contour": True,
                            "visible": True, "thickness": 2.0, "opacity": 0.5,
                        }},
                    }],
                }
            },
            "viewers": {"V1": {"image_id": "img_a", "orientation": "AXIAL"}},
        }
        shot = {"output": self._p("contour.png"), "position_mm": [20.0, 20.0, 5.0], "orientation": "XY"}
        self.assertEqual(self._run(ws, [shot]), 0)
        rgb = np.asarray(Image.open(self._p("contour.png")).convert("RGB")).astype(int)
        green = (rgb[..., 1] > 200) & (rgb[..., 0] < 60) & (rgb[..., 2] < 60)
        self.assertGreater(green.sum(), 20)  # the contour line
        self.assertFalse(green[20, 20])  # not filled: the inside stays black


class TestScreenshotCli(unittest.TestCase):
    def test_run_screenshots_needs_one_workspace(self):
        from vvv.cli import run_screenshots

        tmp = tempfile.mkdtemp()
        try:
            shots = os.path.join(tmp, "shots.json")
            with open(shots, "w") as f:
                f.write("{}")
            self.assertEqual(run_screenshots([], [], shots), 2)
            self.assertEqual(run_screenshots(["a.vvw", "b.vvw"], [], shots), 2)
            self.assertEqual(run_screenshots([os.path.join(tmp, "missing.vvw")], [], shots), 2)
            ws = os.path.join(tmp, "ws.vvw")
            with open(ws, "w") as f:
                f.write("{}")
            self.assertEqual(run_screenshots([ws], [], shots), 2)  # no 'screenshots' list
        finally:
            shutil.rmtree(tmp)
