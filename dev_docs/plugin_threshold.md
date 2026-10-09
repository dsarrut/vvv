# Threshold Plugin Developer Guide

This plugin provides interactive thresholding: a live preview of contour lines at configurable min/max intensity values, and a "Create Image" action that bakes the threshold into a new standalone volume.

## File Structure

- **[plugin_threshold.py](../src/vvv/plugins/threshold/plugin_threshold.py)**: Entry point. Registers lifecycle events and delegates to controller and UI.
- **[control_threshold.py](../src/vvv/plugins/threshold/control_threshold.py)**: Controller. Owns per-image `ThresholdState`, manages preview ROI lifecycle, runs the generation background thread, handles all callbacks.
- **[ui_threshold.py](../src/vvv/plugins/threshold/ui_threshold.py)**: UI. Builds the sidebar: sliders, color pickers, generation options, and handles per-image context switching.

---

## 1. State Ownership

Unlike the profile plugin (where state lives in the core's `ViewState`), threshold state is **owned entirely by the plugin**:

```python
self._states: dict[str, ThresholdState] = {}
```

Consequently:
- `serialize_image_state` returns `state.to_dict()` — the plugin is responsible for persistence.
- `restore_image_state` calls `state.from_dict(data)` and marks geometry dirty.
- `on_image_removed` pops the state dict entry and clears preview ROIs.
- `on_image_loaded` calls `get_image_state` to pre-allocate the state and seed initial thresholds from `vol._cached_min_val / _cached_max_val`.

---

## 2. Preview ROI Lifecycle

The live preview uses two **transient `ContourROI` objects** injected directly into the image's `vs.contours` dict. They are identified by custom boolean attributes:

| Attribute | ROI | Purpose |
|-----------|-----|---------|
| `is_plugin_draft_min` | `roi_min` | Contour at the lower threshold |
| `is_plugin_draft_max` | `roi_max` | Contour at the upper threshold |

These ROIs are **never serialized** — they are created on demand in `_get_or_create_preview_rois` and destroyed via `clear_preview`. The correct ownership sequence:

1. User enables thresholding → `on_enable_toggle` sets `state.is_enabled = True`.
2. On the next geometry pass, `viewer.py` calls `thr_plugin._controller.update_preview(...)`.
3. `update_preview` calls `_get_or_create_preview_rois`, which mounts the two ROIs via `self._api._controller.contours.add_contour(img_id, roi)`.
4. The drawing layer renders them as normal contour ROIs.
5. When the user disables or removes the image, `clear_preview` removes them via `contours.remove_contour`.

**Cache invalidation**: each ROI stores `last_computed_threshold_min/max`, `last_computed_subpixel`, `last_computed_time_idx`, and `last_computed_transform`. When any of these diverge from current state, all polygon dicts are cleared and slices recompute on demand.

---

## 3. `update_preview` Call Site

`update_preview` is **not called from `plugin.update()`**. It is called from the viewer's geometry pass in `src/vvv/ui/viewer.py`, synchronously on the render thread, just before ROI contour rendering:

```python
thr_plugin._controller.update_preview(
    self.image_id, vol, vs, thr_state, self.orientation, self.slice_idx, slice_data,
)
```

The viewer resolves the plugin by scanning `controller.gui.plugins` for `plugin_id == "threshold_plugin"`. The method only computes contours for slices not already cached — expensive work is amortized slice-by-slice.

The drawing dirty-check in `src/vvv/ui/drawing.py` tracks `(threshold_min, threshold_max, subpixel_accurate)` as part of the contour redraw state tuple, so a slider drag triggers a geometry redraw even when the ROI polygon dict doesn't change yet.

---

## 4. Slice Data Source

`update_preview` receives `slice_data` from the viewer. The viewer preferentially passes the **pre-transform slice** (`vs.base_display_data` or `_preview_slices`) so the contour matches what is actually displayed on screen, including any active spatial transform (`vs._preview_R`). DVF volumes skip the transformed path.

---

## 5. Context Switch Snap (`_current_image_id`)

The sidebar uses `self._current_image_id` to detect when the active image changes. On a switch, all DPG widgets are snapped to the new image's state in one pass ("Context Switch Snap" block in `update_ui`). On subsequent frames for the same image, only widgets that diverged from state are updated ("Continuous Sync" block). This avoids fighting with active drag widgets.

---

## 6. Image Generation

"Create Image" runs a background `threading.Thread` to avoid blocking the UI. Key design points:

- A `threading.Event` stop flag (`self._generation_stop`) is created per launch and checked at the start of the thread. Calling `destroy()` sets it, aborting any in-flight generation.
- The thread builds a `VolumeData` and `ViewState` in memory, bypassing disk I/O, then mounts them directly via `api._controller`:

  ```python
  controller.volumes[new_id] = new_vol
  controller.view_states[new_id] = new_vs
  controller.gui.notify_plugins_image_loaded(new_id)
  ```

- `notify_plugins_image_loaded` must be called after mounting so other plugins (`on_image_loaded`) receive the new image.
- Status messages use `api.set_async_status(...)` + `api.request_refresh()` for thread-safe UI feedback.
- 4D volumes are processed frame-by-frame to avoid large intermediate RAM spikes.

---

## 7. Color Format

Color pickers (`add_color_edit`) return floats `[0.0, 1.0]`. `ContourROI.color` and all drawing functions expect integers `[0, 255]`. The `on_threshold_drag` callback auto-detects which scale is in use:

```python
scale = 255.0 if all(c <= 1.0 for c in app_data) else 1.0
state.preview_color_min = [int(c * scale) for c in app_data[:4]]
```

---

## 8. RGB and 4D Handling

- **RGB images**: thresholding is disabled entirely. The UI disables all controls and shows "RGB Base / Not Supported" in the range labels.
- **4D volumes**: generation processes each timepoint independently (loop over `vol.data[t]`). The preview samples from the current `vs.camera.time_idx` frame; a temporal context label is shown when enabled.
- **DVF volumes**: detected via `getattr(vol, "is_dvf", False)`. The generation path uses `np.moveaxis` to rebuild the ITK vector image.
