# Development Session Notes

Cross-session memory consolidated from Claude Code auto-memory.

---

## Registration Live-Preview System

A multi-session refactor of the registration ("reg") tool that added a live preview mode.

### Key architecture

- `ViewState._preview_R`, `_preview_center` — shared rotation state (on Model); set by preview worker, cleared by `reset_preview_rotation()`
- `Viewer._preview_slices`, `_overlay_preview_slices` — per-viewer render caches (on View); atomically replaced by preview worker
- `RegistrationUI._preview_worker_loop` — single persistent worker thread; drains a `queue.Queue` so only the latest request is processed
- `RegistrationUI._preview_version` + lock — version counter to discard stale worker results
- `Controller.resample_image` — spawns a new thread per resample; uses `_active_resample_job` for discard detection
- `ViewState._active_resample_job` — 0=idle, N=job N running; set to 0 by `update_transform_manual` to mark in-flight resamples as unproductive

### Ghost image fixes applied (may need more work)

- Preview worker signals via `vs.is_data_dirty = True` (not direct `v.is_viewer_data_dirty`) so renders only fire through the tick, preventing races
- Viewer caches NOT cleared on slider change — old preview persists until worker atomically replaces; avoids cache-miss fallback to `base_display_data`
- `_package_base_layer`: uses `vol.data` (not `base_display_data`) when `_preview_R is not None` — prevents stale rotation ghost on cache miss
- `_package_overlay_layer`: returns None (no overlay) on cache miss when `_preview_R is not None` — prevents wrong-rotation overlay ghost in fusion
- `update_overlay_display_data`: late-tombstone pattern — old `overlay_data` stays valid during Execute() (GIL release); replaced atomically after compute
- `Controller.resample_image._do()`: two-stage job ID check — before overlay resampling (early exit if discarded during base) and after

### Known remaining issue

Ghost images in fusion mode still appear occasionally, especially with auto-update + rapid slider changes. The root cause is complex threading interactions between the preview worker, resample thread, and DPG render/tick threads.

**Auto-update mode:** `check_reg_auto_resample` checkbox; fires `trigger_resample` 0.7s after last slider change via `threading.Timer` debounce.

---

## Architecture Refactor — viewer.py / gui.py / controller.py (May 2026)

Simplification pass on the 3 largest files. Net: **−108 lines** in the target files.

### Done

- Fixed architecture violation: `controller.update_setting()` no longer calls GUI directly; uses `ui_needs_layout_rebuild` flag consumed in `_refresh_all_ui_panels()`
- Restored `update_crosshair_from_slice()` as a public no-op (test API)
- Extracted `_configure_image_display()` from `update_stuff_in_image_only()` in viewer.py
- Extracted `_apply_camera_sync()` from `tick()` in viewer.py
- Added shared `format_pixel_value(val, vol, time_idx)` in `utils.py` — used by both viewer.py and gui.py (was duplicated in 4 places)
- Replaced 9 individual toggle action methods with 1 `_toggle_camera_bool(field)` + lambdas in dispatcher
- Added `_get_window_dims()` helper replacing 5 repeated `dpg.get_item_width/height` patterns
- Consolidated 3 inline viewport-padding calc sites to use existing `_get_canvas_size()`
- Extracted `_flag_viewers_for_image(vs_id, data_dirty, geometry_dirty)` in controller.py (replaced 3 identical loops)
- Added `vs.mark_both_dirty()` on ViewState (replaced 4+ paired `is_data/is_geometry = True` sets)
- Removed 4 sync manager thin wrappers from Controller; callers now use `controller.sync.*` directly
- Removed 3 GUI passthrough dispatchers (`highlight_active_image_in_list`, `refresh_image_list_ui`, `refresh_sync_ui`)
- Added `_rendering_cfg`, `_interaction_cfg`, `_physics_cfg` property shortcuts on SliceViewer

### Still open

- `RenderState` dataclass to consolidate 6 `last_*` tracking fields in viewer.py
- Move Transform I/O out of Controller into FileManager
- Move `pan_viewers_by_delta()` to SliceViewer
- Larger `tick()` decomposition beyond `_apply_camera_sync()`

---

## Working Preferences

- Pragmatic stopping points are fine — "I stop here" after several iterations on a hard threading problem is acceptable. When a complex concurrency issue remains after several targeted fixes, present the current state clearly and let the user decide whether to continue.
