Ready for review
Select text to add comments on the plan
Architecture Plan: Interactive Transform ("reg") Tool
Context
The reg tool lets the user apply a rigid transform (Tx, Ty, Tz, Rx, Ry, Rz) to an image interactively via sliders, preview the effect in real-time, and eventually bake the transform into a resampled image. The current implementation has two critical bugs:

Crosshair drift during drag: The crosshair screen position shifts when sliders are moved. It should stay fixed — only the image moves underneath it.
Value-at-crosshair stale: The panel values don't update correctly because the coordinate path mixes buffered/unbuffered states incorrectly.
Additionally, there is no fast interactive rotation preview — it goes immediately to the slow ITK resample path.

Core Invariant (The Pin Model)
During any transform change, exactly one thing is fixed:

vs.camera.crosshair_phys_coord  ←  world position, NEVER changes during a drag
vs.camera.pan                   ←  viewer offset, NEVER changes during a drag
vs.camera.zoom                  ←  viewer scale, NEVER changes during a drag
What changes:

vs.space.transform — the new transform
vs.camera.crosshair_voxel — the image voxel under the world pin (derived fresh)
vs.camera.slices — the slice index in each orientation (derived fresh)
vs.crosshair_value — the pixel value under the pin (read fresh from native data)
The image appears to move under a fixed crosshair. The camera does not move.

Root cause of current drift: apply_transform_and_keep_world_fixed() sets camera.target_center = anchor_world_pos, which tells the tick() loop to re-pan the viewer to keep that point centered — defeating the fixed-camera invariant. It also sets is_geometry_dirty=True, which triggers a resize() that recalculates pmin/pmax and can shift the rendered crosshair position.

Architecture: Three Display Phases
Phase 1 — Interactive fast display (during slider drag)
In-field translation (no rotation):

Apply a 2D pixel offset to the base image slice (same RenderLayer.offset_x/y/slice mechanism already used for overlays)
No ITK resampling, no re-extraction from volume
is_data_dirty=True, is_geometry_dirty=False
In-field rotation (during drag):

Use the existing Numba affine kernel (compute_native_voxel_overlay in render_strategy.py) adapted for the base image
New flag vs._is_interactive_rotation = True tells viewer.tick() to use this fast path
No ITK resampling during drag
Overlay: stays at its last resampled state during rotation drag (acceptable)
Out-of-field translation:

Detected when world_to_display(crosshair_phys_coord) produces a slice index outside [0, vol.shape3d[axis])
Extract a new slice from vol.data at the new slice index (cheap — just different z from existing data)
Not a resample; just a different slice read
Out-of-field rotation: Not handled yet (requires full resample — deferred).

Phase 2 — Quality display (300ms debounce after last drag event)
Triggers existing trigger_debounced_rotation_update() → update_base_display_data() (ITK ResampleImageFilter)
Same path as today but only runs after Phase 1 has been visually responsive
Clears _is_interactive_rotation = False on completion
Phase 3 — Apply Transform (bake)
"Apply Transform" checkbox = display toggle (existing behavior: vs.space.is_active)
New "Bake Transform" button = permanently resamples the volume, resets transform to identity, rebuilds the SpatialEngine
Implemented as controller.bake_transform_to_volume(vs_id) in a background thread with loading_shield
Detailed Changes Per File
1. src/vvv/core/view_state.py
Add to ViewState.__init__:

self._reg_anchor_world: np.ndarray | None = None  # world pin during drag (set on first drag event, cleared on settle)
self._is_interactive_rotation: bool = False        # routes to fast Numba path in viewer.tick()
Add update_crosshair_voxel_from_native(native_vox): A lightweight update that changes voxel coords, slices, and crosshair_value without touching crosshair_phys_coord or triggering geometry redraw:

