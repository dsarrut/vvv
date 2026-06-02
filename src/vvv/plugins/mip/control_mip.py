from typing import Optional, Dict
import threading
import numpy as np
import dearpygui.dearpygui as dpg
from vvv.plugins.plugin_api import PluginAPI, PluginTagMixin
from vvv.utils import ViewMode


class MIPViewerState:
    def __init__(self):
        self.mip_enabled = False
        self.projection_axis = "Y"
        self.depth_cueing = 1.0
        self.invert_contrast = False
        self.rotation_angles = {"X": 0.0, "Y": 0.0, "Z": 0.0}
        self.rotation_step = 10.0


class MIPPluginController(PluginTagMixin):
    def __init__(self, plugin_id: str):
        self._plugin_id = plugin_id
        self._api: Optional[PluginAPI] = None
        self._ui = None
        self._states: Dict[str, Dict[str, MIPViewerState]] = {}
        self._caches: Dict[str, dict] = {}
        self._cache_locks: Dict[str, threading.Lock] = {}
        self._precompute_stops: Dict[str, threading.Event] = {}

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
            serialized.update(
                {
                    "mip_enabled": v1_state.mip_enabled,
                    "projection_axis": v1_state.projection_axis,
                    "depth_cueing": v1_state.depth_cueing,
                    "invert_contrast": v1_state.invert_contrast,
                    "rotation_angles": v1_state.rotation_angles.copy(),
                    "rotation_step": v1_state.rotation_step,
                }
            )
        return serialized

    def restore_image_state(
        self, image_id: str, data: dict, context: str = "history"
    ) -> None:
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
                    state.rotation_angles[axis] = float(
                        restored.get(axis, state.rotation_angles[axis])
                    )
        elif "rotation_angle" in data:
            val = float(data["rotation_angle"])
            for axis in ["X", "Y", "Z"]:
                state.rotation_angles[axis] = val
        state.rotation_step = float(data.get("rotation_step", state.rotation_step))

    def save_settings(self, api: PluginAPI) -> None:
        pass

    def load_settings(self, api: PluginAPI) -> None:
        pass

    def clear_viewer_cache(self, viewer_tag: str) -> None:
        tag = viewer_tag.upper()
        if tag in self._precompute_stops:
            self._precompute_stops[tag].set()
        if tag in self._caches:
            with self._cache_locks[tag]:
                self._caches[tag].clear()

    def get_cache_size(self, viewer_tag: str) -> int:
        tag = viewer_tag.upper()
        if tag in self._caches and tag in self._cache_locks:
            with self._cache_locks[tag]:
                return len(self._caches[tag])
        return 0

    def destroy(self) -> None:
        for stop_event in self._precompute_stops.values():
            stop_event.set()
        self._precompute_stops.clear()
        for lock, cache in zip(self._cache_locks.values(), self._caches.values()):
            with lock:
                cache.clear()
        self._caches.clear()
        self._cache_locks.clear()

    def _mark_viewer_dirty(self, viewer):
        if viewer:
            if viewer.view_state:
                viewer.view_state.is_data_dirty = True
            viewer.is_viewer_data_dirty = True
            viewer.is_geometry_dirty = True

    def _sync_to_group(self, source_image_id, apply_fn) -> None:
        """Call apply_fn(state, viewer) for every MIP-enabled viewer in the sync group."""
        if not self._api:
            return
        sync_ids = self._api.get_sync_group_vs_ids(source_image_id, active_only=True)
        viewers = self._api.get_viewers()
        for img_id in sync_ids:
            if img_id == source_image_id:
                continue
            for viewer in viewers.values():
                if viewer.image_id == img_id:
                    target_state = self.get_viewer_state(img_id, viewer.tag)
                    if target_state.mip_enabled:
                        apply_fn(target_state, viewer)
                        self._mark_viewer_dirty(viewer)

    def propagate_rotation(self, source_image_id, rotation_angles: dict) -> None:
        self._sync_to_group(
            source_image_id,
            lambda s, _v: s.rotation_angles.update(rotation_angles),
        )

    def _propagate_display_state(
        self, source_image_id, depth_cueing, invert_contrast
    ) -> None:
        def apply(s, _v):
            if depth_cueing is not None:
                s.depth_cueing = depth_cueing
            if invert_contrast is not None:
                s.invert_contrast = invert_contrast

        self._sync_to_group(source_image_id, apply)

    def on_mip_toggle(self, sender, app_data, user_data):
        if not self._api:
            return
        viewer = self._api.get_active_viewer()
        if viewer and viewer.image_id:
            state = self.get_viewer_state(viewer.image_id, viewer.tag)
            state.mip_enabled = app_data

            # Sync orientation to match projection axis when turning MIP on
            if app_data:
                axis_map = {
                    "Z": ViewMode.AXIAL,
                    "Y": ViewMode.SAGITTAL,
                }
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
            self._propagate_display_state(
                viewer.image_id, depth_cueing=float(app_data), invert_contrast=None
            )
            self._api.request_refresh()

    def on_invert_toggle(self, sender, app_data, user_data):
        if not self._api:
            return
        viewer = self._api.get_active_viewer()
        if viewer and viewer.image_id:
            state = self.get_viewer_state(viewer.image_id, viewer.tag)
            state.invert_contrast = app_data
            self._mark_viewer_dirty(viewer)
            self._api.request_refresh()

    def on_rotation_changed(self, sender, app_data, user_data):
        if not self._api:
            return
        viewer = self._api.get_active_viewer()
        if viewer and viewer.image_id:
            state = self.get_viewer_state(viewer.image_id, viewer.tag)
            orientation_map = {
                ViewMode.AXIAL: "Z",
                ViewMode.CORONAL: "Y",
                ViewMode.SAGITTAL: "Y",
            }
            active_axis = orientation_map.get(viewer.orientation, "Y")
            state.rotation_angles[active_axis] = float(app_data)
            self._mark_viewer_dirty(viewer)
            self.propagate_rotation(viewer.image_id, state.rotation_angles)
            self._api.request_refresh()

    def on_step_changed(self, sender, app_data, user_data):
        if not self._api:
            return
        viewer = self._api.get_active_viewer()
        if viewer and viewer.image_id:
            state = self.get_viewer_state(viewer.image_id, viewer.tag)
            state.rotation_step = float(app_data)
            self._api.request_refresh()

    def on_rotation_step_button(self, _sender, _app_data, user_data):
        if not self._api:
            return
        viewer = self._api.get_active_viewer()
        if not viewer or not viewer.image_id:
            return
        state = self.get_viewer_state(viewer.image_id, viewer.tag)
        orientation_map = {
            ViewMode.AXIAL: "Z",
            ViewMode.CORONAL: "Y",
            ViewMode.SAGITTAL: "Y",
        }
        active_axis = orientation_map.get(viewer.orientation, "Y")
        current = state.rotation_angles.get(active_axis, 0.0)
        new_val = max(
            -180.0, min(180.0, current + state.rotation_step * user_data["dir"])
        )
        state.rotation_angles[active_axis] = round(new_val, 1)
        dpg.set_value(user_data["tag"], new_val)
        self._mark_viewer_dirty(viewer)
        self.propagate_rotation(viewer.image_id, state.rotation_angles)
        self._api.request_refresh()

    def on_step_size_button(self, _sender, _app_data, user_data):
        if not self._api:
            return
        viewer = self._api.get_active_viewer()
        if not viewer or not viewer.image_id:
            return
        state = self.get_viewer_state(viewer.image_id, viewer.tag)
        new_val = max(1.0, min(45.0, state.rotation_step + user_data["dir"]))
        state.rotation_step = round(new_val, 1)
        dpg.set_value(user_data["tag"], new_val)
        self._api.request_refresh()

    def get_mip_projection(
        self,
        viewer,
        data_3d,
        time_idx,
        orientation,
        depth_cueing,
        current_angle,
        proj_axis,
        mip_state,
        extra_layers=None
    ) -> np.ndarray:
        tag = viewer.tag.upper()
        if tag not in self._caches:
            self._caches[tag] = {}
            self._cache_locks[tag] = threading.Lock()
            self._precompute_stops[tag] = threading.Event()
            
        cache_dict = self._caches[tag]
        cache_lock = self._cache_locks[tag]
        
        # Build cache key
        cache_key = (viewer.image_id, time_idx, orientation, depth_cueing, current_angle, id(data_3d))
        
        with cache_lock:
            preview = cache_dict.get(cache_key)
            
        if preview is None:
            # Miss: compute projection synchronously
            from vvv.plugins.mip.math_mip import compute_mip_projection
            if data_3d.ndim == 4:
                t = min(time_idx, data_3d.shape[0] - 1)
                d3d = data_3d[t]
            else:
                d3d = data_3d
                
            if d3d.ndim == 3:
                mip_raw = compute_mip_projection(
                    d3d, axis=proj_axis,
                    depth_cueing=depth_cueing > 0.0,
                    depth_cueing_strength=depth_cueing,
                    rotation_angle=current_angle,
                )
                preview = (
                    np.ascontiguousarray(mip_raw)
                    if orientation == ViewMode.AXIAL
                    else np.ascontiguousarray(np.flipud(mip_raw))
                )
                
                with cache_lock:
                    if len(cache_dict) >= 400:  # _MIP_CACHE_MAX
                        cache_dict.pop(next(iter(cache_dict)), None)
                    cache_dict[cache_key] = preview
            
            # Start background precomputation for other angles if extra_layers is provided
            if extra_layers is not None and d3d.ndim == 3:
                self._start_mip_precompute(
                    viewer=viewer,
                    data_3d=d3d,
                    proj_axis=proj_axis,
                    depth_cueing=depth_cueing,
                    center_angle=current_angle,
                    rotation_step=mip_state.rotation_step,
                    time_idx=time_idx,
                    orientation=orientation,
                    extra_layers=extra_layers
                )
                
        return preview

    def _start_mip_precompute(
        self, viewer, data_3d, proj_axis, depth_cueing,
        center_angle, rotation_step, time_idx, orientation,
        extra_layers=None
    ):
        tag = viewer.tag.upper()
        stop_event = self._precompute_stops[tag]
        stop_event.set()
        
        new_stop = threading.Event()
        self._precompute_stops[tag] = new_stop
        
        image_id = viewer.image_id
        cache_lock = self._cache_locks[tag]
        cache_dict = self._caches[tag]
        step = max(0.1, rotation_step)
        extra_layers = extra_layers or []
        
        # Build all angles in the full rotation ordered by distance from current
        n = max(1, round(360.0 / step))
        all_angles = []
        for i in range(1, n + 1):
            for sign in (1, -1):
                a = center_angle + sign * i * step
                while a > 180.0:
                    a -= 360.0
                while a <= -180.0:
                    a += 360.0
                all_angles.append(round(a, 2))
                
        def _compute_and_cache(d3d, key):
            from vvv.plugins.mip.math_mip import compute_mip_projection
            try:
                mip_raw = compute_mip_projection(
                    d3d, axis=proj_axis,
                    depth_cueing=depth_cueing > 0.0,
                    depth_cueing_strength=depth_cueing,
                    rotation_angle=key[4],
                )
                preview = (
                    np.ascontiguousarray(mip_raw)
                    if orientation == ViewMode.AXIAL
                    else np.ascontiguousarray(np.flipud(mip_raw))
                )
                with cache_lock:
                    if key not in cache_dict:
                        if len(cache_dict) >= 400:
                            cache_dict.pop(next(iter(cache_dict)), None)
                        cache_dict[key] = preview
                        viewer.controller.ui_needs_refresh = True
            except Exception:
                pass
                
        def _run():
            for angle in all_angles:
                if new_stop.is_set():
                    return
                    
                # Base layer
                base_key = (image_id, time_idx, orientation, depth_cueing, angle, id(data_3d))
                with cache_lock:
                    base_cached = base_key in cache_dict
                if not base_cached:
                    if new_stop.is_set():
                        return
                    _compute_and_cache(data_3d, base_key)
                    
                # Extra layers
                for layer_data, layer_id, layer_time_idx in extra_layers:
                    if new_stop.is_set():
                        return
                    layer_key = (layer_id, layer_time_idx, orientation, depth_cueing, angle, id(layer_data))
                    with cache_lock:
                        layer_cached = layer_key in cache_dict
                    if not layer_cached:
                        if new_stop.is_set():
                            return
                        _compute_and_cache(layer_data, layer_key)
                        
        threading.Thread(target=_run, daemon=True).start()
