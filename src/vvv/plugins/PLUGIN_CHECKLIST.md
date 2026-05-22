# Plugin Implementation Checklist

Use this checklist when implementing or reviewing a plugin.

---

## Enabling / disabling

- Set `order = -1` (any negative value) to disable a plugin without removing it from the codebase. Discovery instantiates it but does not register it, so no UI, no hooks, no cost at runtime.
- Positive `order` controls sidebar position (lower = higher up). Default is 999.

---

## Core lifecycle

- [ ] `on_image_loaded(image_id)` — creates per-image state entry
- [ ] `on_image_removed(image_id)` — deletes entry, closes any popup windows, stops background threads
- [ ] `destroy()` — stops background threads, releases non-DPG resources
- [ ] `save_settings` / `load_settings` — global UI preferences (not per-image state)
- [ ] `serialize_image_state` / `restore_image_state` — per-image state, called by history and workspace

---

## Beginner mode

- [ ] Advanced controls added to `api.beginner_tags` or `api.beginner_sliders` so they are hidden in beginner mode
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

## History

- [ ] `serialize_image_state` returns a JSON-serializable dict of all user-facing per-image state
- [ ] `restore_image_state` applies the dict back onto the existing per-image state object (created by `on_image_loaded`)
- [ ] Restored values are applied **before** the first `update()` call so the first frame is correct
- [ ] Old history entries with missing keys are handled gracefully (`data.get("key", default)`)

---

## Workspace

- [ ] Same `serialize_image_state` / `restore_image_state` used for workspace — no separate code path
- [ ] State that belongs to the **core** (WW/WL, colormap, camera) is not duplicated in the plugin's serialization

---

## Background threads

- [ ] A `threading.Event` stop flag is used — created in `__init__`, cleared before spawning, checked inside the thread before writing results back
- [ ] Stop flag is set in `on_image_removed` (for that image's thread) and in `destroy()` (all threads)
- [ ] Thread result callback uses `api.request_refresh()` and `api.set_async_status()` — never touches DPG directly
- [ ] Thread is a **daemon thread** so it does not block app exit

---

## Additional things to verify

- [ ] **RGB images** — controls that don't apply to RGB (WW/WL, histogram) are disabled, not hidden
- [ ] **Empty state** — `update()` handles `viewer = None` and `has_image = False` cleanly; UI shows a neutral "No Image Selected" state
- [ ] **Image reload** — data changes are detected via `id(vol.data)` comparison, not image_id; dirty flags are reset correctly on reload
- [ ] **4D / time series** — if the plugin reads voxel data, does it use the correct time index?
- [ ] **DPG tag namespacing** — every DPG tag is prefixed with `self._plugin_id` via `_t(name)`; no hardcoded strings that could collide with other plugins
- [ ] **Popup window** — if a popup exists, its tags are also namespaced; it is closed in `on_image_removed` and `destroy()`. Name of the popup window should contains the image name.
- [ ] **`update()` is called only when dirty** — avoid expensive recomputation; use caches (`_last_image_id`, `id(vol.data)`) to skip redundant work
- [ ] **Overlay images** — does the plugin need to react to the overlay as well as the base image? (see DVF `_get_target_vs` pattern)
- [ ] **`is_auto_overlay` images** — `on_image_loaded` is NOT dispatched for auto-loaded overlays; plugin state only covers base images
