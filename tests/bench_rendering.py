#!/usr/bin/env python3
"""
VVV Rendering Performance Benchmark
=====================================
Measures ms/frame and equivalent FPS for the key rendering operations.
Does NOT require a running GUI — exercises pure-numpy kernels only.

Usage:
    cd /path/to/vvv
    python tests/bench_rendering.py              # default sizes
    python tests/bench_rendering.py --save       # also write bench_YYYYMMDD_HHMMSS.txt
    python tests/bench_rendering.py --quick      # fewer iterations, faster run

Scenarios:
  1. Slice rendering (get_slice_rgba) — 3 orientations, optional overlay
  2. NN screen mapping (_get_screen_mapped_texture) — zoom levels × canvas sizes
  3. Full pipeline: slice + NN mapping, Linear vs NN, with/without overlay
  All scenarios are run for N_VIEWERS=4 (sequential worst-case).

Configurable constants at the top of this file (VOLUME_SHAPES, CANVAS_SIZES, …).
"""

import sys
import os
import time
import argparse
import platform
import datetime

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from vvv.maths.image import SliceRenderer, RenderLayer
from vvv.utils import ViewMode
from vvv.ui.viewer import SliceViewer


# ──────────────────────────────────────────────────────────────────────────────
# Configuration — edit these to match your target workload
# ──────────────────────────────────────────────────────────────────────────────

# 3-D volume shapes (depth, height, width)  –  float32 memory shown as comment
VOLUME_SHAPES = {
    "256×512×512  (268 MB)": (256, 512, 512),
    "100×1000×1000 (400 MB)": (100, 1000, 1000),
    # "512×512×512  (512 MB)": (512, 512, 512),   # uncomment for a full cube
    # "1000×1000×100 (400 MB)": (1000, 1000, 100), # deep sagittal/coronal slices
}

# Canvas sizes (width, height) — simulates the viewer window dimensions
CANVAS_SIZES = {
    "512×512": (512, 512),
    "1024×768": (1024, 768),
    "1920×1080": (1920, 1080),
}

N_SLICES = 30   # distinct slices stepped through per timing call
N_ITER = 5      # timing repetitions (mean/min/max computed)
N_WARMUP = 3    # warm-up calls (not counted)
N_VIEWERS = 4   # simulated simultaneous viewers (time is multiplied)

ORIENTATIONS = [ViewMode.AXIAL, ViewMode.SAGITTAL, ViewMode.CORONAL]
ORI_NAMES = {
    ViewMode.AXIAL: "Axial",
    ViewMode.SAGITTAL: "Sagittal",
    ViewMode.CORONAL: "Coronal",
}

# Zoom expressed as "factor × fill" (1.0 = image exactly fills canvas).
# Values > 1 mean zoomed in (image extends beyond canvas edges → fast NN path).
# Values < 1 mean zoomed out (image smaller than canvas → slow NN path).
ZOOM_FACTORS = {
    "0.5× (zoomed out, slow path)": 0.5,
    "1× (fill, fast path)": 1.0,
    "2× zoom in (fast path)": 2.0,
    "4× zoom in (fast path)": 4.0,
}

# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────


def make_layer(data: np.ndarray, ww: float = 1000.0, wl: float = 500.0) -> RenderLayer:
    return RenderLayer(
        data=data,
        is_rgb=False,
        num_components=1,
        ww=ww,
        wl=wl,
        cmap_name="Gray",
        threshold=None,
        time_idx=0,
        spacing_2d=(1.0, 1.0),
    )


def max_slices(vol_shape: tuple, ori: ViewMode) -> int:
    """Number of slices along *ori* for a 3-D volume of given shape (D, H, W)."""
    # _AXIS_MAP after the (1,) prepend trick maps:
    #   AXIAL    s_ax=1 → D = vol_shape[0]
    #   SAGITTAL s_ax=3 → W = vol_shape[2]
    #   CORONAL  s_ax=2 → H = vol_shape[1]
    return vol_shape[{ViewMode.AXIAL: 0, ViewMode.SAGITTAL: 2, ViewMode.CORONAL: 1}[ori]]


