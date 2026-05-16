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
