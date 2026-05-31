from typing import Optional, Dict
import dearpygui.dearpygui as dpg
from vvv.plugins.plugin_api import PluginAPI, PluginTagMixin
from vvv.utils import ViewMode


class MIPImageState:
    def __init__(self):
        self.mip_enabled = False
        self.projection_axis = "Y"
        self.depth_cueing = 0.0
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
        
        raw_depth = data.get("depth_cueing", state.depth_cueing)
        if isinstance(raw_depth, bool):
            state.depth_cueing = 0.5 if raw_depth else 0.0
        else:
            state.depth_cueing = float(raw_depth)
            
        state.invert_contrast = data.get("invert_contrast", state.invert_contrast)

    def save_settings(self, api: PluginAPI) -> None:
        pass

    def load_settings(self, api: PluginAPI) -> None:
        pass

    def destroy(self) -> None:
        pass

    def _mark_viewer_dirty(self, viewer):
        if viewer:
            if viewer.view_state:
                viewer.view_state.is_data_dirty = True
            viewer.is_viewer_data_dirty = True
            viewer.is_geometry_dirty = True

    def on_mip_toggle(self, sender, app_data, user_data):
        if not self._api:
            return
        viewer = self._api.get_active_viewer()
        if viewer and viewer.image_id:
            state = self.get_image_state(viewer.image_id)
            state.mip_enabled = app_data
            
            # Sync orientation to match projection axis when turning MIP on
            if app_data:
                axis_map = {"Z": ViewMode.AXIAL, "Y": ViewMode.CORONAL, "X": ViewMode.SAGITTAL}
                target_orientation = axis_map.get(state.projection_axis.upper())
                if target_orientation and viewer.orientation != target_orientation:
                    viewer.set_orientation(target_orientation)

            self._mark_viewer_dirty(viewer)
            self._api.request_refresh()

    def on_depth_cueing_changed(self, sender, app_data, user_data):
        if not self._api:
            return
        viewer = self._api.get_active_viewer()
        if viewer and viewer.image_id:
            state = self.get_image_state(viewer.image_id)
            state.depth_cueing = float(app_data)
            self._mark_viewer_dirty(viewer)
            self._api.request_refresh()

    def on_invert_toggle(self, sender, app_data, user_data):
        if not self._api:
            return
        viewer = self._api.get_active_viewer()
        if viewer and viewer.image_id:
            state = self.get_image_state(viewer.image_id)
            state.invert_contrast = app_data
            self._api.request_refresh()

