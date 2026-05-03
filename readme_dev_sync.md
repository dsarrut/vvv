# Developer Guide: Synchronization Tool

## 1. Overview
The `SyncManager` (`core/sync_manager.py`) broadcasts camera geometry (Zoom, Pan, Slice Depth) and radiometric properties (W/L, Colormaps) across multiple viewers using a **Group ID** paradigm.

* **Group `0` (None):** Image is isolated; ignores all broadcasts.
* **Groups `1+`:** Any change is instantly broadcast to all images in the same group.

The matrix table UI is built in `ui_sync.py`.

## 2. Broadcasting Flow
1. User pans Image A (Group 1) → `SliceViewer.on_drag` calls `controller.sync.propagate_sync(image_id)`.
2. `SyncManager` calculates the physical world coordinate of Image A's crosshair.
3. Sets `vs.camera.target_center = world_coord` for all other ViewStates in Group 1.
4. On the next `tick()`, target viewers autonomously calculate the pan/shift required to match.

## 3. Important Details
* **Infinite Recursion Lock:** `_is_syncing` threading lock prevents A→B→A feedback loops.
* **Pixels Per Millimeter (PPM):** Zoom is synchronized via PPM so images with different spacings appear at the same physical scale on screen.
* **Early Returns:** `ui_sync.py` ignores no-op group clicks. Without this, `PPM → Zoom → PPM` floating-point rounding would cause subtle image drift.
* **Radiometric Overlays:** `propagate_window_level` intentionally ignores the target's `is_rgb` status — the target may have a grayscale overlay that still needs W/L sync.
