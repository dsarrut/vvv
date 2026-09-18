# Synchronization Tool
# Viewport Synchronization Engine

Broadcasts properties across multiple viewers via `core/sync_manager.py`.
This document details VVV's multi-viewer synchronization system managed by `SyncManager` (`src/vvv/core/sync_manager.py`).

* **Groups**: `0` = Isolated. `1+` = Synchronized.
* **Camera Sync**: Pushes `target_center` (physical world coords) and `target_ppm` to synced `ViewState`s.
* **Data Sync**: Radiometrics (W/L, colormaps), Time/Component Index.
* **Safety**:
  * `_is_syncing` lock prevents A→B→A infinite recursion feedback loops.
  * Zoom is synced via PPM (Pixels Per Millimeter) to ensure uniform physical scale regardless of differing voxel geometries.
  * Crosshair position sync is achieved by locking physical coordinates (not voxel slice indices).
---

## 1. Overview & Sync Groups

VVV supports simultaneous display of multiple images across independent viewports (e.g. Axial, Coronal, Sagittal, or side-by-side comparative views). Synchronization coordinates spatial navigation, radiometrics, and temporal scrubbers across linked images.

### Group Model
* **Group `0`**: **Isolated / Unlinked**. Changes to camera, crosshair, or window/level affect only this image.
* **Group `1`, `2`, `...`**: **Synchronized Group**. Any state change in one group member is automatically broadcast to all active members of the same group.
* **Separate Spatial vs. Radiometric Groups**:
  * `sync_group`: Controls spatial/camera navigation (crosshair, slices, zoom).
  * `sync_wl_group`: Controls radiometric properties (Window Width, Window Level, Colormap, Minimum Threshold).

---

## 2. Spatial & Camera Synchronization

### Physical Coordinate Anchoring
Synchronization is strictly performed in **physical real-world millimeter space** ($[x, y, z]$ in mm), **not voxel index space**.

1. **Crosshair & Slices**:
   * Moving the crosshair or scrolling slices updates `source_vs.camera.crosshair_phys_coord`.
   * `SyncManager.propagate_sync(source_vs_id)` converts this physical coordinate into each target image's display coordinate space:
     ```python
     target_voxel = target_vs.world_to_display(crosshair_phys_coord)
     ```
   * Taking extrinsic registration transforms into account, target viewers automatically navigate to the slice intersecting that exact anatomical location.

2. **Optical Scale (Pixels Per Millimeter - PPM)**:
   * Images in medical imaging often have vastly different voxel resolutions (e.g. $0.5 \text{ mm}$ CT vs. $3.0 \text{ mm}$ PET).
   * Synchronizing raw zoom levels or voxel counts would cause misaligned anatomical scales.
   * VVV synchronizes **PPM (Pixels Per Millimeter)**:
     ```python
     target_vs.camera.target_ppm = source_vs.camera.target_ppm
     ```
   * Result: A $5 \text{ cm}$ tumor appears at the exact same physical size on screen across all synchronized viewports.

---

## 3. Radiometric Synchronization

Managed by `propagate_window_level()` and `propagate_colormap()`:

* **Window / Level**: Broadcasts `DisplayState.ww` and `DisplayState.wl` across `sync_wl_group` members.
* **Minimum Thresholding**: Propagates `DisplayState.min_threshold` so noise/air cutoff is applied uniformly across comparative views.
* **Colormap**: Ensures comparative or fused viewports share the same colormap palette.

---

## 4. Temporal Synchronization (4D Sequences)

Managed by `propagate_time_idx(source_vs_id)`:
* When scrubbing through a 4D time series or multi-phase acquisition, changing `time_idx` broadcasts the new timepoint to all synced 4D volumes.
* **Safety Clamping**: Clamped to `target_vs.volume.num_timepoints - 1` to prevent index out-of-range errors when comparing datasets with differing phase counts.

---

## 5. Composite Overlay-Base Dependency Tracking

When fusion overlays are displayed:
* `SyncManager.rebuild_overlay_base_map()` maintains a reverse lookup mapping `overlay_id -> list of base_ids`.
* When an overlay's W/L, colormap, or threshold is modified, all base viewers displaying that overlay are automatically flagged `is_data_dirty = True`.
* Ensures composite slices re-blend and refresh immediately without manual user intervention.

---

## 6. Recursion & Loop Prevention

To prevent infinite $A \to B \to A$ feedback loops:
* Propagation calls are directional and state-guarded: `SyncManager` skips propagating back to `source_vs_id`.
* Property setters in `ViewState` check for actual value changes (`abs(old - new) > epsilon`) before flagging dirty states.
