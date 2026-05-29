# Registration (Transform) Plugin Developer Guide

This plugin provides interactive rigid 3D spatial alignment (translation and rotation) of image volumes. It exposes fine-grained sliders to shift and rotate the image, load and save transformation files, and bake the transform into the underlying voxel grid.

## File Structure

- **[plugin_registration.py](plugin_registration.py)**: Plugin entry point. Defines metadata (exposing the user-facing label `"Transform"`), registers lifecycle events, and delegates to the controller and UI.
- **[control_registration.py](control_registration.py)**: Controller. Coordinates transform calculations, background worker threads, auto-resampling timers, file dialogues (load, save, save as), and manual slider adjustments.
- **[ui_registration.py](ui_registration.py)**: UI. Renders registration sliders, Center of Rotation (CoR) pivot settings, matrix views, and toggles for fast preview/auto-resample. Handles Beginner Mode UI visibility logic.

---

## 1. Transform State Ownership & Workspace Serialization

Registration state lives in the **core** layout model under `ViewState.space` (an instance of the `SpatialEngine` class defined in [geometry.py](../../maths/geometry.py)):

- The actual transform is a `SimpleITK.Euler3DTransform`.
- `vs.space.is_active` flags whether the transform is currently active.
- **Workspace-Only Serialization**: In [control_registration.py](control_registration.py), `serialize_image_state` and `restore_image_state` inspect the call stack using Python's `inspect` module:
  - They only serialize and restore transform parameters if triggered during workspace operations (`save_workspace` or `load_workspace_sequence`).
  - Standard/automatic image history saves (which call the same hook) receive `{}` to prevent dynamic registration matrices from polluting the global history database or loading out of context.

---

## 2. Real-Time 2D Slice Preview

Calculating full 3D resamples is computationally heavy and causes UI stuttering when the user drags the sliders. To solve this, the plugin implements a two-stage rendering strategy:

1. **Fast 2D Affine Preview**: As the user drags the X, Y, Z translation or rotation sliders, the controller pushes preview jobs to a thread-safe `queue.Queue`.
2. **Background Preview Worker**: A daemon thread running `_preview_worker_loop` processes these jobs in the background. It calculates 2D affine projections for the currently visible slices and updates the display cache without blocking the main rendering loop.

---

## 3. Debounced 3D Resampling

When the transform values change, a full 3D resample of the volume is required for accurate interpolation and crosshair tracking:

- **Throttling Timer**: Instead of resampling on every slider tick, changes trigger `_schedule_auto_resample(vs_id)`.
- **Debounce Logic**: This schedules a `threading.Timer` (default delay 0.35s). If the user moves a slider again before the timer fires, the previous timer is cancelled and a new one is created.
- Once the user stops moving the slider, the timer fires `_fire_auto_resample`, which spawns a background thread to compute the 3D resampled volume array and updates the display via `api.resample_image`.

---

## 4. Baking Transforms (In-Place Resampling)

"Baking" permanently applies the current transform to the image, resampling the voxel grid into a new native physical space:

- **Tombstone Pattern**: To avoid memory corruption and segmentation faults, the backend detaches the old C++ SimpleITK image and array views (the tombstone pattern) before swapping in the newly resampled image and array views.
- **Identity Reset**: After resampling, the registration transform is reset to identity, `vs.space.is_active` is set to `False`, and a new `SpatialEngine` is instantiated for the volume.
- **Dependent Overlays**: Baking automatically triggers a rebuild on any other open images (such as fusion overlay layers) that depend on this image's coordinates to keep them spatially aligned.

---

## 5. UI Renaming ("Transform")

To make the application more accessible to clinicians and non-technical users:
- The user-facing label of the plugin is renamed from `"Registration"` to `"Transform"`.
- However, all underlying filenames, directory structures, class names, and internal plugin identifiers (`registration_plugin`) are preserved to prevent breaking imports or saved workspace compatibility.

---

## 6. Beginner Mode UI Hiding

When `api.is_beginner_mode` is `True`, the UI dynamically hides advanced registration tools to avoid overwhelming new users:
- **Hidden Groups**: The Center of Rotation (CoR) controls, the 3D Affine Matrix text display, and advanced operations (Invert, Commit/Bake, Save, Reload) are wrapped in named groups that set `show=False`.
- **Stepped Sliders**: Translation and rotation sliders are configured with stepped behavior and help tooltip buttons describing their function.
