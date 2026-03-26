# Developer Guide: VVV Architecture

This application is a highly optimized medical image viewer built with Python, SimpleITK, and DearPyGui (DPG).

The architecture follows a strict **Model-View-Controller (MVC)** pattern. To maintain peak performance while handling massive 3D and 4D volumetric datasets, the application separates the heavy immutable physical data from the transient UI viewing state, and uses "dirty flags" to ensure the GPU only updates what has actually changed.

---

## Core Modules Breakdown

### 1. The Headless Backend (`config.py`, `image.py`, `core.py`)

**Rule:** *These files must remain completely framework-agnostic. They do not know DearPyGui exists and handle pure data, state, and math.*

* **`config.py` (The Data Constants):** The single source of truth for hardcoded application defaults. Contains `DEFAULT_SETTINGS` (shortcuts, colors, layout), `WL_PRESETS`, and the mathematical generators for `COLORMAPS`.
* **`image.py` (The Pipeline):** * **`VolumeData`:** The immutable source of truth for a loaded image. Manages the SimpleITK image, 4D stacking (`sitk.JoinSeries`), and the zero-copy NumPy array. Stores physical metadata and handles 3D spatial math (voxels to millimeters).
    * **`SliceRenderer`:** A stateless, highly-optimized utility. It slices 3D/4D NumPy arrays, applies Window/Level transfer functions, processes Complementary Color Registration math, Checkerboard modes, and packs the final 1D RGBA arrays for the GPU.
* **`core.py` (The Brain):** Manages the central `Controller` state. It holds the active `ViewStates` (camera, display settings) and orchestrates loading files, saving workspaces, and dispatching synchronization commands between viewers.

### 2. The View (`gui.py`, `viewer.py`, `ui/`)

**Rule:** *The UI layer listens to the Controller and dispatches commands back to it. It does not perform physical data manipulation directly.*

* **`gui.py` (The Window Manager):** Initializes the DearPyGui context, manages the global layout engine (`on_window_resize`), and runs the main render loop. It delegates tab building and specific business logic to the modular `ui_*.py` files.
* **`viewer.py` (`SliceViewer`):** Represents a single 2D viewport. It maps screen pixels to physical coordinates, manages zooming/panning math, and acts as the bridge between DearPyGui's `drawlist` and the `SliceRenderer`.
* **The `ui/` Sub-modules:** To prevent `gui.py` from becoming a "God Object", specific domains are extracted into their own files:
    * `ui_sync.py`, `ui_fusion.py`, `ui_roi.py`, `ui_image_list.py`: These build specific sidebar tabs and handle the callbacks for their respective inputs.
    * `ui_notifications.py`: The central hub for all popups, progress bars (`show_loading_modal`), and top-bar status text.
    * `ui_interaction.py`: Central router for mouse/keyboard events (`InteractionManager` and `NavigationTool`), translating raw inputs (like "Shift + Hover") into W/L or Pan commands.

---

## The Render Loop Lifecycle
When a user adjusts a slider or pans the image, the application follows a strict 3-step lifecycle to guarantee 60fps performance:

1. **Input & Mutation:** The user interacts with the UI (e.g., changes Window/Level via Shift+Hover). The `InteractionManager` updates the `ViewState.display.ww` value and flags `view_state.is_data_dirty = True`.
2. **Synchronization:** The Controller's `SyncManager` is notified. It loops through all `SliceViewers` in the same Sync Group and applies the new W/L values, flagging them all as dirty.
3. **The `tick()` Assessment:** During the main render loop in `gui.py`, `controller.tick()` is called. Each viewer checks its dirty flags:
    * *If `is_geometry_dirty`:* Recalculates the ViewportMapper bounding boxes.
    * *If `is_data_dirty`:* Forces the `SliceRenderer` to slice the NumPy array, apply the W/L, and push the new 1D RGBA array to the GPU texture registry.

---

## Spatial Nomenclature

To prevent coordinate math bugs, this application strictly defines spatial terms:

* **Voxel (`voxel_x`, `voxel_y`, `voxel_z`, `time_idx`):** The 3D/4D integer indices of the NumPy array (e.g., `[512, 512, 120, 0]`). Used exclusively to extract physical pixel values.
* **Physical (`phys_x`, `phys_y`, `phys_z`):** The real-world spatial coordinates in millimeters, calculated using the image's spacing and origin. Used for cross-image synchronization and overlay registration.
* **Pixel/Screen (`pix_x`, `pix_y`):** The 2D coordinates of the user's computer monitor or the application window. Strictly reserved for mouse tracking and drawing UI overlays.
* **Slice/Image (`slice_x`, `slice_y`):** The relative 2D coordinate on the currently extracted image slice.