# Development Session History

* **Registration Live-Preview Refactor**:
  * Added `ViewState._preview_R` and `Viewer._preview_slices` to cache fast Numba affine projections during slider drag.
  * Added `_active_resample_job` to cancel in-flight ITK resamples via early exit checks.
  * **Known remaining issue:** Threading complexity between the preview worker, ITK resample threads, and the DPG loop can still rarely cause visual ghost flashes during rapid auto-update fusion toggles.
* **Architecture Refactor (May 2026)**:
  * Eliminated 100+ lines via helper consolidation (`format_pixel_value`, `_get_window_dims`).
  * Strict MVC adherence: `controller.update_setting` no longer calls the GUI directly.
  * Pending future cleanup: Consolidate tracking fields in `viewer.py` into a `RenderState` dataclass; move transform I/O out of Controller into `FileManager`.
