import os
import json
import unittest
import tempfile
import shutil
import numpy as np
import SimpleITK as sitk
import dearpygui.dearpygui as dpg

from vvv import vvv_screenshot

class TestScreenshot(unittest.TestCase):
    def setUp(self):
        try:
            dpg.destroy_context()
        except Exception:
            pass
        self.tmp_dir = tempfile.mkdtemp()

    def tearDown(self):
        try:
            dpg.destroy_context()
        except Exception:
            pass
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