def slice_shape(vol_shape: tuple, ori: ViewMode) -> tuple[int, int]:
    """2-D pixel dimensions of one slice for a (D, H, W) volume."""
    D, H, W = vol_shape
    # extract_slice returns:
    #   AXIAL    data[t, k, :, :]  → (H, W)
    #   SAGITTAL data[t, :, :, k]  → (D, H)
    #   CORONAL  data[t, :, k, :]  → (D, W)
    return {
        ViewMode.AXIAL:    (H, W),
        ViewMode.SAGITTAL: (D, H),
        ViewMode.CORONAL:  (D, W),
    }[ori]


def pmin_pmax(img_w: int, img_h: int, canvas_w: int, canvas_h: int, zoom: float):
    """
    Compute centred (pmin, pmax) in screen-pixel space.

    zoom is relative to "fill": zoom=1 → image fills canvas exactly,
    zoom=2 → image is 2× as large as the canvas (zoomed in, image bleeds
    outside canvas edges on all sides → no black borders → fast NN path).
    """
    disp_w = canvas_w * zoom
    disp_h = canvas_h * zoom
    pmx = [(canvas_w - disp_w) / 2, (canvas_h - disp_h) / 2]
    pmn = [(canvas_w + disp_w) / 2, (canvas_h + disp_h) / 2]
    return pmx, pmn  # note: pmin is the top-left corner


def bench(fn, n_warmup: int = N_WARMUP, n_iter: int = N_ITER):
    """Run fn() with warmup, return (mean_ms, min_ms, max_ms)."""
    for _ in range(n_warmup):
        fn()
    times = []
    for _ in range(n_iter):
        t0 = time.perf_counter()
        fn()
        times.append((time.perf_counter() - t0) * 1000.0)
    return float(np.mean(times)), float(np.min(times)), float(np.max(times))


def fps(ms: float) -> float:
    return 1000.0 / ms if ms > 0 else float("inf")


def row(label: str, mean_ms: float, min_ms: float, max_ms: float) -> str:
    """Single report row: label | ms (min-max) | fps | 4-viewer ms | 4-viewer fps."""
    v4_ms = mean_ms * N_VIEWERS
    return (
        f"  {label:<42s}"
        f"  {mean_ms:7.2f} ms"
        f"  ({min_ms:.2f}–{max_ms:.2f})"
        f"  {fps(mean_ms):7.1f} fps"
        f"  │  {v4_ms:7.2f} ms  {fps(v4_ms):6.1f} fps"
    )


def section(title: str, lines: list[str]) -> None:
    lines.append("")
    lines.append("─" * 90)
    lines.append(f"  {title}")
    lines.append("─" * 90)
    lines.append(
        f"  {'Scenario':<42s}"
        f"  {'mean ms':>8s}  {'(min–max)':>12s}"
        f"  {'fps':>8s}"
        f"  │  {'4v ms':>8s}  {'4v fps':>7s}"
    )
    lines.append("  " + "-" * 88)


def make_volume(shape: tuple, rng) -> np.ndarray:
    return rng.random(shape).astype(np.float32)


# ──────────────────────────────────────────────────────────────────────────────
# Individual scenario runners
# ──────────────────────────────────────────────────────────────────────────────


def run_slice_rendering(
    vol: np.ndarray,
    overlay: np.ndarray | None,
    lines: list[str],
    n_warmup: int,
    n_iter: int,
) -> None:
    """Benchmark get_slice_rgba for all orientations."""
    base = make_layer(vol)
    ov = make_layer(overlay) if overlay is not None else None
    ov_label = " +ov" if ov else "    "

    for ori in ORIENTATIONS:
        n_s = max_slices(vol.shape, ori)
        slices = np.linspace(1, n_s - 2, N_SLICES, dtype=int)

        def _fn():
            for s in slices:
                SliceRenderer.get_slice_rgba(
                    base=base,
                    overlay=ov,
                    overlay_opacity=0.5 if ov else 0.0,
                    overlay_mode="Alpha",
                    slice_idx=int(s),
                    orientation=ori,
                    rois=[],
                )

        total_ms, total_min, total_max = bench(_fn, n_warmup, n_iter)
        per_ms = total_ms / N_SLICES
        per_min = total_min / N_SLICES
        per_max = total_max / N_SLICES
        sh = slice_shape(vol.shape, ori)
        label = f"{ORI_NAMES[ori]}{ov_label} ({n_s} slices, slice={sh[0]}×{sh[1]}px)"
        lines.append(row(label, per_ms, per_min, per_max))


