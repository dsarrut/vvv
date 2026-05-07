
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
**All Platforms (The Native Voxel Overlay Engine):**
- **Bypassing ITK:** The background SimpleITK resampler is completely ignored. VVV recognizes that resampling a 4mm SPECT to a 1mm CT destroys the "true" blocky resolution of the SPECT.
- **Dual Crop Analytics:** VVV triggers `_render_overlay_as_native_voxels()`. This engine analytically maps the screen Canvas pixels backward through the registration matrices directly into the raw 3D overlay array.
  - **Screen Crop:** Quickly projects the 3D corners of the overlay onto the screen, completely skipping math for background pixels.
  - **Image Crop:** Slices a tiny block from the massive NumPy array to maximize CPU L1/L2 cache hits during extreme zoom.
- **RLE Generation:** Identifies pixel blocks using Run-Length Encoding and blasts them to a Persistent Canvas Buffer (`_native_ov_buf`) using SIMD `np.repeat`.

**Linux & Windows (Base Image):**
- The base image remains a tiny, native-resolution texture. It uses the `GL_NEAREST` hack to stretch across the screen, sitting perfectly underneath the Canvas-sized overlay texture.

**macOS (Base Image):**
- Lacking `GL_NEAREST`, the Base image is also routed through the CPU `_get_screen_mapped_texture()` engine. Both the Base and Overlay are uploaded as massive Canvas-sized textures and drawn 1:1 on top of each other.