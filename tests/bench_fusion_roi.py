#!/usr/bin/env python3
"""
VVV Fusion + ROI Benchmark
===========================
Benchmarks rendering performance (FPS) across 4 viewers (Axial, Sagittal, Coronal, Axial)
for Bilinear rendering comparing:
  1. Base Image only
  2. Base + Fusion Overlay
  3. Base + Fusion Overlay + Spheroid ROI (roi_above_overlay=True)
  4. Base + Fusion Overlay + 5 Spheroid ROIs (roi_above_overlay=True)

Usage:
  python3 tests/bench_fusion_roi.py [--quick] [--very-quick] [--save-csv FILE]
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
dpg_mock.get_drawing_mouse_pos.return_value = [500, 325]
sys.modules['dearpygui.dearpygui'] = dpg_mock

# 2. Path Setup
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

import vvv.ui.render_strategy as rs_mod
rs_mod.GL_NEAREST_SUPPORTED = False

from vvv.core.controller import Controller
from vvv.ui.viewer import SliceViewer
from vvv.utils import ViewMode
from vvv.core.roi_manager import ROIState


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
    elif action == "W/L (Base)":
        for v in viewers:
            if v.mouse_phys_coord is None:
                v.update_crosshair_data(v.quad_w / 2, v.quad_h / 2)
            v.apply_local_auto_window(target="base")
            v.update_render(force_reblend=True)


def bench_config(actions, viewers, n_iters, n_warmup=3):
    """Run all actions for the current setup and return FPS list."""
    row = []
    for action in actions:
        for v in viewers:
            v.zoom = 1.0
            v.pan_offset = [0.0, 0.0]
            v.slice_idx = v.get_display_num_slices() // 2
            v.is_geometry_dirty = True
            v.update_render(force_reblend=True)

        for _ in range(n_warmup):
            execute_action(action, viewers)

        t0 = time.perf_counter()
        for _ in range(n_iters):
            execute_action(action, viewers)
        t1 = time.perf_counter()
        row.append(n_iters / (t1 - t0))
    return row


def fmt_row(name, row, col_w=10):
    parts = [f"{fps:>{col_w-1}.1f} FPS" for fps in row]
    return f"{name:<36} | " + " | ".join(parts)


def main():
    parser = argparse.ArgumentParser(description="VVV Fusion + ROI Benchmark")
    parser.add_argument("--save-csv", metavar="FILE", help="Save FPS results as CSV")
    parser.add_argument("--quick", action="store_true", help="Use 10 iterations instead of 50")
    parser.add_argument("--very-quick", action="store_true", help="Use 2 iterations and tiny volumes for CI tests")
    args = parser.parse_args()

    if args.very_quick:
        n_iters = 2
        n_warmup = 1
        v_shape = (10, 64, 64)
        o_shape = (10, 32, 32)
    elif args.quick:
        n_iters = 10
        n_warmup = 3
        v_shape = (1000, 512, 512)
        o_shape = (800, 256, 256)
    else:
        n_iters = 50
        n_warmup = 3
        v_shape = (1000, 512, 512)
        o_shape = (800, 256, 256)

    print(f"Setting up benchmark data ({v_shape[2]}x{v_shape[1]}x{v_shape[0]} base, {o_shape[2]}x{o_shape[1]}x{o_shape[0]} overlay)...")
    with tempfile.TemporaryDirectory() as tmpdir:
        base_path = os.path.join(tmpdir, "base.nii")
        ov_path   = os.path.join(tmpdir, "ov.nii")

        base_data = np.empty(v_shape, dtype=np.float32)
        base_data[:] = np.linspace(0, 100, v_shape[2], dtype=np.float32)[None, None, :]
        base_img = sitk.GetImageFromArray(base_data)
        base_img.SetSpacing((1.0, 1.0, 1.0))
        sitk.WriteImage(base_img, base_path)

        ov_data = np.empty(o_shape, dtype=np.float32)
        ov_data[:] = np.linspace(0, 100, o_shape[2], dtype=np.float32)[None, None, :]
        ov_img = sitk.GetImageFromArray(ov_data)
        ov_img.SetSpacing((1.25, 2.0, 2.0))
        sitk.WriteImage(ov_img, ov_path)

        print("Loading files into VVV Controller...")
        c = Controller()
        c.gui = MagicMock()
        c.gui.ui_cfg = {"layout": {"viewport_padding": 4}}

        base_id = c.file.load_image(base_path)
        ov_id   = c.file.load_image(ov_path)

        vs_base = c.view_states[base_id]
        ov_vol  = c.volumes[ov_id]

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

        actions = ["Slicing", "Pan Move", "Zoom In", "W/L (Base)"]
        os_label = platform.system()
        sep = "-" * 88

        print(f"\n{'═'*88}")
        print(f"  {os_label}  ·  Fusion + ROI Benchmark (Bilinear mode)  ·  {n_iters} iters/action")
        print(f"{'═'*88}")
        print(f"{'Configuration':<36} | {'Slicing':>10} | {'Pan Move':>10} | {'Zoom In':>10} | {'W/L (Base)':>10}")
        print(sep)

        results = []

        # 1. Base Image Only
        vs_base.display.pixelated_zoom = False
        vs_base.display.overlay.image_id = None
        row = bench_config(actions, viewers, n_iters, n_warmup=n_warmup)
        name = "1. Base Image Only"
        print(fmt_row(name, row))
        results.append((name, row))

        # 2. Base + 10 ROIs Only (No Fusion)
        vs_base.display.overlay.image_id = None
        vs_base.rois = {}
        for i in range(1, 11):
            roi_item = ROIState(
                volume_id=f"roi_{i}",
                name=f"Tumor_{i}",
                color=[0, 255, 0, 180],
            )
            roi_item.is_spheroid = True
            roi_item.center_phys = [150.0 + i * 25.0, 150.0 + i * 25.0, 400.0 + i * 25.0]
            roi_item.r_x_mm = 25.0
            roi_item.r_y_mm = 25.0
            roi_item.r_z_mm = 25.0
            vs_base.rois[f"roi_{i}"] = roi_item
        row = bench_config(actions, viewers, n_iters, n_warmup=n_warmup)
        name = "2. Base + 10 ROIs Only (No Fusion)"
        print(fmt_row(name, row))
        results.append((name, row))

        # 3. Base + Fusion Overlay (No ROIs)
        vs_base.rois = {}
        vs_base.set_overlay(ov_id, ov_vol)
        c._apply_overlay_resample(vs_base, c.view_states[ov_id])
        vs_base.display.overlay_mode = "Alpha"
        vs_base.display.overlay_opacity = 0.5
        vs_base.display.min_threshold = None
        row = bench_config(actions, viewers, n_iters, n_warmup=n_warmup)
        name = "3. Base + Fusion Overlay"
        print(fmt_row(name, row))
        results.append((name, row))

        # 4. Base + Fusion Overlay with min_threshold (50% pixels filtered)
        ov_vs = c.view_states[ov_id]
        ov_vs.display.min_threshold = 50.0
        row = bench_config(actions, viewers, n_iters, n_warmup=n_warmup)
        name = "4. Base + Fusion + min_thresh=50"
        print(fmt_row(name, row))
        results.append((name, row))
        ov_vs.display.min_threshold = None

        # 5. Base + Fusion Overlay + 5 Spheroid ROIs (roi_above_overlay=True)
        vs_base.display.roi_above_overlay = True
        for i in range(1, 6):
            roi_item = ROIState(
                volume_id=f"roi_{i}",
                name=f"Tumor_{i}",
                color=[0, 255, 0, 180],
            )
            roi_item.is_spheroid = True
            roi_item.center_phys = [200.0 + i * 20.0, 200.0 + i * 20.0, 450.0 + i * 20.0]
            roi_item.r_x_mm = 30.0
            roi_item.r_y_mm = 30.0
            roi_item.r_z_mm = 30.0
            vs_base.rois[f"roi_{i}"] = roi_item
        row = bench_config(actions, viewers, n_iters, n_warmup=n_warmup)
        name = "5. Base + Fusion + 5 ROIs (Above)"
        print(fmt_row(name, row))
        results.append((name, row))

        if args.save_csv:
            with open(args.save_csv, "w", newline="") as f:
                w = csv.writer(f)
                w.writerow(["configuration", "platform", "Slicing", "Pan Move", "Zoom In", "W/L_Base"])
                for config_name, row in results:
                    w.writerow([config_name, os_label] + [f"{fps:.2f}" for fps in row])
            print(f"\nResults saved to {args.save_csv}")


if __name__ == "__main__":
    main()
