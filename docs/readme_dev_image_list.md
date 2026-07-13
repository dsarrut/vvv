# Image List Tool

The Image List tool manages and displays all loaded images (volumes) within the sidebar of the VVV interface. It provides controls to rename, view, save, reload, close, and navigate 4D timepoints for each image.

## Features

- **Viewport Assignment**: Matrix of checkboxes allowing quick mapping of each loaded image to any of the 4 layout viewports (`V1` to `V4`).
- **In-place Rename**: An input field allowing developers/users to rename the volume. It handles committing on enter key or on focus loss (deactivation).
- **Global Viewer Controls**:
  - **Show in All**: Sets the image to all 4 viewports.
  - **Save**: Triggers file save callbacks.
  - **Reload**: Reloads the volume from disk.
  - **Close**: Safely closes the volume and removes it from the controller.
- **4D Slider**: Automatically appears for 4D datasets, enabling scrubbing through timepoints.

---

## Architecture & Lifecycle

The tool is implemented in [ui_image_list.py](../src/vvv/ui/ui_image_list.py) and adheres to the following principles:

### 1. Reactive Refresh Only
To avoid CPU overhead from constantly recreating DearPyGui widgets:
- Slower operations (like adding or deleting images, changing layouts) trigger a full rebuild of the image list container via `refresh_image_list_ui(gui)`.
- Rebuilding is driven by the `gui.controller.ui_needs_refresh` flag inside the main loop.

### 2. State-Driven Construction
During a refresh cycle:
- Slices, labels, and viewer assignments are read directly from the backend `Controller` and `ViewState` data.
- UI elements do not hold persistent state; the backend is the single source of truth.

### 3. Lightweight Frame Synchronization
To keep the UI responsive during continuous interactions (such as dragging the time slider or editing names):
- `sync_image_list_ui(gui)` runs in the main render loop (`tick`).
- It checks if DPG elements (like the slider or text fields) differ from their corresponding backend properties and updates only those specific values without destroying/re-creating widgets.

### 4. Event & Thread Safety
- All UI construction and callbacks are bound to the main thread.
- Rename events trigger an asynchronous update: renaming the volume, updating viewer text overlays, and marking the UI as dirty for the next tick.
