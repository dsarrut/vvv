# Plugin System — Developer Guide

## Discovery

`discover_plugins()` in `src/vvv/plugins/__init__.py` auto-discovers any class in a `plugins/<name>/` subdirectory that exposes the plugin contract. No registration step needed — just drop a new folder in.

Classes are accepted if they have `plugin_id`, `label`, `create_ui(parent, api)`, and `update(api)`. They are sorted by `order` (default 999), then `plugin_id`.

**`order < 0` disables a plugin** — it is instantiated (to check the interface) but not added to the active list and never shown in the UI. Use this to keep a plugin in the codebase without loading it (e.g. `order = -1` for debug/WIP plugins).

## Plugin Contract

Every plugin must implement:

```python
class MyPlugin:
    plugin_id: str       # unique, used as DPG tag prefix
    label: str           # shown in sidebar navigation
    description: str     # tooltip
    order: int           # sort position (optional, default 999)

    def create_ui(self, parent, api: PluginAPI) -> None: ...
    def update(self, api: PluginAPI) -> None: ...
    def on_image_loaded(self, image_id: str) -> None: ...
    def on_image_removed(self, image_id: str) -> None: ...
    def serialize_image_state(self, image_id: str) -> dict: ...
    def restore_image_state(self, image_id: str, data: dict) -> None: ...
    def save_settings(self, api: PluginAPI) -> None: ...
    def load_settings(self, api: PluginAPI) -> None: ...
    def destroy(self) -> None: ...
```

**`update(api)`** — called by `gui.py` only when `plugin_api.is_dirty` is true. Do not re-check `is_dirty` inside the plugin.

**`serialize_image_state(image_id) -> dict`** — called by history and workspace save for every loaded image. Return a JSON-serializable dict of plugin-specific per-image state (e.g. histogram view preferences). Return `{}` if nothing to save.

**`restore_image_state(image_id, data)`** — called after `on_image_loaded`, with the dict previously returned by `serialize_image_state`. Apply saved values to the plugin's per-image state. Called for both history and workspace restore paths.

**`on_image_loaded(image_id)`** — called after a base image is fully registered (volumes and view_states are populated). Not called for auto-loaded overlays. Use it to initialize per-image plugin state (e.g. create a per-image state entry keyed by `image_id`).

**`on_image_removed(image_id)`** — called immediately after an image is removed from the app (view state and volume already deleted). Use it to close popup windows that were showing that image, clear per-image caches, and stop any background computation for that image.

**`save_settings(api)` / `load_settings(api)`** — called at app shutdown and after `create_ui` at startup respectively. Use `api.get_settings(plugin_id)` / `api.set_settings(plugin_id, data)` to read/write a dict in the shared settings file. Store per-session UI preferences (style defaults, last-used values). Do not store per-image state — that belongs to workspace/history.

**`destroy()`** — called during shutdown before `dpg.destroy_context()`, after `save_settings`. Use it to stop background threads or release non-DPG resources. DPG items are destroyed automatically by the context.

## Internal 3-Class Convention

Each plugin is expected to be split into three files:

```
plugins/myplugin/
    plugin_myplugin.py   # Plugin class — orchestrates the other two, implements the contract
    ui_myplugin.py       # UI class    — builds DearPyGui widgets
    control_myplugin.py  # Controller  — manages state, DPG sync, callbacks
```

**Plugin class** — thin shell. Constructs controller and UI, wires them together, delegates `create_ui` and `update` calls.

**UI class** — pure widget construction. Receives `plugin_id` and a controller reference. Calls `dpg.add_*` functions only. No state logic.

**Controller class** — all state and callbacks. Holds `self._api` (bound at `create_ui` time via `bind(api)`). Reads from `api.*`, writes back via `api.request_refresh()`, `api.propagate_window_level()`, etc.

### DPG tag namespacing

All DPG tags must be prefixed with `plugin_id` to avoid collisions. Use a helper:

```python
def _t(self, name: str) -> str:
    return f"{self._plugin_id}_{name}"
```

## PluginAPI — What Plugins Can Use

Plugins access the app only through `PluginAPI`. Never hold a reference to `gui` or `controller` directly.

| Method | Returns |
|--------|---------|
| `get_active_viewer()` | current `SliceViewer` |
| `get_viewers()` | dict of all viewers |
| `get_volumes()` | dict of loaded volumes |
| `get_view_states()` | dict of `ViewState` objects |
| `get_ui_config()` | theme/color config dict |
| `get_image_display_name(image_id)` | `(name, is_outdated)` |
| `get_active_image_name()` | display name of current image |
| `get_crosshair_world()` | `[x, y, z]` physical coords |
| `get_mouse_position()` | `[px, py]` screen coords |
| `is_dirty` | bool — state changed this frame |
| `is_beginner_mode` | bool |
| `request_refresh()` | set `ui_needs_refresh = True` |
| `notify(msg, color)` | show status notification |
| `propagate_window_level(image_id)` | sync WW/WL to linked viewers |
| `propagate_colormap(image_id)` | sync colormap to linked viewers |
| `set_async_status(msg)` | set status from a background thread |
| `create_labeled_field(label, tag, help_text)` | build a readonly form row |
| `get_settings(namespace)` | `dict` — load plugin settings by namespace |
| `set_settings(namespace, data)` | write plugin settings dict by namespace |

## Adding a New Plugin

1. Create `src/vvv/plugins/myplugin/`
2. Add `__init__.py` that exports your Plugin class
3. Implement the three-class structure above
4. Run the app — discovery is automatic
