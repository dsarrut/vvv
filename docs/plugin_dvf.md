# DVF Plugin Developer Guide

This plugin controls the visualization of Displacement Vector Fields (DVFs): display mode selection (Component, RGB, Vector Field), vector rendering parameters, and color mapping.

## File Structure

- **[plugin_dvf.py](../src/vvv/plugins/dvf/plugin_dvf.py)**: Registers the plugin entry point and coordinates lifecycle events.
- **[ui_dvf.py](../src/vvv/plugins/dvf/ui_dvf.py)**: Defines the DearPyGui layout for the sidebar panel.
- **[control_dvf.py](../src/vvv/plugins/dvf/control_dvf.py)**: Contains the controller that detects DVF images, syncs UI controls with DVFState, and dispatches callbacks.

---

## 1. Why DVF is Architecturally Different from Other Plugins

Most plugins (e.g. Intensity) only read `ViewState` to drive their UI. The DVF plugin **changes how the image is rendered** — vector arrows and color modes are drawn directly into the viewer texture. This is a deeper integration with the rendering pipeline than a typical plugin.

As a consequence, **`DVFState` lives in `core/view_state.py`**, not inside the plugin itself. This is an intentional architectural decision:

- The renderer (`viewer.py`) reads `vs.dvf` directly to draw arrows. It cannot call into the plugin.
- The core serialization systems (`history_manager`, `save_workspace`, `load_workspace`) need access to DVF state without coupling to the plugin layer.
- DVFState is initialized automatically at `ViewState` construction time with sensible defaults computed from the data (see §3).

**If DVFState were owned by the plugin**, the renderer would need a plugin-aware API (not yet built), and serialization hooks would need to pass through the plugin contract. This is the right long-term direction as the plugin system matures, but requires an `on_image_loaded` event and plugin-owned serialization infrastructure that does not yet exist.

**Practical rule:** the DVF plugin UI and controller are a thin control layer on top of `DVFState`. They read it, write it, and sync it to DPG widgets — but they do not own it.

---

## 2. Detecting a DVF Image

The plugin does not assume the active image is a DVF. On every `update()`, the controller calls `_get_target_vs()` which checks:

1. **Base image**: `viewer.volume.is_dvf` — the primary image loaded in the viewer is a DVF.
2. **Overlay image**: if the base is not a DVF, check `viewer.view_state.display.overlay_id` and inspect the overlay's volume.

This means the plugin works correctly in both cases:
- A DVF loaded directly as the main image.
- A DVF loaded as an overlay on top of a base image (common in registration workflows).

The `is_base` flag returned by `_get_target_vs()` determines whether Display Mode selection (Component / RGB / Vector Field) is shown — it only makes sense for the base image, not for overlays which always use Vector Field mode.

---

## 3. DVFState Initialization

When a `ViewState` is created for a DVF volume, `DVFState.__init__` auto-computes two parameters from the data to produce a visually useful default without any user interaction:

- **`vector_color_max_mag`**: estimated from the 99th percentile of vector magnitudes (subsampled 2×), so the color scale maps to realistic displacement values rather than arbitrary extremes.
- **`vector_sampling`**: set to target approximately 100 arrow heads across the longest image dimension, preventing an unreadable density of arrows on large volumes.

These defaults are recomputed on every fresh image load. History and workspace both persist the user's customized values and restore them on reopen (see §4), overriding the auto-computed defaults.

---

## 4. History and Workspace

DVF state is persisted at two levels:

| Level | When | What |
|-------|------|------|
| **History** | On image close + app exit | `DVFState.to_dict()` — all vector params |
| **Workspace** | Explicit save | `DVFState.to_dict()` — all vector params |

History saves DVF state only when `vol.is_dvf` is true (guarded in `history_manager.save_image_state`). On restore, `vs.dvf.from_dict()` is called before the viewer renders the first frame, so the user sees their last configuration immediately.

The plugin's `save_settings` / `load_settings` are no-ops. All meaningful state is per-image and handled by history and workspace — there is no useful global default to persist at the application level.

---

## 5. Display Modes

The `display_mode` field on `DVFState` controls the rendering path in the viewer:

| Mode | Description |
|------|-------------|
| **Component** | Each spatial component (X, Y, Z) mapped to a colormap independently |
| **RGB** | X → R, Y → G, Z → B, magnitude → alpha |
| **Vector Field** | Arrows drawn at sampled grid points, length and color encode magnitude |

Display mode selection is only visible (and meaningful) when the DVF is the **base** image. When used as an overlay, Vector Field mode is always active.

---

## 6. Vector Field Rendering Parameters

All parameters live in `DVFState` and are synced by the controller every dirty frame:

| Parameter | Description |
|-----------|-------------|
| `vector_sampling` | Pixel spacing between arrow origins (higher = fewer arrows) |
| `vector_scale` | Visual length multiplier (does not affect the underlying displacement) |
| `vector_thickness` | Line width of arrows in pixels |
| `vector_min_length_draw` | Displacements below this magnitude (mm) are not drawn |
| `vector_min_length_arrow` | Displacements below this magnitude (mm) are drawn as lines, not arrows |
| `vector_color_max_mag` | Magnitude value mapped to the maximum color (saturates above) |
| `vector_color_min` | RGBA color for zero-magnitude displacements |
| `vector_color_max` | RGBA color for `vector_color_max_mag`-magnitude displacements |
| `vector_precision` | Decimal places shown in crosshair tracker |
