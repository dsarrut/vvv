# Developer Guide: Synchronization Tool

## 1. Overview
The `SyncManager` is responsible for broadcasting camera geometry (Zoom, Pan, Slice Depth) and radiometric properties (Window/Level, Colormaps) across multiple Viewers.

It operates on a "Group ID" paradigm.
* **Group `0` (None):** The image is isolated and ignores all incoming broadcasts.
* **Groups `1+`:** Any change made to one image in the group is instantly broadcast to all others in the same group.

## 2. Core Mechanics
* **`SyncManager` (`core/sync_manager.py`):** Contains the actual broadcasting math (`propagate_sync`, `propagate_window_level`).
* **`ui_sync.py`:** Generates the matrix table UI. 

### The Broadcasting Flow
1. The user pans Image A (Group 1).
2. `SliceViewer.on_drag` is triggered. The viewer updates its local `pan_offset` and calls `controller.sync.propagate_sync(self.image_id)`.
3. The `SyncManager` calculates the absolute physical World Coordinate of Image A's crosshair (`display_to_world`).
4. The `SyncManager` iterates over all other ViewStates in Group 1.
5. It sets their `vs.camera.target_center = world_coord`.
6. On the next render frame (`tick()`), the target viewers realize they are out of alignment with `target_center` and autonomously calculate the math required to pan/shift their viewports to match.

## 3. Important Gotchas
* **Infinite Recursion Lock:** The `SyncManager` has a built-in `_is_syncing` threading lock. If Image A updates Image B, Image B will try to update Image A. The lock instantly kills the feedback loop.
* **Pixels Per Millimeter (PPM):** To ensure that two images with completely different physical spacings zoom at the exact same physical scale on the screen, VVV synchronizes their `pixels_per_mm`.
* **Early Returns:** `ui_sync.py` implements strict early returns. If a user clicks "Group 1" while already in "Group 1", the UI ignores it. If it didn't, the floating-point rounding errors caused by converting `PPM -> Zoom -> PPM` would cause the image to slightly "snap" or drift across the screen.
* **Radiometric Overlays:** When `propagate_window_level` is called, it intentionally ignores the target Viewer's `is_rgb` status. This is because even if the target Base image is RGB (and can't use W/L), the target Viewer might have a grayscale *Overlay* loaded that needs the Window/Level sync applied to it!