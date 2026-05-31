from typing import Optional, Dict
import dearpygui.dearpygui as dpg
from vvv.plugins.plugin_api import PluginAPI, PluginTagMixin
from vvv.utils import ViewMode


class MIPViewerState:
    def __init__(self):
        self.mip_enabled = False
        self.projection_axis = "Y"
        self.depth_cueing = 0.0
        self.invert_contrast = False
        self.rotation_angles = {"X": 0.0, "Y": 0.0, "Z": 0.0}
        self.rotation_step = 5.0


class MIPPluginController(PluginTagMixin):
    def __init__(self, plugin_id: str):
        self._plugin_id = plugin_id
        self._api: Optional[PluginAPI] = None
        self._ui = None
        self._states: Dict[str, Dict[str, MIPViewerState]] = {}

    def bind(self, api: PluginAPI) -> None:
        self._api = api

    def bind_ui(self, ui) -> None:
        self._ui = ui

    def get_viewer_state(self, image_id: str, viewer_tag: str) -> MIPViewerState:
        tag = viewer_tag.upper()
        if image_id not in self._states:
            self._states[image_id] = {}
        if tag not in self._states[image_id]:
            self._states[image_id][tag] = MIPViewerState()
        return self._states[image_id][tag]

    def get_image_state(self, image_id: str) -> MIPViewerState:
        # Compatibility wrapper returning state for "V1"
        return self.get_viewer_state(image_id, "V1")

    def update(self, api: PluginAPI) -> None:
        if self._ui:
            self._ui.update_ui(api)

    def on_image_loaded(self, image_id: str) -> None:
        # Pre-initialize states for standard viewer tags
        for tag in ["V1", "V2", "V3", "V4"]:
            _ = self.get_viewer_state(image_id, tag)

    def on_image_removed(self, image_id: str) -> None:
        self._states.pop(image_id, None)

    def serialize_image_state(self, image_id: str, context: str = "history") -> dict:
        states_dict = self._states.get(image_id)
        if not states_dict:
            return {}
        serialized = {}
        for tag, state in states_dict.items():
            serialized[tag] = {
                "mip_enabled": state.mip_enabled,
                "projection_axis": state.projection_axis,
                "depth_cueing": state.depth_cueing,
                "invert_contrast": state.invert_contrast,
                "rotation_angles": state.rotation_angles.copy(),
                "rotation_step": state.rotation_step,
            }
        # For backward compatibility, include V1 values at the root level
        if "V1" in states_dict:
            v1_state = states_dict["V1"]
            serialized.update({
                "mip_enabled": v1_state.mip_enabled,
                "projection_axis": v1_state.projection_axis,
                "depth_cueing": v1_state.depth_cueing,
                "invert_contrast": v1_state.invert_contrast,
                "rotation_angles": v1_state.rotation_angles.copy(),
                "rotation_step": v1_state.rotation_step,
            })
        return serialized

    def restore_image_state(self, image_id: str, data: dict, context: str = "history") -> None:
        has_viewer_keys = any(tag in data for tag in ["V1", "V2", "V3", "V4"])
        if has_viewer_keys:
            for tag in ["V1", "V2", "V3", "V4"]:
                if tag in data:
                    state = self.get_viewer_state(image_id, tag)
                    self._restore_single_state(state, data[tag])
        else:
            # Old format flat dictionary. Restore across all standard viewers.
            for tag in ["V1", "V2", "V3", "V4"]:
                state = self.get_viewer_state(image_id, tag)
                self._restore_single_state(state, data)

    def _restore_single_state(self, state: MIPViewerState, data: dict) -> None:
        state.mip_enabled = data.get("mip_enabled", state.mip_enabled)
        state.projection_axis = data.get("projection_axis", state.projection_axis)
        
        raw_depth = data.get("depth_cueing", state.depth_cueing)
        if isinstance(raw_depth, bool):
            state.depth_cueing = 0.5 if raw_depth else 0.0
        else:
            state.depth_cueing = float(raw_depth)
            
        state.invert_contrast = data.get("invert_contrast", state.invert_contrast)
        if "rotation_angles" in data:
            restored = data["rotation_angles"]
            if isinstance(restored, dict):
                for axis in ["X", "Y", "Z"]:
                    state.rotation_angles[axis] = float(restored.get(axis, state.rotation_angles[axis]))
        elif "rotation_angle" in data:
            val = float(data["rotation_angle"])
            for axis in ["X", "Y", "Z"]:
                state.rotation_angles[axis] = val
        state.rotation_step = float(data.get("rotation_step", state.rotation_step))

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
            state = self.get_viewer_state(viewer.image_id, viewer.tag)
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
            state = self.get_viewer_state(viewer.image_id, viewer.tag)
            state.depth_cueing = float(app_data)
            self._mark_viewer_dirty(viewer)
            self._api.request_refresh()

    def on_invert_toggle(self, sender, app_data, user_data):
        if not self._api:
            return
        viewer = self._api.get_active_viewer()
        if viewer and viewer.image_id:
            state = self.get_viewer_state(viewer.image_id, viewer.tag)
            state.invert_contrast = app_data
            self._api.request_refresh()

    def on_rotation_changed(self, sender, app_data, user_data):
        if not self._api:
            return
        viewer = self._api.get_active_viewer()
        if viewer and viewer.image_id:
            state = self.get_viewer_state(viewer.image_id, viewer.tag)
            from vvv.utils import ViewMode
            orientation_map = {
                ViewMode.AXIAL: "Z",
                ViewMode.CORONAL: "Y",
                ViewMode.SAGITTAL: "Y",
            }
            active_axis = orientation_map.get(viewer.orientation, "Y")
            state.rotation_angles[active_axis] = float(app_data)
            self._mark_viewer_dirty(viewer)
            self._api.request_refresh()

    def on_step_changed(self, sender, app_data, user_data):
        if not self._api:
            return
        viewer = self._api.get_active_viewer()
        if viewer and viewer.image_id:
            state = self.get_viewer_state(viewer.image_id, viewer.tag)
            state.rotation_step = float(app_data)
            self._api.request_refresh()

