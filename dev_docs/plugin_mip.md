# Maximum Intensity Projection (MIP) Plugin

The **MIP Plugin** (`src/vvv/plugins/mip/`) renders 3D Maximum Intensity Projections in real time directly within VVV viewports.

---

## 1. Features & User Interactions

* **Toggle MIP Mode (Shortcut: `M`)**:
  * Switches the active viewport between standard 2D slice viewing and 3D Maximum Intensity Projection.
* **Projection Axis**:
  * Automatically matches the viewer's current orientation (Axial: $Z$-axis, Coronal: $Y$-axis, Sagittal: $X$-axis).
* **Interactive Rotation (Left / Right Arrow Keys)**:
  * Rotates the projection ray angle around the current slice plane, allowing 360-degree rotating views of complex vascular or uptake structures (e.g. angiography, PET whole-body).
* **Slab Thickness**:
  * Full-volume projection or partial sub-volume slabs (e.g. 10 mm, 25 mm thickness).
* **Depth Cueing**:
  * Exponential attenuation of distant voxels along the projection ray to provide 3D spatial depth cues.

---

## 2. File Structure

* **`plugin_mip.py`**: Plugin lifecycle entry point implementing `PluginProtocol`.
* **`ui_mip.py`**: Dear PyGui sidebar panel layout (`check_mip_mode`, rotation angle slider, slab thickness slider, depth cueing toggles).
* **`control_mip.py`**: Manages MIP state, keyboard shortcuts (`M`, arrow keys), and viewer invalidation.
* **`math_mip.py`**: Optimized projection math and JIT ray-marching kernels.
* **`test_mip.py`**: Unit tests for MIP projection math, angle rotations, and state persistence.

---

## 3. High-Performance Ray-Marching Math

Computing MIP projections on large volumetric datasets (e.g. $512 \times 512 \times 500$) requires efficient computation:

* **Numba JIT Kernel**:
  * In `math_mip.py`, ray casting and maximum-reduction loops are compiled using **Numba** to machine code for near-instant execution.
* **Pure NumPy Fallback**:
  * If Numba is not installed, a vectorized NumPy fallback executes automatically.
* **Angle Rotations**:
  * Ray angles are transformed using 2D rotation matrices applied to the in-plane axes, casting parallel rays across the rotated bounding box.