def run_nn_mapping(
    img_h: int,
    img_w: int,
    canvas_h: int,
    canvas_w: int,
    zoom_name: str,
    zoom: float,
    lines: list[str],
    n_warmup: int,
    n_iter: int,
) -> None:
    """Benchmark _get_screen_mapped_texture at one (canvas, zoom) combination."""
    rng = np.random.default_rng(42)
    rgba = rng.random((img_h, img_w, 4)).astype(np.float32)
    pm, px = pmin_pmax(img_w, img_h, canvas_w, canvas_h, zoom)

    def _fn():
        SliceViewer._get_screen_mapped_texture(rgba, pm, px, canvas_w, canvas_h)

    mean_ms, min_ms, max_ms = bench(_fn, n_warmup, n_iter)
    label = f"img {img_w}×{img_h}  canvas {canvas_w}×{canvas_h}  {zoom_name}"
    lines.append(row(label, mean_ms, min_ms, max_ms))


def run_full_pipeline(
    vol: np.ndarray,
    overlay: np.ndarray | None,
    canvas_w: int,
    canvas_h: int,
    nn_mode: bool,
    lines: list[str],
    n_warmup: int,
    n_iter: int,
) -> None:
    """Benchmark slice-render + optional NN mapping for all orientations."""
    base = make_layer(vol)
    ov = make_layer(overlay) if overlay is not None else None
    # Use zoom=2× so image fills the canvas (fast NN path active)
    pm, px = pmin_pmax(vol.shape[2], vol.shape[1], canvas_w, canvas_h, zoom=2.0)
    mode_label = "NN  " if nn_mode else "Lin "
    ov_label = "+ov" if ov else "   "

    for ori in ORIENTATIONS:
        n_s = max_slices(vol.shape, ori)
        slices = np.linspace(1, n_s - 2, N_SLICES, dtype=int)

        def _fn():
            for s in slices:
                if ov is not None:
                    rgba, shape = SliceRenderer.get_slice_rgba(
                        base=base, overlay=None, overlay_opacity=1.0,
                        overlay_mode="Alpha", slice_idx=int(s),
                        orientation=ori, rois=[],
                    )
                    ov_rgba, ov_shape = SliceRenderer.get_slice_rgba(
                        base=ov, overlay=None, overlay_opacity=1.0,
                        overlay_mode="Alpha", slice_idx=int(s),
                        orientation=ori, rois=[],
                    )
                else:
                    rgba, shape = SliceRenderer.get_slice_rgba(
                        base=base, overlay=None, overlay_opacity=0.0,
                        overlay_mode="Alpha", slice_idx=int(s),
                        orientation=ori, rois=[],
                    )
                    ov_rgba = ov_shape = None

                if nn_mode:
                    rgba_2d = rgba.reshape((shape[0], shape[1], 4))
                    SliceViewer._get_screen_mapped_texture(
                        rgba_2d, pm, px, canvas_w, canvas_h
                    )
                    if ov_rgba is not None and ov_shape is not None:
                        ov_2d = ov_rgba.reshape((ov_shape[0], ov_shape[1], 4))
                        SliceViewer._get_screen_mapped_texture(
                            ov_2d, pm, px, canvas_w, canvas_h
                        )

        total_ms, total_min, total_max = bench(_fn, n_warmup, n_iter)
        per_ms = total_ms / N_SLICES
        per_min = total_min / N_SLICES
        per_max = total_max / N_SLICES
        sh = slice_shape(vol.shape, ori)
        label = f"{mode_label} {ov_label}  {ORI_NAMES[ori]}  slice={sh[0]}×{sh[1]}px  canvas {canvas_w}×{canvas_h}"
        lines.append(row(label, per_ms, per_min, per_max))


# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────


