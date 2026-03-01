# Developer Guide: VVV Architecture

This application is a medical image viewer built with Python, SimpleITK, and DearPyGui (DPG). 

The architecture follows a **Model-View-Controller (MVC)** pattern. To maintain performance while handling 3D volumetric datasets, the application separates 3D math from 2D screen rendering, and uses "dirty flags" to ensure DearPyGui only updates what has actually changed.

---

## Core Modules Breakdown

### 1. `core.py` (The Model & Controller)

**Rule:** *This file must remain completely framework-agnostic. It does not know DearPyGui exists.*

* **`ImageModel` (The Data):** Holds the source of truth for a loaded image. 
    * Manages the SimpleITK image and the zero-copy numpy array (`self.data`).
    * Handles 3D spatial math (mapping 3D voxels to physical millimeters).
    * Stores image-specific display states (Window/Level, current slice depths, zoom).
    * *Dirty Flag:* `is_data_dirty` (True when pixel data or W/L changes).


* **`Controller` (The Manager):** Acts as the central nervous system.
    * Maintains the dictionaries of all loaded `ImageModel`s and `SliceViewer`s.
    * Handles cross-viewer synchronization (`sync_group`) to ensure different views of the same physical space stay aligned.
    * Exposes backend methods (loading images, updating settings) that the GUI can call.

### 2. `gui.py` (The Global View & Input Router)

**Rule:** *This file handles everything the user touches or sees outside of the image itself.*

* **`MainGUI`:** Builds the static DPG layout (menus, sidebars, viewer quadrants).

 
* **Event Routing:** Receives global mouse and keyboard events from DPG, calculates which viewer the mouse is currently over (`self.hovered_viewer`), and delegates the event to that specific viewer. 
 
 
* **The Render Loop (`run()`):** The beating heart of the application. It runs every frame, checking the "dirty flags" of the models and viewers to determine if a texture needs to be recalculated or a UI element needs to be synced.

### 3. `viewer.py` (The Local Viewport)
**Rule:** *This file bridges the 3D data and the 2D screen.*

* **`SliceViewer`:** Represents a single viewport (e.g., "V1"). 
    * Manages DPG dynamic textures and drawlists (crosshairs, grids, text overlays).
    * *Dirty Flag:* `is_geometry_dirty` (True when the camera pans, zooms, or the window resizes).
 
 
* **`ViewportMapper`:** A pure-math helper class. 
    * Calculates 2D screen bounds, zoom offsets, and translates raw mouse screen pixels into relative 2D image coordinates. It keeps the messy screen-scaling math out of the main viewer logic.

### 4. Helpers & Entry
 
* **`utils.py`:** Contains the `ViewMode` Enum (`AXIAL`, `SAGITTAL`, `CORONAL`, `HISTOGRAM`). Using this Enum prevents silent failures caused by mistyped magic strings.
 
 
* **`cli.py`:** The entry point. Initializes the DPG context, wires the `Controller` to the `MainGUI`, parses command-line arguments, and starts the render loop.

---

## The Render Loop & "Dirty" Flags

Because DearPyGui operates as a retained-mode wrapper over an immediate-mode backend, pushing full-resolution RGBA numpy arrays to the GPU 60 times a second will bottleneck the CPU. We bypass this using two specific flags checked in `gui.py`'s `run()` loop:

1.  **`is_geometry_dirty`:** * *Scope:* Local (`SliceViewer`)
    * *Triggered by:* Pan, Zoom, Window Resize.
    * *Action:* Recalculates the 2D bounding box (`pmin`, `pmax`) to stretch or move the existing GPU texture. It does *not* slice the 3D array again. 
2. **`is_data_dirty`:**
    * *Scope:* Global (`ImageModel`)
    * *Triggered by:* Scrolling to a new slice, changing Window/Level, toggling grids/axes.
    * *Action:* Forces `get_slice_rgba()` to slice the 3D numpy array, apply the Window/Level transfer function, and push the new 1D RGBA array to the GPU texture registry.

---

## Spatial Nomenclature

To prevent coordinate math bugs, this application defines spatial terms:

* **Voxel (`voxel_x`, `voxel_y`, `voxel_z`):** The 3D integer indices of the numpy array (e.g., `[512, 512, 120]`). Used to extract pixel values.
* **Physical (`phys_x`, `phys_y`, `phys_z`):** The real-world coordinates in millimeters, calculated using the image's spacing and origin. Used for cross-image synchronization and annotations.
* **Pixel/Screen (`pix_x`, `pix_y`):** The 2D coordinates of the user's computer monitor or the application window. Strictly reserved for mouse tracking and UI drawing. 
* **Slice/Image (`slice_x`, `slice_y`):** The relative 2D coordinate on the currently extracted image slice. 

---

## Adding New Features
* **Adding a UI Button:** Add it to `gui.py`. If it changes data, bind its callback to a new method in `core.py`.
* **Adding a Math Filter:** Add the calculation to `ImageModel` in `core.py`, and set `self.is_data_dirty = True`.
* **Adding a Custom Overlay (e.g., ROI drawing):** Add the drawing logic to `SliceViewer` in `viewer.py` using DPG's `draw_node` and `draw_line`/`draw_polygon` methods.  
