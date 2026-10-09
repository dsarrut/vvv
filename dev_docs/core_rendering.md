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

### ROI Compositing Cache (get_slice_rgba / _apply_rois)

Separate from the native-overlay ROI mask cache above: `SliceRenderer._apply_rois()` (called from `get_slice_rgba()`, used for the Alpha-mode base/overlay textures) was also rebuilding its ROI mask/color buffers via `build_roi_mask_buffer()` from scratch on every call — including W/L changes, which force a reblend but never touch the ROI. This is a genuinely separate code path from the native-overlay cache (different call site, different resolution space — native canvas vs. slice-native), so that earlier fix didn't cover it.

Fixed the same way: `_apply_rois()` now takes an optional `cache_holder`/`cache_attr` (the `SliceViewer` instance, one attr per call site — `get_slice_rgba()` can be invoked up to 3 times per viewer per frame depending on `roi_above_overlay`, so each needs its own slot). Verified via instrumentation that `build_roi_mask_buffer()` drops to zero calls across repeated W/L updates once the ROI set is unchanged.

This alone didn't fully explain the measured W/L slowdown, though — profiling showed the remaining cost was the alpha-blend step itself (`np.where`/multiply over the full canvas), which necessarily reruns every time because the base RGBA changes with windowing even when the ROI doesn't. Since `roi_mask` is mostly zero outside the ROI's own footprint, `_apply_rois` now derives the ROI's bounding box from `roi_mask` (two `.any()` reductions) and restricts the blend to that sub-region instead of the full `h×w` canvas — a no-op-preserving, size-proportional speedup (bigger win the smaller/sparser the ROI is relative to the canvas).

Net effect on `bench_fusion_roi_large.py` (full-size, 50%-coverage ROI — a pessimistic case since the bbox covers a large fraction of the canvas): W/L's Δ ROI cost dropped from ~20-25ms to ~2-6ms. Slicing's Δ ROI cost also dropped, from ~65-71ms to ~25-28ms — the bbox-restricted blend helps there too even though the mask itself still legitimately rebuilds every slice (a real slice change invalidates the cache by design). That remaining ~25-28ms during Slicing is the inherent cost of rebuilding+compositing a large ROI mask on a genuinely new slice, not a caching gap.

Both `_apply_rois()` call sites are reached from `get_slice_rgba()`, which runs unconditionally on every `_compute_raw_slice_buffers()` call regardless of `NNMode` — including `HW_GL_NEAREST` on Linux/Windows, since that mode only changes how the resulting texture is upscaled to the canvas, not whether the CPU extraction/compositing stage runs. So this fix (and the ROI mask cache above) benefit all platforms equally, not just the macOS SW-NN path.

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

With fusion + ROIs both on, steady-state zoom/pan is now back to baseline cost (matching fusion-only or ROI-only individually), and both W/L and Slicing's ROI-specific overhead are substantially reduced (see ROI Compositing Cache above). What's left, and distinct from ROI compositing, is **slice extraction** itself during actual slicing: `SliceRenderer.get_slice_rgba()` pulling a fresh 2D slice out of a large overlay volume, no ROI involved (observed: ~25-40ms summed across 4 viewers for a 440×440×1095 / ~850MB overlay). Not yet investigated — none of the caching fixes above touch it, since a genuine slice change legitimately invalidates them all. The next thing to try (per discussion, not yet done): compare axial vs. sagittal/coronal extraction cost on the same overlay to check whether this is memory-layout/contiguity-bound (strided reads across the volume's slow axis) or simply bandwidth-bound.

This was the point where further optimization was judged not worth the effort for the current use case ("good enough") — noted here so a future investigation doesn't have to rediscover it.
