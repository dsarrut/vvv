# Developer Guide: Registration Tool

## 1. Features & Capabilities

- **Straighten on Load:** Detects and resamples oblique/tilted images to an identity direction matrix, ensuring fast 2D slicing.
- **Metadata Preservation:** Captures the original Direction Matrix before straightening for UI display and script export.
- **Extrinsic Rigid Registration:** 6-DOF manual transform (Tx, Ty, Tz, Rx, Ry, Rz) applied on top of the straightened physical space.
- **Dynamic Pivot (CoR):** Snap the Center of Rotation to any crosshair pixel; a compensating translation prevents visual jumping.
- **Robust Transform I/O:** Reads/writes `.tfm`, `.mat`, `.txt`. Applies SVD to correct rounding errors in imported rotation matrices.
- **World-Fixed Anchoring:** Adjusting rigid parameters automatically calculates the camera pan/slice shift to keep the crosshair pinned to the same anatomical point.
- **Debounced Updates:** A 0.3s background thread debouncer (`trigger_debounced_rotation_update`) keeps the render loop at 60fps during slider dragging.

## 2. Limitations

- **Quantitative Data Loss:** "Straighten on Load" interpolates oblique images. Raw voxel values are altered.
- **Rigid-Only:** Only `Euler3DTransform` is supported. No automated or deformable registration.
- **Fixed Camera Plane:** The camera is always locked to the orthogonal axes of the base image (no oblique slicer).

## 3. Code Structure

- **`VolumeData`:** Disk I/O, metadata, oblique straightening, and immutable pixel storage.
- **`SpatialEngine` (`maths/geometry.py`):** Source of truth for 3D coordinate mapping. Manages the extrinsic `Euler3DTransform` as a pure math overlay over the straightened space.
- **`ViewState` (`core/view_state.py`):** Owns `update_base_display_data`, triggering the heavy ITK 3D resampler only when math needs to be baked into 2D display arrays.
- **`ui_registration.py`:** Handles callbacks, debouncing, and file parsing. Follows strict UI mandates:
    - **Reactive Refresh Only:** Sets `controller.ui_needs_refresh = True`; never imperatively updates widgets.
    - **State-Driven Building:** Sliders always pull `default_value` from `SpatialEngine`'s transform matrix.
    - **Thread Safety:** ITK resampling runs off the main thread; results are communicated via status flags.
