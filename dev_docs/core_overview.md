# VVV Architecture Overview

Python + SimpleITK + DearPyGui (DPG) medical image viewer. Uses an MVC pattern with strict dirty-flag reactive rendering.

## Core Modules

### 1. Headless Backend (No DPG imports)
* **`VolumeData`** (`maths/image.py`): 3D/4D SimpleITK image and NumPy array, source of truth. Replaced (not edited in place) on reload, bake and save, on the main thread.
* **`SliceRenderer`**: Slices arrays, applies W/L, and blends overlays.
* **`SpatialEngine`**: 3D coordinate mapping and extrinsic transforms.
* **`Controller`**: State bridge. Holds `ViewStates`, `volumes`, and sub-managers (`FileManager`, `SyncManager`, `ROIManager`, etc.).
* **`ViewState`**: Transient display/camera parameters per image.

### 2. View Layer (`ui/`)
* **`MainGUI`**: DPG context, layout calculation, and main loop (`run()`).
* **`SliceViewer`**: Autonomous 2D viewport. Calculates pmin/pmax mapped bounds, generates texture arrays, and pushes to GPU.
* **`OverlayDrawer`**: DPG vector drawing (crosshairs, scalebar, contour ROIs, vector fields).
* **`ui_*.py`**: Shared layout managers, configurations, and core UI bindings.
* **Plugins (`plugins/`)**: Most feature-specific tools (Intensities, ROI, DVF, Contours, Registration, etc.) are implemented as modular, auto-discovered plugins under `src/vvv/plugins/`. For guidelines, see [plugin_architecture.md](plugin_architecture.md).

## Concurrency and Thread Safety

- **Main Thread**: Exclusive owner of DPG calls.
- **Generators**: `ui_sequences.py` yields during loading to keep the UI responsive.
- **Background Threads**: Compute only (file reading, ITK resampling), from inputs captured on the main thread; they never modify shared state.
- **Commits**: results are applied on the main thread, via `controller.call_on_main(fn)` (run by `Controller.tick()`). Per-image jobs (resample, bake) use a `JobRunner`: one worker per image, only the latest job kept, a stale result is discarded (`job.is_current()`).
- **Loading**: files are read in a thread pool and registered on the main thread (`file_manager.read_image` → `register_image`, `roi_manager.register_roi`).

## Render Loop Lifecycle

1. **Event**: Updates `ViewState` properties or flags.
2. **Sync**: `SyncManager` propagates cross-viewer target state.
3. **`tick()`**: each frame, `Controller.tick()` applies the pending main-thread commits, passes the `ViewState` dirty flags to the viewers, then each `SliceViewer.tick()` consumes the state.
    * `is_geometry_dirty`: Update 2D bounding boxes and DPG pan/zoom values.
    * `is_data_dirty`: Extract slice, apply W/L, push RGBA to GPU.

## Spatial Nomenclature

* **Voxel**: Integer NumPy array indices (`[Z, Y, X]`).
* **Physical**: Real-world millimeter coordinates used for sync and registration.
* **Pixel**: Monitor space used for mouse tracking.
