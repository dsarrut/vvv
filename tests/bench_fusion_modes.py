#!/usr/bin/env python3
"""
VVV Fusion Modes Benchmark
==========================
Estimates rendering speed (FPS) for 4 viewers across 3 orientations (Axial, Sagittal, Coronal)
using large datasets: Base (512x512x1000), Overlay (256x256x800).
Screen size is assumed to be 2000x1300 total -> ~1000x650 per viewer.
Simulates CPU fallback behavior on OSX.
"""

import os
import sys
import time
import tempfile
import numpy as np
import SimpleITK as sitk
from unittest.mock import MagicMock

# 1. Mock DearPyGui to run completely headless
dpg_mock = MagicMock()
dpg_mock.does_item_exist.return_value = True
dpg_mock.get_item_width.return_value = 1000
dpg_mock.get_item_height.return_value = 650
sys.modules['dearpygui.dearpygui'] = dpg_mock

# 2. Path Setup
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

# 3. Force OSX Software Rendering Mode (Disable Hardware GL_NEAREST)
import vvv.ui.render_strategy as rs_mod
rs_mod.GL_NEAREST_SUPPORTED = False

from vvv.core.controller import Controller
from vvv.ui.viewer import SliceViewer
from vvv.utils import ViewMode


def execute_action(action, viewers):
    """Simulates the backend updates and triggers the render cycle for all 4 viewers."""
    if action == "Slicing":
        for v in viewers:
            v.slice_idx = min(v.slice_idx + 1, v.get_display_num_slices() - 1)
            v.is_geometry_dirty = True
            v.update_render(force_reblend=True)
    elif action == "Pan Move":
        for v in viewers:
            v.pan_offset[0] += 5.0
            v.is_geometry_dirty = True
            v.update_render(force_reblend=False)
    elif action == "Zoom In":
        for v in viewers:
            v.zoom *= 1.05
            v.is_geometry_dirty = True
            v.update_render(force_reblend=False)
    elif action == "Zoom Out":
        for v in viewers:
            v.zoom *= 0.95
            v.is_geometry_dirty = True
            v.update_render(force_reblend=False)


def main():
    print("Setting up large benchmark data (512x512x1000 base, 256x256x800 overlay)...")
    with tempfile.TemporaryDirectory() as tmpdir:
        base_path = os.path.join(tmpdir, "base.nii")
        ov_path = os.path.join(tmpdir, "ov.nii")
        
        # Generate Base (1000, 512, 512)
        base_data = np.empty((1000, 512, 512), dtype=np.float32)
        base_data[:] = np.linspace(0, 100, 512, dtype=np.float32)[None, None, :]
        base_img = sitk.GetImageFromArray(base_data)
        base_img.SetSpacing((1.0, 1.0, 1.0))
        sitk.WriteImage(base_img, base_path)
        
        # Generate Overlay (800, 256, 256)
        ov_data = np.empty((800, 256, 256), dtype=np.float32)
        ov_data[:] = np.linspace(0, 100, 256, dtype=np.float32)[None, None, :]
        ov_img = sitk.GetImageFromArray(ov_data)
        ov_img.SetSpacing((1.25, 2.0, 2.0))
        sitk.WriteImage(ov_img, ov_path)
        
        print("Loading files into VVV Controller...")
        c = Controller()
        c.gui = MagicMock()
        c.gui.ui_cfg = {"layout": {"viewport_padding": 4}}
        
        base_id = c.file.load_image(base_path)
        ov_id = c.file.load_image(ov_path)
        
        # Configure fusion
        vs_base = c.view_states[base_id]
        ov_vol = c.volumes[ov_id]
        vs_base.set_overlay(ov_id, ov_vol, c)
        vs_base.display.overlay_mode = "Alpha"
        vs_base.display.overlay_opacity = 0.5
        
        # Setup 4 Viewers
        viewers = []
        orientations = [ViewMode.AXIAL, ViewMode.SAGITTAL, ViewMode.CORONAL, ViewMode.AXIAL]
        for i in range(4):
            v = SliceViewer(f"V{i+1}", c)
            c.viewers[f"V{i+1}"] = v
            v.set_image(base_id)
            v.set_orientation(orientations[i])
            v.resize(1000, 650)
            v.zoom = 1.0
            viewers.append(v)
        
        # Benchmark Modes
        modes = [
            ("Linear", False, 1),
            ("Dual-Tex Native", True, 1),
            ("Dual-Tex Resampled", True, 2),
            ("Single-Tex Resampled", True, 3),
            ("Single-Tex Native", True, 4),
        ]
        
        actions = ["Slicing", "Pan Move", "Zoom In", "Zoom Out"]
        
        print("\nRunning OSX Software Rendering Benchmarks...")
        print(f"{'Mode':<22} | {'Slicing':>9} | {'Pan Move':>9} | {'Zoom In':>9} | {'Zoom Out':>9}")
        print("-" * 69)
        
        for mode_name, pix_zoom, nn_mode in modes:
            vs_base.display.pixelated_zoom = pix_zoom
            
            row = []
            for action in actions:
                # Reset viewer state cleanly before testing each action
                for v in viewers:
                    v.experimental_nn_mode = nn_mode
                    v.zoom = 1.0
                    v.pan_offset = [0.0, 0.0]
                    v.slice_idx = v.get_display_num_slices() // 2
                    v.is_geometry_dirty = True
                    v.update_render(force_reblend=True)
                
                # Warmup
                for _ in range(2):
                    execute_action(action, viewers)
                    
                # Measure exactly 10 full application frames
                n_iters = 10
                t0 = time.perf_counter()
                for _ in range(n_iters):
                    execute_action(action, viewers)
                t1 = time.perf_counter()
                
                fps = n_iters / (t1 - t0)
                row.append(fps)
            
            print(f"{mode_name:<22} | {row[0]:>5.1f} FPS | {row[1]:>5.1f} FPS | {row[2]:>5.1f} FPS | {row[3]:>5.1f} FPS")

if __name__ == "__main__":
    main()