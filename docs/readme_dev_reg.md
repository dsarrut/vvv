# Registration Tool

Manages manual 6-DOF extrinsic rigid transforms (`Euler3DTransform`).

* **Transform I/O**: Reads/writes `.tfm`, `.mat`, `.txt` via `api.load_transform` / `api.save_transform`.

## The "Pin Model" Architecture

### Phase 1 — Live Preview (instant, every slider drag)

Dragging a slider calls `on_reg_manual_changed` → updates the `Euler3DTransform` in `vs.space` → enqueues a request to `_preview_queue`. A persistent background worker (`_preview_worker_loop`) drains the queue, discarding stale requests, and computes fast 2D affine slice projections via `compute_preview_2d_affine` (Numba). Results are stored in:

- `vs._preview_R` — the rotation matrix used for the preview
- `viewer._preview_slices` — precomputed affine-projected slices per orientation/slice index

The viewer uses these cached slices instead of re-extracting from `vol.data`, keeping interaction at 60 FPS even for large volumes.

### Phase 2 — Quality Resample (deferred, after 0.7 s of inactivity)

Every slider change resets a `threading.Timer(0.7, _fire_auto_resample)`. When the timer fires without interruption, `_fire_auto_resample` sends a sentinel through the preview queue, which triggers a full `api.resample_image()` — a background ITK `ResampleImageFilter` at full quality. The result replaces the preview slices.

### Phase 3 — Bake

The "Bake" button calls `api.bake_transform_to_volume()`: applies the transform permanently to `VolumeData.data` in physical space and resets `vs.space` to an identity transform.
