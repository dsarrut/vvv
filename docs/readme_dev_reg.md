# Registration Tool

Manages manual 6-DOF extrinsic rigid transforms (`Euler3DTransform`).

* **Straighten on Load**: Oblique images are resampled to an identity matrix on load for fast slicing.
* **Transform I/O**: Reads/writes `.tfm`, `.mat`, `.txt`. Validates SVD for imported rotation matrices.

## The "Pin Model" Architecture
* **Phase 1 (Live Preview)**: Dragging a slider updates the transform but leaves the camera pan/zoom fixed. The image shifts under the crosshair. Rotation invokes a fast Numba affine projection (`_is_interactive_rotation = True`).
* **Phase 2 (Quality)**: After 300ms of inactivity, `trigger_debounced_rotation_update()` runs a full ITK `ResampleImageFilter` in a background thread.
* **Phase 3 (Bake)**: Applies the transform to `VolumeData.data` permanently and resets the transform state to identity.
