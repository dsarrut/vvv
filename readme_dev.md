# Developer Guide: VVV Architecture

This application is an optimized medical image viewer built with Python, SimpleITK, and DearPyGui (DPG).

The architecture follows a **Model-View-Controller (MVC)** pattern. To maintain performance while handling 3D and 4D volumetric datasets, the application separates the immutable physical data from the transient UI viewing state, and uses "dirty flags" to ensure the GPU only updates what has actually changed.

---

## Core Modules Breakdown

### 1. The Headless Backend (`config.py`, `math/image.py`, `core.py`)

**Rule:** *These files must remain framework-agnostic. They do not know DearPyGui exists and handle pure data, state, and math.*

* **`config.py` (The Data Constants):** The single source of truth for hardcoded application defaults. Contains `DEFAULT_SETTINGS` (shortcuts, colors, layout), `WL_PRESETS`, and the mathematical generators for `COLORMAPS`.
* **`math/image.py` (The Pipeline):**
    * **`VolumeData`:** The immutable source of truth for a loaded image. Manages the SimpleITK image, 4D stacking (`sitk.JoinSeries`), and the zero-copy NumPy array. Stores physical metadata and handles 3D spatial math (voxels to millimeters).
    * **`SliceRenderer`:** A stateless, optimized utility. It slices 3D/4D NumPy arrays, applies Window/Level transfer functions, processes overlay blending modes (like Alpha, Registration, and Checkerboard), and packs the final 1D RGBA arrays for the GPU.
* **`core.py` (The Brain):** Manages the central `Controller` state. It holds the active `ViewStates` (camera, display settings) and orchestrates loading files, saving workspaces, and dispatching synchronization commands between viewers.
* **The Domain Managers (`core/`):** The Controller delegates heavy lifting to specialized managers:
    *   `FileManager`: Disk I/O, DICOM parsing, and Workspace serialization.
    *   `SyncManager`: Cross-image spatial and radiometric synchronization.
    *   `ROIManager`: Binarization, tight-cropping, stats math, and label map extraction.
    *   `ExtractionManager`: Interactive pixel thresholding and new volume generation.
    *   `HistoryManager`: An LRU cache (capped at 100) that remembers user preferences per file.

### 2. The View (`gui.py`, `viewer.py`, `ui/`)

**Rule:** *The UI layer listens to the Controller and dispatches commands back to it. It does not perform physical data manipulation directly.*

* **`gui.py` (The Window Manager):** Initializes the DearPyGui context, manages the global layout engine (`on_window_resize`), and runs the main render loop. It delegates tab building and specific business logic to the modular `ui_*.py` files.
* **`viewer.py` (`SliceViewer`):** Represents a single 2D viewport. It maps screen pixels to physical coordinates, manages zooming/panning math, and acts as the bridge between DearPyGui's `drawlist` and the `SliceRenderer`. It also manages the advanced rendering pipeline for interpolations: standard **Linear**, true **Nearest Neighbor** (pixelated zoom achieved by dynamically matching the GPU texture to the exact screen canvas size), and **Voxel Strips** (bypassing textures entirely to render geometric primitives at massive zoom levels).
* **The `ui/` Sub-modules:** To prevent `gui.py` from becoming a "God Object", specific domains are extracted into their own files:
    * `ui_sync.py`, `ui_fusion.py`, `ui_roi.py`, `ui_image_list.py`, `ui_extraction.py`, `ui_registration.py`: These build specific sidebar tabs and handle the callbacks for their respective inputs. Callbacks should modify the `ViewState` directly or set `controller.ui_needs_refresh = True` to trigger UI updates.
    * `ui_notifications.py`: The central hub for all popups, progress bars (`show_loading_modal`), and top-bar status text.
    * `ui_interaction.py`: Central router for mouse/keyboard events (`InteractionManager` and `NavigationTool`), translating raw inputs (like "Shift + Hover") into W/L or Pan commands.
    * `ui_sequences.py`: Python generators that handle multi-threaded loading and long UI tasks (like booting workspaces) without freezing the 60FPS render loop.

---

## Concurrency and Thread Safety
To keep the UI fluid (60 FPS) while loading large datasets, VVV uses Python Generators coupled with `concurrent.futures.ThreadPoolExecutor`.

1. **The UI Thread:** DearPyGui runs strictly on the main thread.
2. **Generators (`yield`):** Sequences in `ui_sequences.py` yield control back to the render loop, allowing the progress bar to redraw while waiting for C++ or Disk I/O.
3. **Thread Safety:** Background threads must *never* touch UI elements (like `dpg.set_value`). Instead, they write to the immutable `VolumeData` and set `controller.ui_needs_refresh = True`.
4. **The Dictionary Lock:** When mutating central Controller dictionaries (like adding a new ROI), background threads must acquire `controller.roi._lock` to prevent Python `RuntimeError: dictionary changed size during iteration` crashes in the main render loop.

---

## The Render Loop Lifecycle
When a user adjusts a slider or pans the image, the application follows a strict 3-step lifecycle to guarantee 60fps performance:

1.  **Input & Mutation:** The user interacts with a UI element. The corresponding callback in a `ui/` module or `gui.py` updates a property on the `ViewState` (e.g., `view_state.display.ww`) or sets a flag on the controller (e.g., `controller.ui_needs_refresh = True`).
2.  **Synchronization:** If a `ViewState` property was changed, the `SyncManager` may be invoked to propagate that change to other viewers in the same sync group.
3.  **The `tick()` Assessment:** During the main render loop in `gui.py`, `controller.tick()` is called. Each viewer checks its dirty flags:
    *   *If `is_geometry_dirty`:* Recalculates the ViewportMapper bounding boxes. If Nearest Neighbor interpolation is active, this also triggers a precise software-side screen mapping recalculation.
    *   *Texture Rebuilds:* If the image size, orientation, or interpolation mode changes, the viewer safely purges old GPU textures and atomically binds a newly sized dynamic texture to prevent OpenGL ghosting.
    *   *If `is_data_dirty` (or Texture Rebuilt):* Forces the `SliceRenderer` to slice the NumPy array, apply the W/L, and push the new 1D RGBA array to the active GPU texture.
    *   If `controller.ui_needs_refresh` is true, the relevant UI panels are rebuilt.

---

## Spatial Nomenclature

To prevent coordinate math bugs, this application defines spatial terms:

* **Voxel (`voxel_x`, `voxel_y`, `voxel_z`, `time_idx`):** The 3D/4D integer indices of the NumPy array (e.g., `[512, 512, 120, 0]`). Used exclusively to extract physical pixel values.
* **Physical (`phys_x`, `phys_y`, `phys_z`):** The real-world spatial coordinates in millimeters, calculated using the image's spacing and origin. Used for cross-image synchronization and overlay registration.
* **Pixel/Screen (`pix_x`, `pix_y`):** The 2D coordinates of the user's computer monitor or the application window. Strictly reserved for mouse tracking and drawing UI overlays.
* **Slice/Image (`slice_x`, `slice_y`):** The relative 2D coordinate on the currently extracted image slice.
