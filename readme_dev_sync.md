# Synchronization Tool

Broadcasts properties across multiple viewers via `core/sync_manager.py`.

* **Groups**: `0` = Isolated. `1+` = Synchronized.
* **Camera Sync**: Pushes `target_center` (physical world coords) and `target_ppm` to synced `ViewState`s.
* **Data Sync**: Radiometrics (W/L, colormaps), Time/Component Index.
* **Safety**:
  * `_is_syncing` lock prevents A→B→A infinite recursion feedback loops.
  * Zoom is synced via PPM (Pixels Per Millimeter) to ensure uniform physical scale regardless of differing voxel geometries.
  * Crosshair position sync is achieved by locking physical coordinates (not voxel slice indices).
