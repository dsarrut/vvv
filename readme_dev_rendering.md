
# Developer Guide: Rendering Pipeline

This document outlines the four main rendering pathways and their platform-specific optimizations.

## 1. Single Image, Linear
**macOS, Linux, & Windows:**
- **Extraction:** The CPU extracts the exact 2D slice from the NumPy array at its native resolution (e.g., 512x512).
- **Rendering:** This small array is colorized and pushed to the GPU as a single dynamic texture.
- **Scaling:** DearPyGui tells the GPU to stretch this small texture across the viewport's physical coordinates (`pmin` to `pmax`). The GPU applies its default hardware Bilinear interpolation, resulting in a smooth, high-fps image.

## 2. Single Image, Nearest Neighbor (NN)
**Linux & Windows (The Hardware Fast Path):**
- Because DearPyGui uses OpenGL on Linux and Windows, VVV executes a clever ctypes registry hack (`gl_nn_apply_pending()` & `gl_nn_reapply_all()`) to modify the underlying graphics API dynamically.
- The CPU does exactly what it does in Linear mode: pushes a tiny native-resolution texture to the GPU. The GPU natively handles the blocky, pixelated upscaling (`GL_NEAREST`) at 0 CPU cost.

**macOS (The CPU Fallback):**
- Metal does not allow raw OpenGL hacks.
- VVV routes the slice through `_get_screen_mapped_texture()`. This highly optimized pure-NumPy function:
  1. **Calculates Viewport:** Determines exactly how big the viewport is (e.g., 1920x1080).
  2. **RLE Bulk Copy:** Uses Run-Length Encoding (`np.repeat`) to tile the pixels on the CPU instantly, bypassing slow scatter-gather indexing.
  3. **Persistent Buffers:** Writes directly into a persistent Canvas Buffer (`_base_canvas_buffer`) to completely eliminate OS `malloc` thrashing and garbage collection overhead.
  4. This massive, pre-pixelated canvas is uploaded to the GPU and drawn exactly at `pmin=[0,0]`.

## 3. Two Images Fusion, Linear
**macOS, Linux, & Windows:**
- **Background Math:** When fused, a background thread uses SimpleITK (`sitkLinear`) to 3D-resample the overlay volume into the exact spatial grid of the base image.
- **CPU Blending:** During the 60fps render loop, the CPU extracts a native-resolution slice from the Base image and a matching slice from the resampled Overlay buffer.
- **Rendering:** `SliceRenderer.get_slice_rgba()` blends these two arrays together on the CPU into a single, native-resolution RGBA flat array. This single texture is uploaded to the GPU and stretched bilinearly to fit the screen.

## 4. Two Images Fusion, Nearest Neighbor (NN)
VVV implements five distinct NN rendering strategies (defined in `NNMode`), allowing users to toggle between them (default key: `J`) depending on OS capabilities and performance needs.

**0. Hardware GL_NEAREST (Linux & Windows Only):**
- **Pipeline:** Leaves both Base and ITK-resampled Overlay images as small, native-resolution textures.
- **Scaling:** Uses ctypes to inject `glTexParameteri(GL_NEAREST)` so the GPU handles the blocky upscaling automatically. Near zero CPU cost.

**1. SW Dual-Tex Native (Default Fallback for macOS):**
- **Pipeline:** Creates two massive screen-sized (canvas) textures.
- **Base:** Upscaled using the CPU-based Run-Length Encoding (RLE) mapping (`compute_software_nearest_neighbor`).
- **Overlay:** Uses the "Native Voxel Overlay Engine" (`compute_native_voxel_overlay`). It analytically maps canvas pixels backward through registration matrices directly into the raw 3D overlay array, bypassing SimpleITK resampling to preserve true voxel blockiness (e.g., 4mm SPECT over 1mm CT).

**2. SW Dual-Tex Resampled:**
- **Pipeline:** Creates two canvas-sized textures.
- **Base & Overlay:** Both use the CPU RLE mapper on the ITK-resampled slice grids. Fast, but loses the "true" physical voxel size of the original overlay if it differs from the base grid.

**3. SW Single-Tex Merged (Pre-Compositing):**
- **Pipeline:** Creates exactly one canvas-sized texture, cutting GPU upload bandwidth in half.
- **Math:** Alpha-blends the ITK-resampled overlay slice directly onto the base slice *on the CPU* (`blend_slices_cpu`), then runs the RLE upscaler on the combined single image.

**4. SW Single-Tex Native:**
- **Pipeline:** Creates exactly one canvas-sized texture.
- **Math:** First runs the RLE upscaler on the base image, then directly alpha-blends the blocky "Native Voxel" overlay pixels into the exact same memory buffer on the CPU before uploading to the GPU.

## 5. Lazy Rendering (Interaction Optimizations)
To maintain 60+ FPS during heavy continuous interactions (Panning, Zooming, Window/Leveling) on macOS software paths, VVV employs "Lazy" states triggered by `_mark_lazy_interaction()`:

- **Lazy NN:** During interaction, the heavy overlay NN math is skipped. The user drags the pixelated base image smoothly. Once the mouse rests for 150ms (`lazy_nn_settle_ms`), a full dual-texture NN upload fires to restore the overlay.
- **Lazy Lin:** During interaction, the entire viewer drops out of pixelated mode entirely and uses hardware Bilinear scaling (fastest possible framerate). Once resting for 150ms, it snaps back into the blocky NN modes.