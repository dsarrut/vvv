#!/usr/bin/env python3
"""
VVV Fusion + Large ROI Benchmark
=================================
Targets the specific scenario that turned out to be slow on macOS: a large
base image, a large fusion overlay, AND a large ROI displayed on top —
across Slicing, Pan, Zoom, and W/L actions.

Unlike bench_fusion_modes.py (no ROIs) and bench_rendering.py (no ROIs, no
registration transform), this exercises the two caches added to
compute_native_voxel_overlay: the transform/geometry cache and the ROI mask
buffer cache. Both are keyed to survive Pan/Zoom/W-L (nothing they depend on
changes) but correctly invalidate every iteration during Slicing (a new ROI
slice + a new base slice are extracted each time) — so this benchmark should
show Slicing as visibly more expensive than Pan/Zoom/W-L, which is exactly
what live VVV_PROFILE data showed in the app.

Compares "fusion only" vs "fusion + large ROI" for the same NN mode, so the
ROI-specific cost is directly visible as a delta, not just an absolute number.
"""

import argparse
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
    elif action == "W/L (W)":
        for v in viewers:
            if v.mouse_phys_coord is None:
                v.update_crosshair_data(v.quad_w / 2, v.quad_h / 2)
            v.apply_local_auto_window(target="base")
            v.update_render(force_reblend=True)
    elif action == "W/L (X)":
        for v in viewers:
            if v.mouse_phys_coord is None:
                v.update_crosshair_data(v.quad_w / 2, v.quad_h / 2)
            v.apply_local_auto_window(target="overlay")
            v.update_render(force_reblend=True)


def bench_mode(nn_mode, roi_above_overlay, actions, viewers, vs_base, n_iters, n_warmup=3):
    """Run all actions for one (nn_mode, roi) combo, return list of FPS values."""
    row = []
    for action in actions:
        for v in viewers:
            v.controller.settings.data["rendering"] = {
                "gl_nearest": nn_mode == NNMode.HW_GL_NEAREST,
                "single_texture": "Single" if nn_mode in (NNMode.SW_SINGLE_MERGED, NNMode.SW_SINGLE_NATIVE) else "Dual",
                "native_voxel": "Native" if nn_mode in (NNMode.SW_DUAL_NATIVE, NNMode.SW_SINGLE_NATIVE) else "Resampled",
                "lazy_lin": "Off",
            }
            vs_base.display.roi_above_overlay = roi_above_overlay
            v._nn_settle_done = True
            v._last_move_time = 0.0
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


def fmt_row(name, row, col_w=9, unit="FPS"):
    parts = [f"{val:>{col_w-1}.1f} {unit}" for val in row]
    return f"{name:<24} | " + " | ".join(parts)


def make_volume(path, shape, spacing):
    data = np.empty(shape, dtype=np.float32)
    data[:] = np.linspace(0, 100, shape[2], dtype=np.float32)[None, None, :]
    img = sitk.GetImageFromArray(data)
    img.SetSpacing(spacing)
    sitk.WriteImage(img, path)


def make_large_roi_mask(path, shape, spacing, origin, direction, coverage=0.5):
    """A large box mask covering `coverage` fraction of each axis, centered."""
    mask = np.zeros(shape, dtype=np.uint8)
    z, y, x = shape
    cz, cy, cx = int(z * coverage), int(y * coverage), int(x * coverage)
    z0, y0, x0 = (z - cz) // 2, (y - cy) // 2, (x - cx) // 2
    mask[z0:z0 + cz, y0:y0 + cy, x0:x0 + cx] = 1
    img = sitk.GetImageFromArray(mask)
    img.SetSpacing(spacing)
    img.SetOrigin(origin)
    img.SetDirection(direction)
    sitk.WriteImage(img, path)


