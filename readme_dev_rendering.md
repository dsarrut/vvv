


1. Single Image, Linear

macOS & Linux:
- Extraction: The CPU extracts the exact 2D slice from the Numpy array at its native resolution (e.g., 512x512).
- Rendering: This small array is colorized and pushed to the GPU as a single dynamic texture.
- Scaling: DearPyGui tells the GPU to stretch this small texture across the viewport's physical coordinates (pmin to pmax). The GPU applies its default hardware Bilinear interpolation, resulting in a smooth, high-fps image.

2. Single Image, Nearest Neighbor (NN)

Linux (The Fast Path):
- Because DearPyGui uses OpenGL on Linux, VVV executes a clever ctypes hack (_try_set_gl_nearest()) to modify the underlying graphics API.
- The CPU does exactly what it does in Linear mode: pushes a tiny 512x512 texture to the GPU. The GPU natively handles the blocky, pixelated upscaling at 0 CPU cost.

macOS (The CPU Fallback):
- Metal does not allow raw OpenGL hacks.
- VVV routes the slice through _get_screen_mapped_texture(). This highly optimized pure-Numpy function calculates exactly how big the viewport is (e.g., 1920x1080) and manually repeats/tiles the pixels on the CPU until the array matches the screen 1:1. This massive, pre-pixelated canvas is uploaded to the GPU and drawn exactly at pmin=[0,0].

3. Two Images Fusion, Linear

macOS & Linux:
- Background Math: When fused, a background thread uses SimpleITK with sitkLinear to 3D-resample the overlay volume into the exact spatial grid of the base image.
- CPU Blending: During the 60fps render loop, the CPU extracts a native-resolution slice from the Base image and a matching slice from the resampled Overlay buffer.
- Rendering: SliceRenderer.get_slice_rgba() blends these two arrays together on the CPU into a single, native-resolution RGBA flat array. This single texture is uploaded to the GPU and stretched bilinearly to fit the screen.

4. Two Images Fusion, Nearest Neighbor (NN)

macOS & Linux (The Overlay Engine):

- Bypassing ITK: The background SimpleITK resampler is completely ignored. VVV recognizes that resampling a 4mm SPECT to a 1mm CT destroys the "true" blocky resolution of the SPECT.
- Native Voxel Mapping: VVV triggers _render_overlay_as_native_voxels(). This engine analytically maps the screen Canvas pixels backward through the registration matrices directly into the raw, un-resampled 3D overlay array. It produces a massive, Canvas-sized (e.g., 1920x1080) texture of perfectly preserved, blocky native pixels.

Linux (Base Image):
- The base image remains a tiny, native-resolution texture. It uses the GL_NEAREST hack to stretch across the screen, sitting underneath the Canvas-sized overlay texture.

macOS (Base Image):
- Because it lacks GL_NEAREST, the Base image is also routed through the CPU _get_screen_mapped_texture() engine. Both the Base and Overlay are uploaded as massive Canvas-sized textures and drawn 1:1 on top of each other.