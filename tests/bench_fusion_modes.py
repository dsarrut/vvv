#!/usr/bin/env python3
"""
VVV Fusion Modes Benchmark
==========================
Estimates rendering speed (FPS) for 4 viewers across 3 orientations (Axial, Sagittal, Coronal)
using large datasets: Base (512x512x1000), Overlay (256x256x800).
Screen size is assumed to be 2000x1300 total -> ~1000x650 per viewer.

On macOS: tests all SW CPU modes (HW GL_NEAREST unavailable due to Metal backend).
On Linux/Windows: also tests mode 0 (Hardware GL_NEAREST via raw OpenGL).
"""

import argparse
import csv
import os
import platform
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
dpg_mock.set_value.return_value = None
dpg_mock.configure_item.return_value = None
dpg_mock.get_item_state.return_value = {"visible": True}
sys.modules['dearpygui.dearpygui'] = dpg_mock

# 2. Path Setup
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

# 3. Import render_strategy BEFORE deciding whether to override GL support
import vvv.ui.render_strategy as rs_mod
from vvv.ui.render_strategy import NNMode

IS_LINUX_WINDOWS = platform.system() in ("Linux", "Windows")

if not IS_LINUX_WINDOWS:
    # macOS uses Metal — raw GL calls crash with no context, force SW rendering
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
    parser = argparse.ArgumentParser(description="VVV Fusion Modes Benchmark")
    parser.add_argument("--save-csv", metavar="FILE", help="Save FPS results as CSV")
    parser.add_argument("--quick", action="store_true", help="Use 10 iterations instead of 50")
    args = parser.parse_args()

    n_iters = 10 if args.quick else 50

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

        # Configure fusion — set_overlay calls update_overlay_display_data synchronously
        vs_base = c.view_states[base_id]
        ov_vol = c.volumes[ov_id]
        vs_base.set_overlay(ov_id, ov_vol, c)
        vs_base.display.overlay_mode = "Alpha"
        vs_base.display.overlay_opacity = 0.5

        overlay_ready = vs_base.display.overlay_data is not None
        if not overlay_ready:
            print("WARNING: overlay resampling did not complete — overlay-dependent modes will show base-only cost")

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
        # pix_zoom=False means no NN processing (bilinear GPU upscaling); nn_mode is irrelevant.
        # On Linux/Windows mode 0 (HW_GL_NEAREST) is listed first as the hardware baseline.
        modes = []
        if IS_LINUX_WINDOWS:
            modes.append(("HW GL_NEAREST",        True,  NNMode.HW_GL_NEAREST))
        modes += [
            ("Bilinear (no NN)",       False, NNMode.SW_DUAL_NATIVE),   # pix_zoom=False; nn_mode irrelevant
            ("SW Dual-Tex Native",     True,  NNMode.SW_DUAL_NATIVE),
            ("SW Dual-Tex Resampled",  True,  NNMode.SW_DUAL_RESAMPLED),
            ("SW Single-Tex Merged",   True,  NNMode.SW_SINGLE_MERGED),
            ("SW Single-Tex Native",   True,  NNMode.SW_SINGLE_NATIVE),
        ]

        actions = ["Slicing", "Pan Move", "Zoom In", "Zoom Out"]

        os_label = platform.system()
        print(f"\nRunning {os_label} Rendering Benchmarks ({n_iters} iterations per action)...")
        print(f"Overlay data: {'ready' if overlay_ready else 'NOT ready (base-only cost)'}")
        print(f"{'Mode':<26} | {'Slicing':>9} | {'Pan Move':>9} | {'Zoom In':>9} | {'Zoom Out':>9}")
        print("-" * 73)

        results = []

        for mode_name, pix_zoom, nn_mode in modes:
            vs_base.display.pixelated_zoom = pix_zoom

            row = []
            for action in actions:
                # Reset viewer state cleanly before testing each action
                for v in viewers:
                    v.nn_mode = nn_mode
                    v.zoom = 1.0
                    v.pan_offset = [0.0, 0.0]
                    v.slice_idx = v.get_display_num_slices() // 2
                    v.is_geometry_dirty = True
                    v.update_render(force_reblend=True)

                # Warmup
                for _ in range(3):
                    execute_action(action, viewers)

                # Measure
                t0 = time.perf_counter()
                for _ in range(n_iters):
                    execute_action(action, viewers)
                t1 = time.perf_counter()

                fps = n_iters / (t1 - t0)
                row.append(fps)

            print(f"{mode_name:<26} | {row[0]:>5.1f} FPS | {row[1]:>5.1f} FPS | {row[2]:>5.1f} FPS | {row[3]:>5.1f} FPS")
            results.append((mode_name, row))

        if args.save_csv:
            with open(args.save_csv, "w", newline="") as f:
                w = csv.writer(f)
                w.writerow(["mode", "platform", "overlay_ready"] + actions)
                for mode_name, row in results:
                    w.writerow([mode_name, os_label, overlay_ready] + [f"{fps:.2f}" for fps in row])
            print(f"\nResults saved to {args.save_csv}")

        print()
        print("Note: Pan/Zoom actions skip re-blending (force_reblend=False), so they measure")
        print("only the NN upscaling cost. Base NN (1000x650 canvas) dominates all SW modes —")
        print("overlay-mode differences show more clearly during Slicing (force_reblend=True).")


if __name__ == "__main__":
    main()
