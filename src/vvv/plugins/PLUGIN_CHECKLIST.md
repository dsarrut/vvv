# Plugin Implementation Checklist

Use this checklist when implementing or reviewing a plugin.

---

## Enabling / disabling

- Set `order = -1` (any negative value) to disable a plugin without removing it from the codebase. Discovery instantiates it but does not register it, so no UI, no hooks, no cost at runtime.
- Positive `order` controls sidebar position (lower = higher up). Default is 999.
- `plugin_id` must be **unique** across all plugins — a collision silently corrupts DPG tag namespaces and is caught at startup with a `RuntimeError`.

---

## PluginAPI contract

Plugins must only interact with the app through `PluginAPI`. Bypassing it creates hidden dependencies and breaks the isolation the protocol provides.

- [ ] Plugin never accesses `api._controller`, `api._gui`, or any private attribute
- [ ] If an operation is missing from `PluginAPI`, add a method there — do not reach into internals
- [ ] Contours: use `api.add_contour(image_id, roi)` and `api.remove_contour(image_id, roi_id)`
- [ ] Generating a new image from plugin output: use `api.mount_generated_image(new_vol, new_vs)` — this assigns an ID, registers the volume, assigns it to the active viewer, and notifies all plugins

---

## Core lifecycle

- [ ] `on_image_loaded(image_id)` — creates per-image state entry
- [ ] `on_image_removed(image_id)` — deletes entry, closes any popup windows, stops background threads
- [ ] `destroy()` — implement in **both** the plugin and its controller, even if currently empty; delegate: `self._controller.destroy()`. Never leave `destroy()` as `pass` in the plugin only — future additions to the controller will silently skip cleanup.
- [ ] `save_settings` / `load_settings` — global UI preferences that apply to every new image (not per-image state). These are called once at startup/shutdown, not per image.
- [ ] `serialize_image_state` / `restore_image_state` — per-image state, called by history and workspace

---

## Beginner mode

- [ ] Help buttons (`build_help_button`) added next to non-obvious controls
- [ ] Tooltips (`build_beginner_tooltip`) on labels that need explanation

---

## Sync

- [ ] Plugin reads from the **active viewer** only (`api.get_active_viewer()`), not a hardcoded viewer
- [ ] When a callback writes display state, it calls the appropriate propagate method (`api.propagate_window_level`, `api.propagate_colormap`, …) so synced viewers update
- [ ] Plugin does not assume a 1-to-1 image/viewer relationship — multiple viewers can show the same image

---

## Image removal (`on_image_removed`)

- [ ] Per-image plugin state dict cleaned up (e.g. `self._hist.pop(image_id, None)`)
- [ ] Any floating popup window that was showing data for that image is **deleted** (not just hidden)
- [ ] Background threads computing data for that image are **stopped** (stop event set)
- [ ] Render caches referencing that image id are cleared (`_last_sidebar_image_id`, etc.)

---

## History and workspace

- [ ] `serialize_image_state(image_id, context)` returns a JSON-serializable dict. The `context` parameter is either `"history"` (auto-restore on file load) or `"workspace"` (explicit save/load). Return `{}` for contexts you don't support.
- [ ] `restore_image_state` applies the dict back onto the existing per-image state object (created by `on_image_loaded`)
- [ ] Restored values are applied **before** the first `update()` call so the first frame is correct
- [ ] Old history entries with missing keys are handled gracefully (`data.get("key", default)`)
- [ ] State that belongs to the **core** (WW/WL, colormap, camera) is not duplicated in the plugin's serialization
- [ ] check that history never interfere when workspace is used

---

## Background threads

- [ ] A `threading.Event` stop flag is used — created in `__init__`, cleared before spawning, checked inside the thread before writing results back
- [ ] Stop flag is set in `on_image_removed` (for that image's thread) and in `destroy()` (all threads)
- [ ] Thread results are posted back via `api.run_on_main_thread(callback)` — never touch DPG or plugin state directly from a background thread
- [ ] Inside the callback, call `api.request_refresh()` and `api.set_async_status()` to signal the main loop
- [ ] Thread is a **daemon thread** so it does not block app exit

---

## Additional things to verify

- [ ] **RGB images** — controls that don't apply to RGB (WW/WL, histogram) are disabled, not hidden
- [ ] **Empty state** — `update()` handles `viewer = None` and `has_image = False` cleanly; UI shows a neutral "No Image Selected" state
- [ ] **Image reload** — data changes are detected via `id(vol.data)` comparison, not image_id; dirty flags are reset correctly on reload
- [ ] **4D / time series** — if the plugin reads voxel data, does it use the correct time index (`vs.camera.time_idx`)? Does a time change invalidate any cache?
- [ ] **DPG tag namespacing** — every DPG tag is prefixed with `self._plugin_id` via `_t(name)`; no hardcoded strings that could collide with other plugins
- [ ] **Editable input fields** — every `add_input_text` / `add_input_int` / `add_input_float` that accepts user typing must have a string tag whose name contains `"input_"` (e.g. `self._t("input_my_field")`). The global key-press guard in `ui_interaction.py` scans aliases for this substring to suppress viewer shortcuts while the user is typing. Fields without a tag (auto-ID) or with a tag that doesn't contain `"input_"` will leak keystrokes to the viewer. `readonly=True` fields are exempt.
- [ ] **Popup window** — if a popup exists, its tags are also namespaced; it is closed in `on_image_removed` and `destroy()`. Name of the popup window should contain the image name.
- [ ] **`update()` is called only when dirty** — avoid expensive recomputation; use caches (`_last_image_id`, `id(vol.data)`) to skip redundant work
- [ ] **Overlay images** — does the plugin need to react to the overlay as well as the base image? (see DVF `_get_target_vs` pattern)
- [ ] **`is_auto_overlay` images** — `on_image_loaded` is NOT dispatched for auto-loaded overlays; plugin state only covers base images
- [ ] **Styling & Colors** — avoid hardcoded colors (e.g. RGB red/blue/green lists) for UI text, warnings, or headers. Query `api.get_ui_config()["colors"]` to respect the global theme colors (e.g. `text_header`, `text_dim`).
- [ ] **Theme Binding** — bind standard DearPyGui themes (e.g. `icon_button_theme`) rather than manually styling buttons, keeping UI controls visually unified.
- [ ] **Settings persistence** — `save_settings`/`load_settings` store *default values for new images*, not per-image state. Per-image state belongs in `serialize_image_state`/`restore_image_state`. Do not mix the two.
- [ ] **Unified Settings** — check if important UI element properties (like some sizes, colors) are managed in `ui_theme.py` and settings files.

