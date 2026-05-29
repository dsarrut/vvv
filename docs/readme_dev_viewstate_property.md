# How to Add a Property to ViewState

`ViewState` is the per-image display state. It is composed of sub-state objects:

| Sub-state | Purpose | Dirty flag triggered |
|---|---|---|
| `CameraState` | Spatial navigation: zoom, pan, slices, overlays, time | `is_geometry_dirty` |
| `DisplayState` | Rendering parameters: W/L, colormap, overlay opacity/mode | `is_data_dirty` |
| `DVFState` | DVF-specific visualization settings | `is_geometry_dirty` |
| `SpaceState` | Registration transform | — (manual) |

---

## Step-by-step

### 1. Choose the right sub-state

- Affects **which slice is drawn or where**: → `CameraState`
- Affects **how pixels are colored**: → `DisplayState`
- Only relevant when the image is a DVF: → `DVFState`
- Related to transforms: → `SpaceState`

### 2. Declare the type hint at class level

```python
class CameraState:
    my_new_flag: bool
```

This is required — the `__setattr__` override reads class attributes at runtime.

### 3. Initialize with a default in `__init__`

```python
self.my_new_flag = True
```

### 4. Decide on the dirty behavior

Adding the field name to `_GEOM_FIELDS` or `_DATA_FIELDS` makes the setter automatically flip the parent `ViewState`'s dirty flag whenever the value actually changes:

```python
_GEOM_FIELDS = {
    ...
    "my_new_flag",   # add here if a change requires a geometry redraw
}
```

Use `_GEOM_FIELDS` (geometry redraw) when the change affects which polygons/contours/overlays are drawn but not the pixel data itself. Use `_DATA_FIELDS` (data redraw) when the rendered pixels change (W/L, colormap, blending). If neither — the field is pure state with no automatic rendering side-effect.

### 5. Serialize in `to_dict`

```python
def to_dict(self):
    return {
        ...
        "my_new_flag": self.my_new_flag,
    }
```

### 6. Deserialize in `from_dict` with a backward-compatible default

```python
def from_dict(self, d):
    ...
    self.my_new_flag = d.get("my_new_flag", True)  # same default as __init__
```

The `d.get(key, default)` pattern ensures old history/workspace files that don't have the key continue to work correctly.

### 7. Decide on sync

If the property should propagate to viewers in the same sync group, add a propagation call in the relevant controller method (see `sync_manager.py`). Most display toggles do not need sync. Spatial state that affects the crosshair or slice position does.

---

## Example: adding `show_contour` to `CameraState`

```python
# 1. Type hint
class CameraState:
    show_contour: bool

# 2-3. GEOM_FIELDS + init
_GEOM_FIELDS = { ..., "show_contour" }

def __init__(self, volume, parent_vs=None):
    ...
    self.show_contour = True

# 4. to_dict
def to_dict(self):
    return { ..., "show_contour": self.show_contour }

# 5. from_dict
def from_dict(self, d):
    ...
    self.show_contour = d.get("show_contour", True)
```

Setting `vs.camera.show_contour = False` now automatically sets `vs.is_geometry_dirty = True` and queues a redraw on the next `tick()`.

---

## Common mistakes

- **Forgetting `from_dict`**: old workspaces silently break because the field is missing.
- **Wrong dirty flag**: putting a rendering property in `_GEOM_FIELDS` (or vice versa) causes redraws at the wrong level. When in doubt: geometry = layout/structure, data = pixel values.
- **Setting dirty from a background thread**: `is_geometry_dirty` and `is_data_dirty` are not thread-safe. Post back to the main thread via `api.run_on_main_thread(callback)`.
