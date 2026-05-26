import json
import math
from typing import Optional
import numpy as np
import dearpygui.dearpygui as dpg
from vvv.plugins.plugin_api import PluginAPI, PluginTagMixin
from vvv.utils import ViewMode, voxel_to_slice, slice_to_voxel
from vvv.ui.file_dialog import save_file_dialog


class ProfilePluginController(PluginTagMixin):
    """Controller for interactive profiles plugin."""

    def __init__(self, plugin_id: str):
        self._plugin_id = plugin_id
        self._api: Optional[PluginAPI] = None
        self._ui = None

    def bind(self, api: PluginAPI) -> None:
        self._api = api

    def bind_ui(self, ui) -> None:
        self._ui = ui

    def update(self, api: PluginAPI) -> None:
        if self._ui:
            self._ui.update_ui(api)

    def on_image_loaded(self, image_id: str) -> None:
        pass

    def on_image_removed(self, image_id: str) -> None:
        if self._api:
            vs = self._api.get_view_states().get(image_id)
            if vs:
                for p_id in vs.profiles:
                    win_tag = self._t(f"plot_win_{p_id}")
                    if dpg.does_item_exist(win_tag):
                        dpg.delete_item(win_tag)
        if self._ui:
            self._ui._last_profile_key = None

    def serialize_image_state(self, image_id: str) -> dict:
        if self._api:
            vs = self._api.get_view_states().get(image_id)
            if vs:
                for p_id, profile in vs.profiles.items():
                    win_tag = self._t(f"plot_win_{p_id}")
                    if dpg.does_item_exist(win_tag):
                        profile.plot_position = dpg.get_item_pos(win_tag)
        return {}

    def restore_image_state(self, image_id: str, data: dict) -> None:
        pass

    def save_settings(self, api: PluginAPI) -> None:
        pass

    def load_settings(self, api: PluginAPI) -> None:
        pass

    def destroy(self) -> None:
        if self._api:
            for vs in self._api.get_view_states().values():
                for p_id in vs.profiles:
                    win_tag = self._t(f"plot_win_{p_id}")
                    if dpg.does_item_exist(win_tag):
                        dpg.delete_item(win_tag)

    # --- UI Interactions and Callbacks ---

    def on_btn_add_clicked(self, sender, app_data, user_data):
        if not self._api:
            return
        viewer = self._api.get_active_viewer()
        if not viewer or not viewer.image_id:
            self._api.notify("Please load an image first.")
            return
        viewer.on_key_press(dpg.mvKey_P)

    def on_color_changed(self, sender, app_data, user_data):
        api = self._api
        if not api:
            return
        viewer = api.get_active_viewer()
        if not viewer or not viewer.view_state:
            return
        profile = viewer.view_state.profiles.get(user_data)
        if profile:
            profile.color = [int(c * 255) for c in app_data[:4]]
            viewer.view_state.is_geometry_dirty = True
            api.request_refresh()

    def on_profile_name_changed(self, sender, app_data, user_data):
        api = self._api
        if not api:
            return
        viewer = api.get_active_viewer()
        if not viewer or not viewer.view_state:
            return
        profile = viewer.view_state.profiles.get(user_data)
        if profile:
            profile.name = app_data
            win_tag = self._t(f"plot_win_{profile.id}")
            if dpg.does_item_exist(win_tag):
                image_name, _ = api.get_image_display_name(viewer.image_id)
                dpg.configure_item(win_tag, label=f"Profile: {profile.name} [{image_name}]")
            api.request_refresh()

    def on_delete_clicked(self, sender, app_data, user_data):
        api = self._api
        if not api:
            return
        viewer = api.get_active_viewer()
        if not viewer or not viewer.view_state:
            return
        profile_id = user_data
        if profile_id in viewer.view_state.profiles:
            del viewer.view_state.profiles[profile_id]

            win_tag = self._t(f"plot_win_{profile_id}")
            if dpg.does_item_exist(win_tag):
                dpg.delete_item(win_tag)

            viewer.view_state.is_geometry_dirty = True
            api.request_refresh()

    def on_align_clicked(self, sender, app_data, user_data):
        api = self._api
        if not api:
            return
        viewer = api.get_active_viewer()
        if not viewer or not viewer.view_state:
            return

        p_id, direction = user_data
        vs = viewer.view_state
        p = vs.profiles.get(p_id)
        if not p:
            return

        is_buf = viewer._is_buffered()
        shape = viewer.get_slice_shape()

        v1 = vs.world_to_display(p.pt1_phys, is_buffered=is_buf)
        v2 = vs.world_to_display(p.pt2_phys, is_buffered=is_buf)

        sx1, sy1 = voxel_to_slice(v1[0], v1[1], v1[2], viewer.orientation, shape)
        sx2, sy2 = voxel_to_slice(v2[0], v2[1], v2[2], viewer.orientation, shape)

        cx, cy = (sx1 + sx2) / 2.0, (sy1 + sy2) / 2.0
        length = math.hypot(sx2 - sx1, sy2 - sy1)

        if direction == "h":
            sx1, sy1 = cx - length / 2.0, cy
            sx2, sy2 = cx + length / 2.0, cy
        else:
            sx1, sy1 = cx, cy - length / 2.0
            sx2, sy2 = cx, cy + length / 2.0

        v1_new = slice_to_voxel(sx1, sy1, viewer.slice_idx, viewer.orientation, shape)
        v2_new = slice_to_voxel(sx2, sy2, viewer.slice_idx, viewer.orientation, shape)

        p.pt1_phys = vs.display_to_world(v1_new, is_buffered=is_buf)
        p.pt2_phys = vs.display_to_world(v2_new, is_buffered=is_buf)
        p.orientation = viewer.orientation
        p.slice_idx = viewer.slice_idx

        vs.is_geometry_dirty = True
        if self._ui:
            self._ui.update_plot_header(p)
            self._ui.update_plot_info(p)
            self._ui.refresh_plot_series(p)
        api.request_refresh()

    def on_snap_clicked(self, sender, app_data, user_data):
        api = self._api
        if not api:
            return
        viewer = api.get_active_viewer()
        if not viewer or not viewer.view_state:
            return

        p_id = user_data
        vs = viewer.view_state
        p = vs.profiles.get(p_id)
        if not p:
            return

        v1 = vs.world_to_display(p.pt1_phys, is_buffered=False)
        v2 = vs.world_to_display(p.pt2_phys, is_buffered=False)

        if v1 is not None and v2 is not None:
            v1_snapped = np.round(v1)
            v2_snapped = np.round(v2)

            p.pt1_phys = vs.display_to_world(v1_snapped, is_buffered=False)
            p.pt2_phys = vs.display_to_world(v2_snapped, is_buffered=False)

            vs.is_geometry_dirty = True
            if self._ui:
                self._ui.update_plot_info(p)
                self._ui.refresh_plot_series(p)
            api.request_refresh()

    def on_goto_clicked(self, sender, app_data, user_data):
        api = self._api
        if not api:
            return
        viewer = api.get_active_viewer()
        if not viewer or not viewer.view_state:
            return
        profile = viewer.view_state.profiles.get(user_data)
        if not profile:
            return

        vs = viewer.view_state
        viewer.set_orientation(profile.orientation)

        mid_phys = (profile.pt1_phys + profile.pt2_phys) / 2.0
        length_mm = np.linalg.norm(profile.pt2_phys - profile.pt1_phys)

        win_w = viewer.quad_w - (viewer.mapper.margin_left * 2)
        win_h = viewer.quad_h - (viewer.mapper.margin_top * 2)
        if length_mm > 1e-5 and win_w > 0 and win_h > 0:
            target_ppm = (min(win_w, win_h) * 0.60) / length_mm
            vs.camera.target_ppm = target_ppm

        vs.camera.target_center = mid_phys
        vs.update_crosshair_from_phys(mid_phys)

        api.propagate_sync(viewer.image_id)
        api.request_refresh()

    def on_change_slice_clicked(self, sender, app_data, user_data):
        api = self._api
        if not api:
            return
        p_id, delta = user_data
        viewer = api.get_active_viewer()
        if not viewer or not viewer.view_state:
            return
        vs = viewer.view_state
        p = vs.profiles.get(p_id)
        if not p:
            return

        is_buf = viewer._is_buffered()
        v1 = vs.world_to_display(p.pt1_phys, is_buffered=is_buf)
        v2 = vs.world_to_display(p.pt2_phys, is_buffered=is_buf)

        v_idx, _, _, _ = viewer._ORIENTATION_MAP.get(
            p.orientation, (None, 0, None, None)
        )
        if v_idx is None:
            return

        max_s = viewer.get_display_num_slices()
        new_idx = np.clip(p.slice_idx + delta, 0, max_s - 1)
        if new_idx == p.slice_idx:
            return

        actual_delta = new_idx - p.slice_idx
        v1[v_idx] += actual_delta
        v2[v_idx] += actual_delta
        p.slice_idx = int(new_idx)

        p.pt1_phys = vs.display_to_world(v1, is_buffered=is_buf)
        p.pt2_phys = vs.display_to_world(v2, is_buffered=is_buf)

        viewer.slice_idx = p.slice_idx
        api.propagate_sync(viewer.image_id)

        vs.is_geometry_dirty = True
        if self._ui:
            self._ui.update_plot_header(p)
            self._ui.update_plot_info(p)
            self._ui.refresh_plot_series(p)
        api.request_refresh()

    def on_profile_coord_edited(self, sender, app_data, user_data):
        api = self._api
        if not api:
            return
        viewer = api.get_active_viewer()
        if not viewer or not viewer.view_state:
            return
        p_id, pt_idx = user_data["id"], user_data["pt"]
        p = viewer.view_state.profiles.get(p_id)
        if p:
            new_val = np.array(app_data)
            if pt_idx == 1:
                p.pt1_phys = new_val
            else:
                p.pt2_phys = new_val
            viewer.view_state.is_geometry_dirty = True
            if self._ui:
                self._ui.update_plot_info(p)
                self._ui.refresh_plot_series(p)
            api.request_refresh()

    def on_toggle_log_clicked(self, sender, app_data, user_data):
        api = self._api
        if not api:
            return
        p_id = user_data
        viewer = api.get_active_viewer()
        if not viewer or not viewer.view_state:
            return
        p = viewer.view_state.profiles.get(p_id)
        if p:
            p.use_log = not p.use_log
            if self._ui:
                self._ui.rebuild_plot_window_contents(p)

    def on_export_profile_clicked(self, sender, app_data, user_data):
        api = self._api
        if not api:
            return
        viewer = api.get_active_viewer()
        if not viewer or not viewer.image_id:
            return
        p = viewer.view_state.profiles.get(user_data)
        if not p:
            return

        default_name = f"profile_plugin_{p.name.replace(' ', '_')}.json"
        file_path = save_file_dialog("Export Profile Data", default_name=default_name)
        if file_path:
            data = api.get_full_export_data(viewer.image_id, p)
            try:
                with open(file_path, "w") as f:
                    json.dump(data, f, indent=4)
                api.notify(f"Exported: {p.name}")
            except Exception as e:
                api.notify(f"Export Failed: {e}")
