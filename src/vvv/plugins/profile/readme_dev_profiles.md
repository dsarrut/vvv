# Profile Plugin Developer Guide

This plugin provides interactive intensity profiles: line segments drawn on a viewer slice that sample voxel intensities along their length and display the result as an XY plot.

## File Structure

- **[plugin_profile.py](plugin_profile.py)**: Entry point. Registers lifecycle events and delegates to controller and UI.
- **[control_profile.py](control_profile.py)**: Controller. Handles all user interaction callbacks (add, delete, rename, color, align, snap, goto, slice navigation, coordinate editing, export).
- **[ui_profile.py](ui_profile.py)**: UI. Builds the sidebar list and the per-profile floating plot window.

---

## 1. Profile State Ownership

Profile state lives entirely in `ViewState.profiles: dict[str, ProfileLineState]`, owned by the **core** — not by this plugin. Key consequences:

- `on_image_loaded` is a no-op: profiles start empty, created only via user interaction.
- `serialize_image_state` returns `{}` and `restore_image_state` is a no-op: the core `file_manager` and `ui_sequences` already serialize/restore `profiles` as part of workspace and history handling. The plugin must not duplicate this or it will produce doubled profiles on load.
- `on_image_removed` only needs to close any open plot windows; it does not clean up the dict (the core disposes of the `ViewState` itself).

---

## 2. Profile Creation Flow

Profiles are created by the **viewer** (not the plugin) when the user presses `P` over an active slice:

1. The viewer instantiates a `ProfileLineState`, assigns it a DPG UUID as its `id`, picks a color from `ROI_COLORS`, and places it horizontally at the current slice center.
2. Endpoints are stored as **physical (world-space) coordinates** in `pt1_phys` / `pt2_phys` (numpy arrays, mm).
3. The viewer then calls `profile_plugin._ui.on_plot_clicked(None, None, p.id)` directly to auto-open the plot window.

The plugin's "Add Profile (P)" button in the sidebar simply calls `viewer.on_key_press(dpg.mvKey_P)` to delegate back to the viewer.

---

## 3. Coordinate Systems

A profile always lives in physical (world) space so it survives orientation switches and zoom changes. Three coordinate systems are involved:

| Space | Description | Used for |
|-------|-------------|----------|
| **Physical (mm)** | `pt1_phys`, `pt2_phys` — stored in `ProfileLineState` | Ground truth, serialization |
| **Display voxel** | Output of `view_state.world_to_display(pt_phys)` | Drawing, slice detection |
| **Slice (screen)** | Output of `voxel_to_slice(...)` | Pixel positions for `draw_line` |

The align and snap operations convert back and forth via `voxel_to_slice` / `slice_to_voxel` / `world_to_display` / `display_to_world` to reposition endpoints while keeping them in the current slice plane.

---

## 4. Intensity Sampling

Sampling is handled entirely by `ProfileManager` in `src/vvv/core/profile_manager.py`:

- Step size = `min(vol.spacing)` so the line is always sampled at sub-voxel resolution.
- Each sample uses **trilinear interpolation** over the native voxel grid.
- RGB volumes return `np.mean(channel)`, DVF volumes return `np.linalg.norm(vector)`.
- 4D volumes use `vs.camera.time_idx` to select the correct timepoint.

The plugin retrieves data through `api.get_profile_data(image_id, profile)` and `api.get_full_export_data(image_id, profile)`.

---

## 5. Sidebar List — Dirty-Key Rebuild Guard

`update_ui` is called on every frame. Rebuilding the table every frame would destroy the color picker popup before the user finishes picking a color. The fix is a `_last_profile_key` cache:

```python
profile_key = (viewer.image_id, tuple(viewer.view_state.profiles.keys()))
if profile_key == self._last_profile_key:
    return   # nothing added or removed — skip rebuild
```

The table is only rebuilt when the set of profile IDs changes (add, delete) or the active image changes. The key is reset to `None` in `on_image_removed` so the next render unconditionally refreshes the list.

**Important**: do not add `build_beginner_tooltip` or tagged DPG items inside the table rows — they are deleted and recreated on every rebuild, which would accumulate stale tag IDs in `api.beginner_tags`.

---

## 6. Color Format

DPG `add_color_edit` callback (`app_data`) returns floats in **[0.0, 1.0]**. `ProfileLineState.color` and all DPG drawing functions (`draw_line`, `draw_circle`) expect integers in **[0, 255]**. The conversion is:

```python
profile.color = [int(c * 255) for c in app_data[:4]]
```

---

## 7. Plot Window Per Profile

Each profile has an optional floating popup window (`plot_win_{profile.id}`) built by `build_plot_window_contents`. It contains:

- A toolbar mirroring the sidebar row actions (color, align, snap, goto, slice nav, delete).
- A DPG line series plot (`series_{profile.id}`) showing distance (mm) vs intensity.
- Editable physical coordinate inputs (`input_phys_p1/p2_{profile.id}`) that write back to `pt1_phys` / `pt2_phys`.
- A "Linear / Log" toggle that rebuilds the entire plot window to swap the Y-axis scale.

The window label includes the image name: `"Profile: {name} [{image_name}]"` so it remains identifiable across multi-image layouts. The label is kept in sync when the user renames the profile via `on_profile_name_changed`.

---

## 8. Drawing (Viewer Side)

Drawing is handled by `Drawer.draw_profiles()` in `src/vvv/ui/drawing.py`, called every frame during the viewer's geometry pass:

- Profiles on the **current slice** are drawn as a full-opacity line with endpoint circles.
- Profiles on **adjacent slices** (within ±6 slices) are drawn dimmed, with alpha decreasing linearly with distance.
- **Cross-plane profiles** (orientation differs from the viewer) appear as a small ring at their midpoint projection.
- Only works in 2D image-orientation views (`viewer.is_image_orientation()`); hidden in 3D/MPR modes.
