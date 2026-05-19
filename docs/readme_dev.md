# VVV Architecture Overview

Python + SimpleITK + DearPyGui (DPG) medical image viewer. Uses an MVC pattern with strict dirty-flag reactive rendering.

## Core Modules

### 1. Headless Backend (No DPG imports)
* **`VolumeData`**: Immutable 3D/4D SimpleITK image and NumPy array source of truth.
* **`SliceRenderer`**: Slices arrays, applies W/L, and blends overlays.
* **`SpatialEngine`**: 3D coordinate mapping and extrinsic transforms.
* **`Controller`**: State bridge. Holds `ViewStates`, `volumes`, and sub-managers (`FileManager`, `SyncManager`, `ROIManager`, etc.).
* **`ViewState`**: Transient display/camera parameters per image.

### 2. View Layer (`ui/`)
* **`MainGUI`**: DPG context, layout calculation, and render loop (`tick()`).
* **`SliceViewer`**: Autonomous 2D viewport. Calculates pmin/pmax mapped bounds, generates texture arrays, and pushes to GPU.
* **`OverlayDrawer`**: DPG vector drawing (crosshairs, scalebar, contour ROIs, vector fields).
* **`ui_*.py`**: Tab builders and event callbacks. Callbacks update `ViewState` or set `controller.ui_needs_refresh = True`.

## Concurrency and Thread Safety

- **Main Thread**: Exclusive owner of DPG calls.
- **Generators**: `ui_sequences.py` yields during loading to keep the UI responsive.
- **Background Threads**: Mutate data (e.g. ITK resampling) and set `controller.ui_needs_refresh`.

## Render Loop Lifecycle

1. **Event**: Updates `ViewState` properties or flags.
2. **Sync**: `SyncManager` propagates cross-viewer target state.
3. **`tick()`**: Viewers consume state.
    * `is_geometry_dirty`: Update 2D bounding boxes and DPG pan/zoom values.
    * `is_data_dirty`: Extract slice, apply W/L, push RGBA to GPU.

## Spatial Nomenclature

* **Voxel**: Integer NumPy array indices (`[Z, Y, X]`).
* **Physical**: Real-world millimeter coordinates used for sync and registration.
* **Pixel**: Monitor space used for mouse tracking.