def main():
    parser = argparse.ArgumentParser(description="VVV Fusion + Large ROI Benchmark")
    parser.add_argument("--quick", action="store_true", help="Small volumes, fast iteration (script smoke-test)")
    parser.add_argument("--very-quick", action="store_true", help="Tiny volumes and 2 iterations, for CI tests")
    parser.add_argument("--n-iters", type=int, default=15, help="Iterations per action (default 15)")
    args = parser.parse_args()

    if args.very_quick:
        n_iters, n_warmup = 2, 1
        base_shape = (10, 64, 64)
        ov_shape = (10, 48, 48)
    elif args.quick:
        n_iters, n_warmup = 3, 1
        base_shape = (60, 128, 128)
        ov_shape = (60, 96, 96)
    else:
        n_iters, n_warmup = args.n_iters, 3
        # Mirrors the real-world case that was slow: base ~500³, overlay
        # large enough to be a genuine memory/cache-locality burden
        # (~440x440x1095 / ~850MB was the actual reported case).
        base_shape = (1000, 512, 512)
        ov_shape = (700, 440, 440)

    print(f"Setting up benchmark data (base {base_shape[2]}x{base_shape[1]}x{base_shape[0]}, "
          f"overlay {ov_shape[2]}x{ov_shape[1]}x{ov_shape[0]}, "
          f"~{np.prod(ov_shape) * 4 / 1e6:.0f}MB overlay)...")

    with tempfile.TemporaryDirectory() as tmpdir:
        base_path = os.path.join(tmpdir, "base.nii")
        ov_path = os.path.join(tmpdir, "ov.nii")
        roi_path = os.path.join(tmpdir, "roi.nii")

        make_volume(base_path, base_shape, (1.0, 1.0, 1.0))
        make_volume(ov_path, ov_shape, (1.25, 2.0, 2.0))

        print("Loading files into VVV Controller...")
        c = Controller()
        c.gui = MagicMock()
        c.gui.ui_cfg = {"layout": {"viewport_padding": 4}}
        c.gui.interaction = None  # deterministic: no active ROI drag

        base_id = c.file.load_image(base_path)
        ov_id = c.file.load_image(ov_path)

        vs_base = c.view_states[base_id]
        base_vol = c.volumes[base_id]
        ov_vol = c.volumes[ov_id]
        vs_base.set_overlay(ov_id, ov_vol)
        c._apply_overlay_resample(vs_base, c.view_states[ov_id])
        vs_base.display.overlay_mode = "Alpha"
        vs_base.display.overlay_opacity = 0.5
        vs_base.display.pixelated_zoom = True

        overlay_ready = vs_base.display.overlay_data is not None
        if not overlay_ready:
            print("WARNING: overlay resampling did not complete — overlay-dependent modes will show base-only cost")

        print("Creating and loading a large ROI mask (50% coverage box)...")
        make_large_roi_mask(
            roi_path, base_vol.shape3d, base_vol.spacing.tolist(),
            base_vol.origin.tolist(), base_vol.matrix.flatten().tolist(),
            coverage=0.5,
        )
        roi_id = c.roi.load_binary_mask(base_id, roi_path)
        roi_ready = roi_id in c.volumes and hasattr(c.volumes[roi_id], "roi_bbox")
        if not roi_ready:
            print("WARNING: ROI load did not complete — ROI rows will show base+fusion cost only")

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

        modes = [
            ("SW Dual-Tex Native", NNMode.SW_DUAL_NATIVE),
            ("SW Single-Tex Native", NNMode.SW_SINGLE_NATIVE),
        ]
        actions = ["Slicing", "Pan Move", "Zoom In", "Zoom Out", "W/L (W)", "W/L (X)"]
        os_label = platform.system()
        sep = "-" * 96

        print(f"\n{'='*96}")
        print(f"  {os_label}  ·  Fusion + Large ROI  ·  {n_iters} iters/action")
        print(f"  ROI coverage: 50% box, {'ON' if roi_ready else 'FAILED TO LOAD'}")
        print(f"{'='*96}")
        print(f"{'Mode':<24} | {'Slicing':>9} | {'Pan Move':>9} | {'Zoom In':>9} | {'Zoom Out':>9} | {'W/L (W)':>9} | {'W/L (X)':>9}")
        print(sep)

        for mode_name, nn_mode in modes:
            row_no_roi = bench_mode(nn_mode, False, actions, viewers, vs_base, n_iters, n_warmup)
            print(fmt_row(f"{mode_name} (no ROI)", row_no_roi))
            if roi_ready:
                row_roi = bench_mode(nn_mode, True, actions, viewers, vs_base, n_iters, n_warmup)
                print(fmt_row(f"{mode_name} (+ROI)", row_roi))
                delta = [
                    (1.0 / r - 1.0 / n) * 1000 if r > 0 and n > 0 else 0.0
                    for n, r in zip(row_no_roi, row_roi)
                ]
                print(fmt_row("  delta ROI cost", delta, unit="ms"))
            print(sep)

        print(
            "\nNote: Slicing is expected to stay the most expensive action — it's the one case "
            "where both the geometry cache and the ROI mask cache legitimately invalidate every "
            "iteration (new slice data each time). Pan/Zoom/W-L should be cheap regardless of ROI, "
            "since nothing they touch invalidates either cache."
        )


if __name__ == "__main__":
    main()