def update_crosshair_voxel_from_native(self, native_vox: np.ndarray):
    ix = int(np.clip(np.round(native_vox[0]), 0, self.volume.shape3d[2] - 1))
    iy = int(np.clip(np.round(native_vox[1]), 0, self.volume.shape3d[1] - 1))
    iz = int(np.clip(np.round(native_vox[2]), 0, self.volume.shape3d[0] - 1))
    self.camera.crosshair_voxel = [native_vox[0], native_vox[1], native_vox[2], self.camera.time_idx]
    self.camera.slices[ViewMode.AXIAL]    = iz
    self.camera.slices[ViewMode.SAGITTAL] = ix
    self.camera.slices[ViewMode.CORONAL]  = iy
    self.crosshair_value = self._read_voxel_value(ix, iy, iz, use_buffer=False)
    self.is_data_dirty = True
    # is_geometry_dirty intentionally NOT set — pan/zoom/crosshair screen pos unchanged
2. src/vvv/maths/geometry.py
Add has_translation(tolerance=1e-5) parallel to existing has_rotation():

def has_translation(self, tolerance=1e-5):
    if not self.transform or not self.is_active:
        return False
    tx, ty, tz = self.transform.GetTranslation()
    return abs(tx) > tolerance or abs(ty) > tolerance or abs(tz) > tolerance
3. src/vvv/ui/ui_registration.py
Replace apply_transform_and_keep_world_fixed() with three focused methods:

_ensure_drag_anchor(vs) — called once at drag start:

def _ensure_drag_anchor(self, vs):
    if vs._reg_anchor_world is None:
        vs._reg_anchor_world = vs.camera.crosshair_phys_coord.copy()
_on_transform_drag(viewer) — called on every slider event:

_ensure_drag_anchor(vs)
Update vs.space.transform from slider values via controller.update_transform_manual()
Map anchor back to new native voxel: native_vox = vs.space.world_to_display(vs._reg_anchor_world, is_buffered=False)
Call vs.update_crosshair_voxel_from_native(native_vox) — updates voxel/slices/value without touching phys coord or pan
Set vs._is_interactive_rotation = vs.space.has_rotation()
Propagate to sync group: call vs.update_crosshair_voxel_from_native(tgt_native) on each synced ViewState (NOT target_center — no pan update)
Trigger debounced resample for quality (existing trigger_debounced_rotation_update)
vs.is_data_dirty = True, vs.is_geometry_dirty = False
_on_transform_settled(viewer) — called on apply/toggle (not drag):

Same as today's apply_transform_and_keep_world_fixed() but uses vs._reg_anchor_world as the anchor (not re-derived)
Calls vs.update_crosshair_from_phys(anchor) (full reconcile — safe because drag is over)
Sets camera.target_center = anchor to re-center (OK here: this is a discrete user action, not continuous drag)
Clears vs._reg_anchor_world = None and vs._is_interactive_rotation = False
Wire on_reg_manual_changed() → _on_transform_drag()
Wire on_reg_apply_toggled() → _on_transform_settled()

4. src/vvv/ui/viewer.py
Modify _package_base_layer(): When vs.space.is_active and translation only (no rotation), compute pixel offset from translation mm → pixels and pass as RenderLayer(offset_x=, offset_y=, offset_slice=).

Extract a helper _translation_to_offsets(tx, ty, tz, orientation, spacing) (also used in _package_overlay_layer to avoid duplication) with correct sign conventions per orientation:

Orientation	offset_x	offset_y	offset_slice
AXIAL	tx/sp_x	ty/sp_y	tz/sp_z
CORONAL	tx/sp_x	-tz/sp_z	ty/sp_y
SAGITTAL	-ty/sp_y	-tz/sp_z	tx/sp_x
Add _compute_rotation_fast_preview() in viewer.py: When vs._is_interactive_rotation = True, bypass _compute_raw_slice_buffers() and render the base image via the same affine canvas-mapping math as compute_native_voxel_overlay, but for the base image (no overlay). Extract the shared affine math from render_strategy.py into _build_affine_canvas_mapping(vs, vol, orientation, mapper) and call it from both paths.

