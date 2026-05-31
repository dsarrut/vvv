from typing import Optional, Dict
import dearpygui.dearpygui as dpg
from vvv.plugins.plugin_api import PluginAPI, PluginTagMixin


class MIPImageState:
    def __init__(self):
        self.mip_enabled = False
        self.projection_axis = "Y"
        self.depth_cueing = False
        self.invert_contrast = False


class MIPPluginController(PluginTagMixin):
    def __init__(self, plugin_id: str):
        self._plugin_id = plugin_id
        self._api: Optional[PluginAPI] = None
        self._ui = None
        self._states: Dict[str, MIPImageState] = {}

    def bind(self, api: PluginAPI) -> None:
        self._api = api

    def bind_ui(self, ui) -> None:
        self._ui = ui

    def get_image_state(self, image_id: str) -> MIPImageState:
        if image_id not in self._states:
            self._states[image_id] = MIPImageState()
        return self._states[image_id]

    def update(self, api: PluginAPI) -> None:
        if self._ui:
            self._ui.update_ui(api)

    def on_image_loaded(self, image_id: str) -> None:
        _ = self.get_image_state(image_id)

    def on_image_removed(self, image_id: str) -> None:
        self._states.pop(image_id, None)

    def serialize_image_state(self, image_id: str, context: str = "history") -> dict:
        state = self._states.get(image_id)
        if state:
            return {
                "mip_enabled": state.mip_enabled,
                "projection_axis": state.projection_axis,
                "depth_cueing": state.depth_cueing,
                "invert_contrast": state.invert_contrast,
            }
        return {}

    def restore_image_state(self, image_id: str, data: dict, context: str = "history") -> None:
        state = self.get_image_state(image_id)
        state.mip_enabled = data.get("mip_enabled", state.mip_enabled)
        state.projection_axis = data.get("projection_axis", state.projection_axis)
        state.depth_cueing = data.get("depth_cueing", state.depth_cueing)
        state.invert_contrast = data.get("invert_contrast", state.invert_contrast)

    def save_settings(self, api: PluginAPI) -> None:
        pass

    def load_settings(self, api: PluginAPI) -> None:
        pass

    def destroy(self) -> None:
        pass

    def on_mip_toggle(self, sender, app_data, user_data):
        if not self._api:
            return
        viewer = self._api.get_active_viewer()
        if viewer and viewer.image_id:
            state = self.get_image_state(viewer.image_id)
            state.mip_enabled = app_data
            self._api.request_refresh()

    def on_axis_changed(self, sender, app_data, user_data):
        if not self._api:
            return
        viewer = self._api.get_active_viewer()
        if viewer and viewer.image_id:
            state = self.get_image_state(viewer.image_id)
            state.projection_axis = app_data
            self._api.request_refresh()

    def on_depth_cueing_toggle(self, sender, app_data, user_data):
        if not self._api:
            return
        viewer = self._api.get_active_viewer()
        if viewer and viewer.image_id:
            state = self.get_image_state(viewer.image_id)
            state.depth_cueing = app_data
            self._api.request_refresh()

    def on_invert_toggle(self, sender, app_data, user_data):
        if not self._api:
            return
        viewer = self._api.get_active_viewer()
        if viewer and viewer.image_id:
            state = self.get_image_state(viewer.image_id)
            state.invert_contrast = app_data
            self._api.request_refresh()
