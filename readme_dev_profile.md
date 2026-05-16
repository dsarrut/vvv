# Profile Tool

Extracts and displays 1D intensity profiles along arbitrary line segments drawn across image slices.

## Architecture

| Layer | File | Role |
|---|---|---|
| State | `core/view_state.py` — `ProfileLineState` | Source of truth for each profile (coordinates, color, UI state) |
| Computation | `core/profile_manager.py` — `ProfileManager` | Stateless: samples intensities along the line via trilinear interpolation |
| Drawing | `ui/drawing.py` — `OverlayDrawer.draw_profiles()` | Renders profile lines and endpoints into each viewer's DPG draw node |
| UI | `ui/ui_profile.py` — `ProfileUI` | Sidebar list, floating plot windows, all user actions |
| Interaction | `ui/ui_interaction.py` | Detects endpoint/midpoint hover; handles drag in real time |
| Creation | `ui/viewer.py` — `on_key_press()` | P key (configurable) creates a default horizontal profile at FOV center |
| Persistence | `core/file_manager.py` / `ui/ui_sequences.py` | `to_dict` / `from_dict` serialization into `.vvw` workspace files |

## Data Model — `ProfileLineState`

```
id          str         UUID
name        str         "Profile 1", "Profile 2", …
color       [R,G,B,A]   255-based RGBA
pt1_phys    np.array    3D physical coordinates (mm) of endpoint 1
pt2_phys    np.array    3D physical coordinates (mm) of endpoint 2
orientation ViewMode    Slice plane the profile was drawn on
slice_idx   int         Slice index within that plane
visible     bool
plot_open   bool        Always reset to False on workspace load
use_log     bool        Log scale on the Y axis
```

All profiles for an image are stored in `ViewState.profiles` (dict keyed by UUID). This dict is the single source of truth — no copy is held anywhere else.

## Intensity Sampling — `ProfileManager`

`_sample_points()` is the shared core used by both public methods:

1. `step = min(vol.spacing)` — uses the finest voxel dimension across all three axes, so cross-plane and anisotropic profiles never undersample.
2. Generates `num_points = ceil(dist / step) + 1` evenly-spaced physical positions along the segment.
3. Maps each position to fractional voxel coordinates via `vol.physic_coord_to_voxel_coord()`.
4. Applies **trilinear interpolation** across the 8 surrounding voxel corners. Out-of-bounds corners contribute `0.0` (clamp).
5. Handles 4D volumes (time index clamped to `min(time_idx, num_timepoints-1)`), DVF (`‖v‖`), and RGB (`mean`).

`get_profile_data()` returns `(distances, intensities)` for the live plot.
`get_full_export_data()` returns a dict with all data computed from the same single `_sample_points()` call — no second traversal.

## Reactive Update Flow

Profile edits propagate via two flags, never via direct imperative calls:

```
Any profile change
  → vs.is_geometry_dirty = True   → viewer.tick() redraws overlays (60 fps)
  → controller.ui_needs_refresh = True → gui.loop() rebuilds the sidebar list
```

Plot windows are updated eagerly (not via dirty flags) because they are immediate user-driven actions: `update_plot_info()` and `_refresh_plot_series()` are called directly from each callback.

## Drawing

`draw_profiles()` runs every tick when `vs.is_geometry_dirty` is set. For each profile:

- **In-plane** (same orientation, `|z1 - z2| < 0.5`): draws the line + endpoint circles. Adjacent slices (±6) are drawn with gradual alpha dimming (configurable via `settings.profiles.dim_opacity` / `dim_thickness`).
- **Cross-plane**: draws a small ring at the segment midpoint, visible within ±5 slices of the profile's depth range.

Geometry is written into a per-viewer DPG draw node (`viewer.profile_node_tag`). The node is cleared and rewritten each dirty tick; no incremental update.

## JSON Export Fields

Each point in the `"data"` array contains:

| Field | Type | Description |
|---|---|---|
| `distance_mm` | float | Distance from `pt1_phys` along the segment |
| `intensity` | float | Trilinearly interpolated voxel value |
| `in_bounds` | bool | `True` if the fractional voxel coord is within `[0, shape−1]` on all axes; `False` means at least one corner was clamped to 0 |
| `point_phys_mm` | [x,y,z] float | World-space physical position (mm) |
| `point_voxel_coord` | [x,y,z] float | Fractional voxel coordinate used for interpolation |
| `point_voxel_index` | [x,y,z] int | Nearest integer voxel for direct array access |
| `point_display_voxel` | [x,y,z] float | Voxel coordinate in un-buffered display space (post-registration, pre-padding); `null` if outside transform |

A top-level `"coordinate_systems"` key documents each field in the file itself.

## Coordinate Spaces

Four spaces are involved in every operation:

| Space | Unit | Key conversion |
|---|---|---|
| Physical | mm | `vol.physic_coord_to_voxel_coord()` |
| Voxel | array indices | `vs.world_to_display()` / `vs.display_to_world()` |
| Display voxel | after registration/buffering | `voxel_to_slice()` |
| Screen | pixels | viewport mapper (`ViewportMapper`) |

Profile endpoints are stored in **physical space** (mm) so they remain valid across orientation switches, zoom changes, and registration transforms.

## Keyboard Shortcut

Configurable in Settings → Shortcuts (`shortcuts.add_profile`, default `P`). The viewer resolves it at runtime from `controller.settings.data["shortcuts"]` — not hardcoded. Also appears in the Shortcuts & Controls help window.