In update_render() (the tick() render path):

if vs._is_interactive_rotation:
    self._compute_rotation_fast_preview()
else:
    self._compute_raw_slice_buffers()  # existing path
Do NOT change _get_crosshair_display_voxel() — it already uses world_to_display(crosshair_phys_coord, is_buffered=False) which is correct for both the fast path and the quality path.

5. src/vvv/core/sync_manager.py
Add propagate_transform_sync(source_vs_id): A lighter version of propagate_sync that updates voxel coords/values in synced images without changing any camera pan/zoom state. Called from _on_transform_drag() in place of propagate_sync.

def propagate_transform_sync(self, source_vs_id):
    source_vs = self.controller.view_states.get(source_vs_id)
    if not source_vs or source_vs.camera.crosshair_phys_coord is None:
        return
    world_phys = source_vs.camera.crosshair_phys_coord  # the fixed world pin
    for target_id in self.get_sync_group_vs_ids(source_vs_id, active_only=True):
        if target_id == source_vs_id:
            continue
        target_vs = self.controller.view_states.get(target_id)
        if not target_vs:
            continue
        tgt_native = target_vs.space.world_to_display(world_phys, is_buffered=False)
        target_vs.update_crosshair_voxel_from_native(tgt_native)
    self.trigger_redraw(...)
6. src/vvv/ui/render_strategy.py
Extract the inner affine math from compute_native_voxel_overlay into a reusable function:

def build_affine_canvas_mapping(vol, transform, orientation, mapper) -> tuple[np.ndarray, np.ndarray]:
    """Returns (A_total, b_total) for mapping canvas pixel → native voxel."""
    ...
Call this from both compute_native_voxel_overlay (overlay path) and _compute_rotation_fast_preview (base image path).

7. src/vvv/core/controller.py
Add bake_transform_to_volume(vs_id):

Background thread with loading_shield
ITK ResampleImageFilter on the full volume
Replace vol.sitk_image, vol.data, update vol.origin
Reset vs.space.transform = None, vs.space.is_active = False, vs.base_display_data = None
Rebuild vs.space = SpatialEngine(vol, view_state=vs)
Call update_crosshair_from_phys(crosshair_phys_coord) to remap crosshair
Rebuild dependent overlays, call propagate_sync(vs_id), update_all_viewers_of_image(vs_id)
8. src/vvv/ui/ui_registration.py (UI additions)
Add "Bake Transform" button next to "Apply Transform" checkbox
Button triggers controller.bake_transform_to_volume(vs_id)
Clarify label: "Apply to Viewers" for the checkbox, "Bake into Image" for the button
Implementation Order (to avoid regressions)
Add _reg_anchor_world, _is_interactive_rotation to ViewState; add update_crosshair_voxel_from_native()
Add has_translation() to SpatialEngine
Fix anchor logic in ui_registration.py — replace apply_transform_and_keep_world_fixed with the three methods; wire callbacks; verify crosshair no longer drifts during translation drag
Add base layer offset in _package_base_layer() using _translation_to_offsets() helper; verify base image shifts visually during translation
Add propagate_transform_sync() to SyncManager; verify synced viewers update correctly during drag
Extract build_affine_canvas_mapping() from render_strategy.py; implement _compute_rotation_fast_preview(); wire via _is_interactive_rotation; verify fast rotation preview works
Add bake_transform_to_volume() to controller.py and "Bake Transform" button to UI
Verification
Single image, translation only: image shifts in viewer, crosshair screen pos fixed, values update
Single image, rotation: fast Numba preview during drag, quality ITK after 300ms settle, crosshair fixed
Synced images: dragging transform on image A updates crosshair values in synced viewers without panning them
Fusion: base image translation shifts base + overlay together correctly (existing _package_overlay_layer offset minus base offset)
Apply Transform toggle: display toggle only (no resample), crosshair stays fixed
Bake Transform: full resample, transform reset to identity, all viewers update