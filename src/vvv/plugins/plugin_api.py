import numpy as np


class PluginAPI:
    """Restricted surface area exposed to plugins. Plugins must not hold a reference to gui or controller."""

    def __init__(self, gui):
        self._gui = gui
        self._controller = gui.controller

    @property
    def is_dirty(self):
        if self._controller.ui_needs_refresh:
            return True
        viewer = self._gui.context_viewer
        if not viewer or not viewer.view_state:
            return False
        if viewer.view_state.is_data_dirty:
            return True
        ov_id = viewer.view_state.display.overlay_id
        if ov_id:
            ov_vs = self._controller.view_states.get(ov_id)
            if ov_vs and ov_vs.is_data_dirty:
                return True
        return False

    def get_ui_config(self):
        return self._gui.ui_cfg

    # --- Beginner-mode surface (allows passing api as the `gui` arg to ui_components) ---

    @property
    def ui_cfg(self):
        return self._gui.ui_cfg

    @property
    def is_beginner_mode(self) -> bool:
        return self._gui.is_beginner_mode

    @property
    def beginner_tags(self) -> list:
        return self._gui.beginner_tags

    @property
    def beginner_sliders(self) -> list:
        return self._gui.beginner_sliders

    def create_labeled_field(self, label, tag, help_text=None):
        self._gui.create_labeled_field(label, tag, help_text=help_text)

    def get_active_image_name(self):
        viewer = self._gui.context_viewer
        if viewer and viewer.image_id:
            name, _ = self._controller.get_image_display_name(viewer.image_id)
            return name
        return "None"

    def get_crosshair_world(self):
        viewer = self._gui.context_viewer
        if viewer and viewer.view_state and viewer.view_state.camera.crosshair_phys_coord is not None:
            return viewer.view_state.camera.crosshair_phys_coord
        return [0.0, 0.0, 0.0]

    def get_mouse_position(self):
        if hasattr(self._gui.interaction, "last_mouse_pos"):
            return self._gui.interaction.last_mouse_pos
        return [0, 0]

    def get_active_viewer(self):
        return self._gui.context_viewer

    def get_viewers(self):
        return self._controller.viewers

    def get_volumes(self):
        return self._controller.volumes

    def get_image_display_name(self, image_id):
        return self._controller.get_image_display_name(image_id)

    def get_view_states(self):
        return self._controller.view_states

    def request_refresh(self):
        self._controller.ui_needs_refresh = True

    def notify(self, msg, color=None):
        self._gui.show_status_message(msg, color=color)

    # --- Sync actions (wraps controller internals; keeps plugins off the controller directly) ---

    def propagate_window_level(self, image_id):
        self._controller.sync.propagate_window_level(image_id)

    def propagate_colormap(self, image_id):
        self._controller.sync.propagate_colormap(image_id)

    def set_async_status(self, msg):
        """Set a status message from a background thread (picked up by the main loop)."""
        self._controller.status_message = msg

    # --- Plugin settings (persisted in the app settings file under "plugins.<namespace>") ---

    def get_settings(self, namespace: str) -> dict:
        return self._controller.settings.data.get("plugins", {}).get(namespace, {})

    def set_settings(self, namespace: str, data: dict) -> None:
        self._controller.settings.data.setdefault("plugins", {})[namespace] = data
