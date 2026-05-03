# Developer Guide: VVV Architecture

This application is an optimized medical image viewer built with Python, SimpleITK, and DearPyGui (DPG). The architecture follows an **MVC** pattern with dirty flags to ensure the GPU only updates what changed.

---

## Core Modules

### 1. Headless Backend

**Rule:** *These files must remain framework-agnostic. No DearPyGui.*

* **`config.py`:** Single source of truth for defaults (`DEFAULT_SETTINGS`, `WL_PRESETS`, `COLORMAPS`).
* **`maths/image.py`:**
    * **`VolumeData`:** Immutable source of truth for a loaded image. Manages the SimpleITK image, 4D stacking, and zero-copy NumPy array. Handles 3D spatial metadata.
    * **`SliceRenderer`:** Stateless utility. Slices 3D/4D arrays, applies W/L, blends overlays (Alpha, Registration, Checkerboard), and packs RGBA for the GPU.
* **`maths/geometry.py` (`SpatialEngine`):** The absolute source of truth for 3D coordinate mapping. Manages the base geometry (via SimpleITK) and the active extrinsic transform.
* **`maths/contours.py` (`ContourROI`):** Data container for 2D polygon sets representing anatomical structures.
* **`maths/image_utils.py`:** Helpers for orientation string extraction and metadata parsing.
* **`core/controller.py` (The Brain):** Central coordinator. Holds `ViewStates`, manages layout, and dispatches synchronization. Delegates to specialized managers.
* **`core/view_state.py` (`ViewState`, `CameraState`):** Transient UI state per image (camera, display, overlays).
* **Domain Managers (`core/`):**
    * `FileManager`: Disk I/O, DICOM parsing, Workspace serialization.
    * `SyncManager`: Cross-image spatial and radiometric synchronization.
    * `ROIManager`: Binary masks, label maps, RT-Structs, stats, and bounding-box crops.
    * `ContourManager`: Lifecycle and memory management for vector contour overlays.
    * `ExtractionManager`: Interactive threshold-based volume generation.
    * `HistoryManager`: LRU cache (100 entries) for per-file user preferences.
    * `SettingsManager`: Persistent user settings (`~/.config/vvv/.vv_settings`).

### 2. The View (`ui/`)

**Rule:** *The UI layer listens to the Controller and dispatches commands back to it.*

* **`ui/gui.py`:** Initializes DPG context, manages layout engine, runs the main render loop. Delegates to modular `ui_*.py` files.
* **`ui/viewer.py` (`ViewportMapper`, `SliceViewer`):** Single 2D viewport. Maps screen pixels to physical coordinates, manages zoom/pan, and bridges DPG's `drawlist` with `SliceRenderer`. Supports **Linear**, **Nearest Neighbor**, and **Voxel Strips** interpolation modes.
* **`ui/drawing.py` (`OverlayDrawer`):** All DPG drawing node updates (voxel grid, contour overlays), extracted to keep `SliceViewer` focused on state.
* **`ui/ui_components.py`:** Reusable DPG widget builders (section titles, stepped sliders).
* **Sidebar tab modules:**
    * `ui_sync.py`, `ui_fusion.py`, `ui_roi.py`, `ui_image_list.py`, `ui_extraction.py`, `ui_registration.py`, `ui_contours.py`, `ui_dvf.py`, `ui_intensities.py`: Build tabs and handle callbacks for their domain.
    * `ui_dicom.py` (`DicomBrowserWindow`): DICOM series browser with async folder scanning.
    * `ui_settings.py` (`SettingsWindow`): Floating settings editor.
    * `ui_theme.py`: DPG theme and font configuration.
    * `ui_notifications.py`: Popups, progress bars, and status text.
    * `ui_interaction.py` (`InteractionManager`): Mouse/keyboard event router (W/L drag, pan, zoom).
    * `ui_sequences.py`: Python generators for multi-threaded loading without blocking the render loop.
    * `file_dialog.py`: Native file dialog wrapper.

---

## Concurrency and Thread Safety

1. **UI Thread:** DearPyGui runs strictly on the main thread.
2. **Generators (`yield`):** `ui_sequences.py` yields control back to the render loop while waiting for I/O.
3. **Thread Safety:** Background threads write to `VolumeData` and set `controller.ui_needs_refresh = True`. They never call `dpg.*` directly.
4. **Dictionary Lock:** Background threads must acquire `controller.roi._lock` before mutating ROI dictionaries.

---

## Render Loop Lifecycle

1. **Input & Mutation:** Callback updates `ViewState` (e.g., `vs.display.ww`) or sets `controller.ui_needs_refresh = True`.
2. **Synchronization:** `SyncManager` propagates changes to other viewers in the same sync group.
3. **`tick()` Assessment:**
    * *`is_geometry_dirty`*: Recalculates `ViewportMapper` bounding boxes.
    * *Texture Rebuilds*: Purges old GPU textures and binds a new dynamic texture when size/orientation/interpolation changes.
    * *`is_data_dirty`*: `SliceRenderer` slices the NumPy array, applies W/L, pushes RGBA to GPU texture.
    * *`ui_needs_refresh`*: Rebuilds relevant UI panels.

---

## Spatial Nomenclature

* **Voxel** (`voxel_x/y/z`, `time_idx`): Integer NumPy indices. Used for pixel value extraction.
* **Physical** (`phys_x/y/z`): Real-world millimeter coordinates. Used for cross-image sync and overlay registration.
* **Pixel/Screen** (`pix_x/y`): Monitor coordinates. Used for mouse tracking and UI overlay drawing.
* **Slice/Image** (`slice_x/y`): Relative 2D coordinates on the currently extracted slice.
