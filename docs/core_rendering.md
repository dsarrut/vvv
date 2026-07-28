# Rendering Pipeline

## 1. Architecture Overview

1. **CPU Extract**: `SliceRenderer` generates raw RGBA arrays (`last_rgba_flat`, `last_overlay_rgba_flat`).
2. **Texture Prep**: Upscaling (NN vs Bilinear) and compositing applied based on mode.
3. **GPU Draw**: DPG `draw_image` renders the final texture(s).

## 2. Modes (`NNMode`)

* **`HW_GL_NEAREST`**: (Linux/Win) Zero-cost hardware GPU upscaling.
* **`SW_DUAL_NATIVE`**: 2 canvas-sized textures. RLE base, native-voxel overlay.
* **`SW_DUAL_RESAMPLED`**: 2 canvas-sized textures. Both scaled via RLE from ITK grids.
* **`SW_SINGLE_MERGED`**: 1 texture. CPU alpha-blends ITK slices, then RLE scales.
* **`SW_SINGLE_NATIVE`**: 1 texture. RLE base + native-voxel overlay painted into same buffer. (macOS default for fusion).

## 3. Optimizations

### Lazy-Lin
Drops to GPU bilinear interpolation during interaction (pan/zoom/W&L drag) to preserve 60FPS. Restores to full NN quality after 150ms settle time. Triggered globally via `_mark_lazy_interaction()`.

### Numba Acceleration
Used to accelerate `compute_native_voxel_overlay` (~40x faster than pure NumPy) by compiling the affine canvas mapping to JIT machine code.

**If numba is not installed/importable, this silently falls back to the pure-NumPy path** — no error, just ~40-50x slower fusion rendering. This is easy to miss (it happened during development on this exact codebase). A startup warning (`cli.py`) and a `Numba: ON/OFF` indicator in the `--debug` info panel (`gui.py`) now surface this explicitly.

### Native-Overlay Geometry Cache
`compute_native_voxel_overlay`'s transform composition (`A_total`/`b_total`), the overlay bbox corner projection, and the resulting screen-crop bounds depend only on the registration transform, threshold, volumes, and orientation — not on zoom/pan. This is now cached per-viewer (`viewer._native_ov_geom_cache`) and only recomputed when one of those actually changes, instead of on every frame. Keyed on transform *values* (`GetMatrix()`/`GetTranslation()`/`GetFixedParameters()`), not object identity — registration dragging mutates the transform in place (`SetCenter`/`SetTranslation`) rather than replacing it, so identity comparison would silently show a stale overlay position mid-drag.

### ROI Mask Buffer Cache
`build_roi_mask_buffer()` (composites all active ROI masks/colors into `h×w` buffers for native-voxel painting) was being rebuilt from scratch every frame, including pure zoom/pan where no ROI actually changed. For large ROIs this dominated `compute_native_voxel_overlay`'s cost far more than the numba kernel itself (~90% of it, in profiling). Now cached per-viewer via `TextureManager._get_cached_roi_mask()`, keyed on `(h, w, [(id(roi.data), color, opacity, offset_x, offset_y) for each active ROI])`. Safe because `LayerPackager.package_roi_layers()` already reuses the same array object per ROI when its slice hasn't changed, so `id(roi.data)` is a valid, cheap invalidation signal.

## 4. Diagnostics

Set `VVV_PROFILE=1` to get a per-stage timing breakdown printed every 30 render calls, summed across all viewers:
- `extract` — raw slice extraction (`_compute_raw_slice_buffers`), split into `package` / `extract_base` / `extract_overlay`
- `upload_base` — NN scaling + native overlay compositing, split into `nn_base` / `native_overlay` (further split into `roi_package` / `roi_mask_build`)
- `upload_overlay`, `gpu_set_value` — separate overlay texture upload and the actual `dpg.set_value` GPU upload cost
- A one-time `[VVV_PROFILE:overlay] use_numba=...` line confirms whether the numba path is actually active
- `[VVV_PROFILE:overlay]` lines report the native-overlay kernel's real workload (crop pixel count, overlay voxel count, kernel-only time) every 30 calls

This is left in place (zero overhead when unset) since it was decisive for diagnosing the issues above — a synthetic benchmark using representative-looking data missed the numba fallback and the ROI cost entirely.

## 5. Rejected Approach: Texture-Size Capping

An earlier attempt capped the SW NN texture buffer below full canvas resolution (either flat, or zoom-aware based on visible source pixels) and relied on DPG's GPU stretch to fill the rest, on the theory that NN block edges would stay sharp. **This doesn't hold on macOS**: DPG's dynamic textures only support float32 (`mvFormat_Float_rgba`), there is no sampler/filter API to force nearest-neighbor magnification, and `try_set_gl_nearest()` explicitly no-ops on macOS (raw GL calls crash under Metal — this is *why* the whole SW NN pipeline exists). Any texture smaller than its on-screen draw quad gets bilinear-blurred at block boundaries, which is clearly visible and defeats the purpose of NN mode. Reverted in full — don't retry this without a genuine macOS-side nearest-filter mechanism.

## 6. Known Remaining Bottleneck

With fusion + ROIs both on, steady-state zoom/pan is now back to baseline cost (matching fusion-only or ROI-only individually). What's left is **slice extraction** itself during actual slicing: `SliceRenderer.get_slice_rgba()` pulling a fresh 2D slice out of a large overlay volume (observed: ~25-40ms summed across 4 viewers for a 440×440×1095 / ~850MB overlay). Not yet investigated — none of the caching fixes above touch it, since a genuine slice change legitimately invalidates them all.
