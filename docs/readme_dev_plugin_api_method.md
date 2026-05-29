# How to Add a Method to PluginAPI

`PluginAPI` (`src/vvv/plugins/plugin_api.py`) is the only surface plugins are allowed to touch. It delegates to controller subsystems and hides all internal structure from plugin code.

**Rule:** if a plugin needs an operation that `PluginAPI` doesn't expose, add a method there — do not let the plugin reach into `api._controller` or `api._gui` directly. A violation there is an anti-pattern that creates hidden coupling and breaks isolation.

---

## When to add a method

- A plugin needs to read or mutate controller state that isn't already exposed.
- A plugin needs to trigger an operation in a controller subsystem (`roi`, `profiles`, `sync`, `file`, etc.).
- A plugin generates a new image and wants to mount it into the viewer (use `mount_generated_image`).

## When NOT to add a method

- The data is already accessible via an existing method (`get_volumes()`, `get_view_states()`, etc.).
- The operation is purely UI — it belongs in the plugin's own controller or UI layer.

---

## Step-by-step

### 1. Identify which controller subsystem owns the operation

```
controller.roi        → ROI operations
controller.profiles   → profile extraction
controller.sync       → sync group propagation
controller.file       → disk I/O
controller.contours   → contour add/remove
controller.volumes    → loaded volume dict (read via get_volumes())
controller.view_states → view state dict (read via get_view_states())
```

### 2. Add a thin wrapper in `PluginAPI`

Group it with similar methods under the relevant comment block.

```python
# --- ROI operations ---

def my_new_operation(self, image_id: str, some_arg) -> SomeType:
    return self._controller.roi.my_new_operation(image_id, some_arg)
```

Keep wrappers thin. `PluginAPI` is a boundary, not a logic layer. If you find yourself writing non-trivial logic in `PluginAPI`, it belongs in the controller subsystem instead.

### 3. Don't expose mutable internal dicts directly

Avoid returning raw references to internal dicts that a plugin could accidentally mutate in unexpected ways. Prefer returning specific values or copies when the internal structure is sensitive. (`get_volumes()` and `get_view_states()` are intentional exceptions — plugins need broad read access.)

### 4. Update `PLUGIN_CHECKLIST.md`

If plugins are expected to call this new method (rather than it being a low-level utility), add it to the relevant checklist item so future plugin authors know to use it:

```markdown
- [ ] Contours: use `api.add_contour(image_id, roi)` and `api.remove_contour(image_id, roi_id)`
```

### 5. Tests

Only add a test in `tests/test_plugin_api.py` if there is non-trivial logic in the wrapper (argument transformation, error handling, conditional branching). A test for a one-line delegate is noise. The underlying controller subsystem's own tests cover the real logic.

---

## Example: `mount_generated_image`

A plugin that creates a new volume from processing output (e.g. the threshold plugin) needs to register it and assign it to the active viewer. The operation touches four internal fields and calls `notify_plugins_image_loaded`. This belongs in `PluginAPI`, not in the plugin:

```python
# In PluginAPI:
def mount_generated_image(self, new_vol, new_vs) -> str:
    """Register a newly created volume+view_state and assign it to the active viewer."""
    new_id = str(self._controller.next_image_id)
    self._controller.next_image_id += 1
    self._controller.volumes[new_id] = new_vol
    self._controller.view_states[new_id] = new_vs
    viewer = self._gui.context_viewer
    if viewer:
        self._controller.layout[viewer.tag] = new_id
    self._gui.notify_plugins_image_loaded(new_id)
    return new_id
```

The plugin calls `api.mount_generated_image(new_vol, new_vs)` with no knowledge of `controller.next_image_id`, `controller.layout`, or `gui.notify_plugins_image_loaded`.

---

## Common mistakes

- **Returning `self._controller.some_dict` directly**: the plugin can then mutate internal state unpredictably. Return a copy or a value, not the dict itself.
- **Adding logic to the wrapper**: if the wrapper grows beyond a line or two of delegation, the logic belongs in the subsystem, not in `PluginAPI`.
- **Forgetting the checklist**: the method exists but plugin authors don't know to use it, so they reach into `_controller` anyway.