def main(save: bool = False, quick: bool = False) -> None:
    n_warmup = 1 if quick else N_WARMUP
    n_iter = 2 if quick else N_ITER
    rng = np.random.default_rng(0)

    lines: list[str] = []

    # ── Header ────────────────────────────────────────────────────────────────
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines += [
        "=" * 90,
        "  VVV RENDERING PERFORMANCE BENCHMARK",
        "=" * 90,
        f"  Date      : {now}",
        f"  Platform  : {platform.system()} {platform.release()} ({platform.machine()})",
        f"  Python    : {platform.python_version()}",
        f"  NumPy     : {np.__version__}",
        f"  n_warmup  : {n_warmup}   n_iter : {n_iter}   n_slices : {N_SLICES}",
        "",
        "  Columns: mean ms/frame  (min–max)  fps  │  4-viewer equivalent (× 4, sequential)",
        "  'fast path' = NN repeat-expand path (zoom ≥ fill, no black border).",
        "  'slow path' = NN fancy-index fallback (image smaller than canvas area).",
    ]

    # ── Section 1: slice rendering, no overlay ────────────────────────────────
    section("1. SLICE RENDERING — get_slice_rgba, no overlay", lines)

    for vol_name, vol_shape in VOLUME_SHAPES.items():
        lines.append(f"\n  ── Volume: {vol_name}  shape={vol_shape}")
        try:
            vol = make_volume(vol_shape, rng)
        except MemoryError:
            lines.append("  !! Skipped — not enough memory.")
            continue
        run_slice_rendering(vol, None, lines, n_warmup, n_iter)
        del vol

    # ── Section 2: slice rendering, with overlay ──────────────────────────────
    section("2. SLICE RENDERING — get_slice_rgba, with overlay (same-size)", lines)

    for vol_name, vol_shape in VOLUME_SHAPES.items():
        lines.append(f"\n  ── Volume: {vol_name}  shape={vol_shape}")
        try:
            vol = make_volume(vol_shape, rng)
            ov = make_volume(vol_shape, rng)
        except MemoryError:
            lines.append("  !! Skipped — not enough memory.")
            continue
        run_slice_rendering(vol, ov, lines, n_warmup, n_iter)
        del vol, ov

    # ── Section 3: NN screen mapping in isolation ─────────────────────────────
    section("3. NN SCREEN MAPPING — _get_screen_mapped_texture", lines)

    for (canvas_name, (canvas_w, canvas_h)) in CANVAS_SIZES.items():
        lines.append(f"\n  ── Canvas: {canvas_name}")
        for img_h, img_w in [(512, 512), (1000, 1000)]:
            for zoom_name, zoom in ZOOM_FACTORS.items():
                run_nn_mapping(
                    img_h, img_w, canvas_h, canvas_w,
                    zoom_name, zoom, lines, n_warmup, n_iter,
                )

    # ── Section 4: full pipeline, no overlay, 1920×1080 ──────────────────────
    section("4. FULL PIPELINE — 1920×1080 canvas, no overlay", lines)

    canvas_w, canvas_h = 1920, 1080
    for vol_name, vol_shape in VOLUME_SHAPES.items():
        lines.append(f"\n  ── Volume: {vol_name}  shape={vol_shape}")
        try:
            vol = make_volume(vol_shape, rng)
        except MemoryError:
            lines.append("  !! Skipped — not enough memory.")
            continue
        run_full_pipeline(vol, None, canvas_w, canvas_h, False, lines, n_warmup, n_iter)
        run_full_pipeline(vol, None, canvas_w, canvas_h, True, lines, n_warmup, n_iter)
        del vol

    # ── Section 5: full pipeline, with overlay, 1920×1080 ────────────────────
    section("5. FULL PIPELINE — 1920×1080 canvas, with overlay", lines)

    for vol_name, vol_shape in VOLUME_SHAPES.items():
        lines.append(f"\n  ── Volume: {vol_name}  shape={vol_shape}")
        try:
            vol = make_volume(vol_shape, rng)
            ov = make_volume(vol_shape, rng)
        except MemoryError:
            lines.append("  !! Skipped — not enough memory.")
            continue
        run_full_pipeline(vol, ov, canvas_w, canvas_h, False, lines, n_warmup, n_iter)
        run_full_pipeline(vol, ov, canvas_w, canvas_h, True, lines, n_warmup, n_iter)
        del vol, ov

    # ── Footer ────────────────────────────────────────────────────────────────
    lines += ["", "=" * 90, "  END OF BENCHMARK", "=" * 90]

    report = "\n".join(lines)
    print(report)

    if save:
        fname = f"bench_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        with open(fname, "w") as f:
            f.write(report + "\n")
        print(f"\n  Report saved to: {fname}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="VVV rendering benchmark")
    parser.add_argument("--save", action="store_true", help="Save report to timestamped .txt file")
    parser.add_argument("--quick", action="store_true", help="Fewer iterations for a fast sanity check")
    args = parser.parse_args()
    main(save=args.save, quick=args.quick)
