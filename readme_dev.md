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

* **`core.py` (The Brain):**
    * **`Controller`:** Acts as the central nervous system. Maintains the dictionaries of all loaded datasets and viewports. Handles complex cross-viewer synchronization (e.g., forcing Window/Level parity during image registration).
    * **`ViewState`:** Stores all transient viewing parameters tied to a specific image (W/L, camera zoom/pan, current slice depths, time index, visibility toggles).
    * **`SettingsManager`:** Reads/writes user preferences to the OS-specific `.vv_settings` JSON file.

### 2. The Frontend (`gui.py`, `settings_ui.py`)

**Rule:** *These files handle the global application layout, sidebars, menus, and user inputs.*

* **`MainGUI` (`gui.py`):** Builds the static DPG layout (menus, sidebars, viewer quadrants). It routes global mouse/keyboard events to the currently active viewport, and manages the main application `run()` loop.
* **`SettingsWindow` (`settings_ui.py`):** A dynamic, non-modal floating window. It uses a recursive "JSON-like" tree builder to automatically generate UI sliders and color pickers directly from the `DEFAULT_SETTINGS` dictionary, requiring zero hardcoded layout logic.

### 3. The Viewport (`viewer.py`, `drawing.py`)

**Rule:** *These files bridge the physical 3D/4D data to the 2D screen.*

* **`SliceViewer` (`viewer.py`):** Represents a single viewport (e.g., "V1"). It pulls physical data from `VolumeData` and UI parameters from `ViewState`. It manages a dynamic shortcut dispatcher and handles mouse drag/scroll events.
* **`OverlayDrawer` (`drawing.py`):** An isolated utility class that contains all raw DearPyGui drawing node commands. It calculates the geometries and draws the Crosshairs, Scale Bars, Legends, Voxel Grids, and Histograms without cluttering the viewer logic.
* **`ViewportMapper` (`viewer.py`):** A pure-math helper class. Calculates 2D screen bounds, zoom offsets, and translates raw mouse screen pixels into relative 2D image coordinates.

### 4. Utilities & Entry

* **`utils.py`:** Contains the `ViewMode` Enum (`AXIAL`, `SAGITTAL`, `CORONAL`, `HISTOGRAM`). Using this Enum prevents silent failures caused by mistyped magic strings.
* **`cli.py`:** The entry point. Initializes the DPG context, parses command-line arguments (including smart grouping for shell-expanded 4D wildcards and fusion parameters), and bootstraps the application.

---

## The Render Loop & "Dirty" Flags

Because DearPyGui operates as a retained-mode wrapper over an immediate-mode backend, pushing full-resolution RGBA numpy arrays to the GPU 60 times a second will bottleneck the CPU. We bypass this using two specific flags checked in `gui.py`'s `run()` loop:

1.  **`is_geometry_dirty`:** * *Scope:* Local (`SliceViewer`)
    * *Triggered by:* Pan, Zoom, Window Resize.
    * *Action:* Recalculates the 2D bounding box (`pmin`, `pmax`) to stretch or move the existing GPU texture. It does *not* slice the 3D array again.

2. **`is_data_dirty`:**
    * *Scope:* Global (`ViewState`)
    * *Triggered by:* Scrolling to a new slice, changing time index, changing Window/Level, toggling grids/axes.
    * *Action:* Forces the `SliceRenderer` to slice the NumPy array, apply the W/L, and push the new 1D RGBA array to the GPU texture registry.

---

## Spatial Nomenclature

To prevent coordinate math bugs, this application strictly defines spatial terms:

* **Voxel (`voxel_x`, `voxel_y`, `voxel_z`, `time_idx`):** The 3D/4D integer indices of the NumPy array (e.g., `[512, 512, 120, 0]`). Used exclusively to extract physical pixel values.
* **Physical (`phys_x`, `phys_y`, `phys_z`):** The real-world spatial coordinates in millimeters, calculated using the image's spacing and origin. Used for cross-image synchronization and overlay registration.
* **Pixel/Screen (`pix_x`, `pix_y`):** The 2D coordinates of the user's computer monitor or the application window. Strictly reserved for mouse tracking and drawing UI overlays.
* **Slice/Image (`slice_x`, `slice_y`):** The relative 2D coordinate on the currently extracted image slice.

---

## Adding New Features
* **Adding a UI Setting:** Add the default value to `config.py`. It will magically appear in the Settings UI!
* **Adding a Keyboard Shortcut:** Add the keybinding to `config.py` and register the action in `SliceViewer._init_shortcut_dispatcher()`.
* **Adding a Math Filter:** Add the calculation to `VolumeData` in `image.py`, and set `view_state.is_data_dirty = True`.
* **Adding a Custom Overlay (e.g., ROI drawing):** Add the drawing logic to `OverlayDrawer` in `drawing.py` using DPG's `draw_line`/`draw_polygon` methods.