#!/usr/bin/env python3
"""
VVV Fusion Modes Benchmark
==========================
Estimates rendering speed (FPS) for 4 viewers across 3 orientations (Axial, Sagittal, Coronal)
using large datasets: Base (512x512x1000), Overlay (256x256x800).
Screen size is assumed to be 2000x1300 total -> ~1000x650 per viewer.

On macOS: tests all SW CPU modes (HW GL_NEAREST unavailable due to Metal backend).
On Linux/Windows: also tests mode 0 (Hardware GL_NEAREST via raw OpenGL).

For each SW mode, two Pan/Zoom columns are shown:
  Pan (full NN) : full NN + overlay every frame — lazy_nn=False
  Pan (lazy)    : base NN only during interaction (overlay skipped), full NN+overlay after 150ms settle
The settle cost (one-shot full re-upload after stopping) equals "Pan (full NN)".
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

LAZY_SETTLE_S = 0.15  # seconds — must match viewer default


def execute_action(action, viewers):
    """Simulates the backend updates and triggers the render cycle for all 4 viewers."""
    if action == "Slicing":
        for v in viewers:
            v.slice_idx = min(v.slice_idx + 1, v.get_display_num_slices() - 1)
            v.is_geometry_dirty = True
            v.update_render(force_reblend=True)
    elif action in ("Pan Move", "Pan (lazy-live)"):
        # update_render(force_reblend=False) sets _last_move_time=now when lazy_nn=True,
        # which is exactly what we want for the "live drag" case.
        for v in viewers:
            v.pan_offset[0] += 5.0
            v.is_geometry_dirty = True
            v.update_render(force_reblend=False)
    elif action == "Pan (lazy-settle)":
        # Simulate tick()'s settle path: direct NN upload without triggering a new move.
        # _last_move_time=0 ensures time.time()-0 >> settle_ms so the lazy guard is skipped.
        for v in viewers:
            v._last_move_time = 0.0
            v._upload_base_texture()
            v._upload_overlay_texture()
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


def bench_mode(pix_zoom, nn_mode, actions, viewers, vs_base, n_iters, lazy=False):
    """Run all actions for one mode, return list of FPS values."""
    vs_base.display.pixelated_zoom = pix_zoom
    row = []
    for action in actions:
        for v in viewers:
            v.nn_mode = nn_mode
            v.lazy_nn = lazy
            v._nn_settle_done = True
            v._last_move_time = 0.0
            v.zoom = 1.0
            v.pan_offset = [0.0, 0.0]
            v.slice_idx = v.get_display_num_slices() // 2
            v.is_geometry_dirty = True
            v.update_render(force_reblend=True)

        for _ in range(3):  # warmup
            execute_action(action, viewers)

        t0 = time.perf_counter()
        for _ in range(n_iters):
            execute_action(action, viewers)
        t1 = time.perf_counter()
        row.append(n_iters / (t1 - t0))
    return row


def fmt_row(name, row, col_w=9):
    parts = [f"{fps:>{col_w-1}.1f} FPS" for fps in row]
    return f"{name:<28} | " + " | ".join(parts)


def main():
    parser = argparse.ArgumentParser(description="VVV Fusion Modes Benchmark")
    parser.add_argument("--save-csv", metavar="FILE", help="Save FPS results as CSV")
    parser.add_argument("--quick", action="store_true", help="Use 10 iterations instead of 50")
    args = parser.parse_args()

    n_iters = 10 if args.quick else 50

    print("Setting up large benchmark data (512x512x1000 base, 256x256x800 overlay)...")
    with tempfile.TemporaryDirectory() as tmpdir:
        base_path = os.path.join(tmpdir, "base.nii")
        ov_path   = os.path.join(tmpdir, "ov.nii")

        base_data = np.empty((1000, 512, 512), dtype=np.float32)
        base_data[:] = np.linspace(0, 100, 512, dtype=np.float32)[None, None, :]
        base_img = sitk.GetImageFromArray(base_data)
        base_img.SetSpacing((1.0, 1.0, 1.0))
        sitk.WriteImage(base_img, base_path)

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
        ov_id   = c.file.load_image(ov_path)

        vs_base = c.view_states[base_id]
        ov_vol  = c.volumes[ov_id]
        vs_base.set_overlay(ov_id, ov_vol, c)
        vs_base.display.overlay_mode    = "Alpha"
        vs_base.display.overlay_opacity = 0.5

        overlay_ready = vs_base.display.overlay_data is not None
        if not overlay_ready:
            print("WARNING: overlay resampling did not complete — overlay-dependent modes will show base-only cost")

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

        # (name, pix_zoom, nn_mode)
        # pix_zoom=False → Bilinear baseline: nn_mode irrelevant
        sw_modes = []
        if IS_LINUX_WINDOWS:
            sw_modes.append(("HW GL_NEAREST",       True,  NNMode.HW_GL_NEAREST))
        sw_modes += [
            ("Bilinear (no NN)",     False, NNMode.SW_DUAL_NATIVE),
            ("SW Dual-Tex Native",   True,  NNMode.SW_DUAL_NATIVE),
            ("SW Dual-Tex Resampled",True,  NNMode.SW_DUAL_RESAMPLED),
            ("SW Single-Tex Merged", True,  NNMode.SW_SINGLE_MERGED),
            ("SW Single-Tex Native", True,  NNMode.SW_SINGLE_NATIVE),
        ]

        # ── Section 1: full NN every frame ──────────────────────────────────
        actions_full = ["Slicing", "Pan Move", "Zoom In", "Zoom Out"]
        os_label = platform.system()
        sep = "-" * 78

        print(f"\n{'═'*78}")
        print(f"  {os_label}  ·  Full NN every frame (lazy_nn=False)  ·  {n_iters} iters/action")
        print(f"{'═'*78}")
        print(f"{'Mode':<28} | {'Slicing':>9} | {'Pan Move':>9} | {'Zoom In':>9} | {'Zoom Out':>9}")
        print(sep)

        full_results = []
        for mode_name, pix_zoom, nn_mode in sw_modes:
            row = bench_mode(pix_zoom, nn_mode, actions_full, viewers, vs_base, n_iters, lazy=False)
            print(fmt_row(mode_name, row))
            full_results.append((mode_name, "full", row))

        # ── Section 2: lazy NN  ──────────────────────────────────────────────
        # Bilinear (no NN) and HW GL_NEAREST are unaffected by lazy (no NN to defer)
        lazy_modes = [(n, pz, m) for (n, pz, m) in sw_modes
                      if pz and m != NNMode.HW_GL_NEAREST]

        actions_lazy = ["Slicing", "Pan (lazy-live)", "Pan (lazy-settle)"]
        hdr_lazy = f"{'Mode':<28} | {'Slicing':>9} | {'Pan(live)':>9} | {'Settle':>9}"
        note = ("  Pan(live)  = bilinear during drag  |  "
                "Settle = one NN upload after 150ms pause  (= Pan Move cost above)")

        print(f"\n{'═'*78}")
        print(f"  {os_label}  ·  Lazy NN (lazy_nn=True, settle={int(LAZY_SETTLE_S*1000)}ms)  ·  {n_iters} iters/action")
        print(f"{'═'*78}")
        print(hdr_lazy)
        print(sep)

        lazy_results = []
        for mode_name, pix_zoom, nn_mode in lazy_modes:
            row = bench_mode(pix_zoom, nn_mode, actions_lazy, viewers, vs_base, n_iters, lazy=True)
            print(fmt_row(mode_name, row))
            lazy_results.append((mode_name, "lazy", row))

        print(f"\n{note}")

        # ── CSV export ───────────────────────────────────────────────────────
        if args.save_csv:
            with open(args.save_csv, "w", newline="") as f:
                w = csv.writer(f)
                w.writerow(["mode", "strategy", "platform", "overlay_ready",
                             "Slicing", "Pan/Pan-live", "Zoom-In/Settle", "Zoom-Out"])
                for mode_name, strategy, row in full_results + lazy_results:
                    w.writerow([mode_name, strategy, os_label, overlay_ready]
                               + [f"{fps:.2f}" for fps in row])
            print(f"\nResults saved to {args.save_csv}")


if __name__ == "__main__":
    main()
