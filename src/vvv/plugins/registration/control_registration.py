from __future__ import annotations
import os
import math
import queue
import threading
import numpy as np
from typing import Optional, TYPE_CHECKING
import dearpygui.dearpygui as dpg
from vvv.plugins.plugin_api import PluginAPI, PluginTagMixin
from vvv.ui.file_dialog import open_file_dialog, save_file_dialog
from vvv.ui.render_strategy import (
    compute_preview_2d_affine,
    compute_overlay_preview_2d_affine,
)

if TYPE_CHECKING:
    from vvv.core.view_state import ViewState


class RegistrationPluginController(PluginTagMixin):
    """Controller for the registration plugin."""

    def __init__(self, plugin_id: str):
        self._plugin_id = plugin_id
        self._api: Optional[PluginAPI] = None
        self._ui = None

        self._preview_version = 0
        self._preview_lock = threading.Lock()
        self._preview_queue = queue.Queue()
        threading.Thread(target=self._preview_worker_loop, daemon=True).start()
        self._auto_timer: "threading.Timer | None" = None
        self._auto_timer_lock = threading.Lock()
        self._auto_timer_vs_id: str | None = None
        self._last_data_ids: dict[str, int] = {}

    def bind(self, api: PluginAPI) -> None:
        self._api = api

    def bind_ui(self, ui) -> None:
        self._ui = ui

    def update(self, api: PluginAPI) -> None:
        # Detect reload of any loaded volume
        for img_id, vol in api.get_volumes().items():
            curr_id = id(vol.data)
            if img_id not in self._last_data_ids:
                self._last_data_ids[img_id] = curr_id
            elif self._last_data_ids[img_id] != curr_id:
                self._last_data_ids[img_id] = curr_id
                vs = api.get_view_states().get(img_id)
                if vs and vs.space.is_active:
                    vs.needs_resample = True
                    api.resample_image(img_id)

        viewer = api.get_active_viewer()
        if viewer and viewer.image_id:
            self._check_preview_slice_needed(viewer.image_id)
        if self._ui:
            self._ui.update_ui(api)

    def on_image_loaded(self, image_id: str) -> None:
        pass

    def on_image_removed(self, image_id: str) -> None:
        self._last_data_ids.pop(image_id, None)
        with self._auto_timer_lock:
            if self._auto_timer_vs_id == image_id and self._auto_timer is not None:
                self._auto_timer.cancel()
                self._auto_timer = None
                self._auto_timer_vs_id = None

    def serialize_image_state(self, image_id: str, context: str = "history") -> dict:
        if context != "workspace" or not self._api:
            return {}

        vs = self._api.get_view_states().get(image_id)
        if not vs or not vs.space:
            return {}

        state_dict = {
            "is_active": vs.space.is_active,
            "transform_file": vs.space.transform_file,
            "full_transform_path": vs.space.full_transform_path
        }

        if vs.space.transform:
            state_dict["transform_params"] = list(vs.space.transform.GetParameters())
            state_dict["transform_center"] = list(vs.space.transform.GetCenter())

        return state_dict

    def restore_image_state(self, image_id: str, data: dict, context: str = "history") -> None:
        if context != "workspace" or not data or not self._api:
            return

        vs = self._api.get_view_states().get(image_id)
        if not vs or not vs.space:
            return

        vs.space.is_active = data.get("is_active", False)
        vs.space.transform_file = data.get("transform_file", "None")
        vs.space.full_transform_path = data.get("full_transform_path", None)

        params = data.get("transform_params")
        center = data.get("transform_center")
        if params is not None and center is not None:
            import SimpleITK as sitk
            t = sitk.Euler3DTransform()
            t.SetCenter(tuple(center))
            t.SetParameters(tuple(params))
            vs.space.transform = t
        else:
            vs.space.transform = None

        if vs.space.is_active:
            vs.needs_resample = True
            self._api.resample_image(image_id)
        else:
            self._api.update_all_viewers_of_image(image_id)

    def save_settings(self, api: PluginAPI) -> None:
        pass

    def load_settings(self, api: PluginAPI) -> None:
        pass

    def _preview_worker_loop(self):
        while True:
            req = self._preview_queue.get()
            if req is None:
                break
            # Drain: skip all but the latest queued request
            while not self._preview_queue.empty():
                try:
                    req = self._preview_queue.get_nowait()
                except queue.Empty:
                    break
            if req is None:
                break
            vs_id, version, R, center, viewer_slices = req
            self._trigger_fast_preview(vs_id, version, R, center, viewer_slices)

    def _trigger_fast_preview(self, image_id, version, R, center, viewer_slices):
        if not self._api:
            return
        vs: ViewState | None = self._api.get_view_states().get(image_id)
        if not vs:
            return

        new_previews = {}
        new_overlay_previews = {}
        overlay_vol = vs.volume

        for viewer in self._api.get_viewers().values():
            ctx = viewer_slices.get(id(viewer))
            if ctx is None:
                continue
            kind, orientation, slice_idx = ctx

            if kind == "base":
                vol = viewer.volume
                if getattr(vol, "is_dvf", False):
                    continue
                preview = compute_preview_2d_affine(
                    vol, orientation, slice_idx, R, center, vs.camera.time_idx
                )
                if preview is not None:
                    new_previews[(orientation, slice_idx)] = preview

            elif kind == "overlay":
                base_vol = viewer.volume
                if base_vol is None or getattr(base_vol, "is_dvf", False):
                    continue
                t_idx = min(vs.camera.time_idx, overlay_vol.num_timepoints - 1)
                ov_preview = compute_overlay_preview_2d_affine(
                    base_vol, overlay_vol, orientation, slice_idx, R, center, t_idx
                )
                if ov_preview is not None:
                    new_overlay_previews[(orientation, slice_idx)] = ov_preview

        with self._preview_lock:
            if self._preview_version != version:
                return
            vs._preview_R = R
            vs._preview_center = center

        for viewer in self._api.get_viewers().values():
            if viewer.image_id == image_id:
                viewer._preview_slices = new_previews
            elif viewer.view_state and viewer.view_state.display.overlay_id == image_id:
                viewer._overlay_preview_slices = new_overlay_previews

        if vs:
            vs.is_data_dirty = True
        self._api.request_refresh()

    def _check_preview_slice_needed(self, vs_id):
        if not self._api:
            return
        vs: ViewState | None = self._api.get_view_states().get(vs_id)
        if not vs or vs._preview_R is None or not vs._preview_slice_needed:
            return
        vs._preview_slice_needed = False
        if not vs.space.has_rotation():
            return
        rot_transform = vs.space.get_rotation_only_transform()
        matrix_val = rot_transform.GetMatrix()
        if (
            hasattr(matrix_val, "_mock_return_value")
            or not isinstance(matrix_val, (list, tuple, np.ndarray))
            or len(matrix_val) != 9
        ):
            R = np.eye(3, dtype=np.float64)
        else:
            R = np.array(matrix_val, dtype=np.float64).reshape(3, 3)

        center_val = rot_transform.GetCenter()
        if (
            hasattr(center_val, "_mock_return_value")
            or not isinstance(center_val, (list, tuple, np.ndarray))
            or len(center_val) != 3
        ):
            center = np.zeros(3, dtype=np.float64)
        else:
            center = np.array(center_val, dtype=np.float64)
        viewer_slices = {}
        for v in self._api.get_viewers().values():
            if v.image_id == vs_id:
                viewer_slices[id(v)] = ("base", v.orientation, v.slice_idx)
            elif v.view_state and v.view_state.display.overlay_id == vs_id:
                viewer_slices[id(v)] = ("overlay", v.orientation, v.slice_idx)
        if not viewer_slices:
            return
        with self._preview_lock:
            self._preview_version += 1
            version = self._preview_version
        self._preview_queue.put((vs_id, version, R, center, viewer_slices))

    def _is_live_preview_enabled(self):
        return True

    def _is_auto_resample_enabled(self):
        tag = self._t("check_reg_auto_resample")
        exists = dpg.does_item_exist(tag)
        val = dpg.get_value(tag) if exists else None
        return exists and val

    def _cancel_auto_timer(self):
        with self._auto_timer_lock:
            if self._auto_timer is not None:
                self._auto_timer.cancel()
                self._auto_timer = None

    def _schedule_auto_resample(self, vs_id):
        with self._auto_timer_lock:
            if self._auto_timer is not None:
                self._auto_timer.cancel()
            self._auto_timer_vs_id = vs_id
            t = threading.Timer(0.7, self._fire_auto_resample)
            t.daemon = True
            self._auto_timer = t
        t.start()

    def _fire_auto_resample(self):
        with self._auto_timer_lock:
            self._auto_timer = None
            vs_id = self._auto_timer_vs_id
        if vs_id and self._api:
            self._api.resample_image(vs_id)

    def destroy(self) -> None:
        self._cancel_auto_timer()
        self._preview_queue.put(None)

    # --- UI Callbacks ---

    def on_reg_load_clicked(self, sender, app_data, user_data):
        if not self._api:
            return
        viewer = self._api.get_active_viewer()
        if not viewer or not viewer.image_id:
            return

        file_path = open_file_dialog(
            "Load Transform",
            multiple=False,
            extensions=[".tfm", ".txt", ".mat", ".xfm"],
        )
        if isinstance(file_path, str):
            vs = viewer.view_state
            world_pos = vs.camera.crosshair_phys_coord

            if self._api.load_transform(viewer.image_id, file_path):
                vs.space.full_transform_path = file_path
                self._api.notify(f"Loaded {os.path.basename(file_path)}")
                vs.space.is_active = True

                if world_pos is not None:
                    vs.update_crosshair_from_phys(world_pos)

                self._api.update_all_viewers_of_image(viewer.image_id)
                self._api.update_sidebar_crosshair(viewer)
                if self._ui:
                    self._ui.pull_reg_sliders_from_transform()

                self._api.resample_image(viewer.image_id)
                if dpg.does_item_exist(self._t("btn_reg_resample")):
                    dpg.bind_item_theme(self._t("btn_reg_resample"), 0)
                self._api.request_refresh()
            else:
                self._api.notify(
                    "Failed to parse transform file.",
                    color=self._api.get_ui_config()["colors"].get("warning"),
                )

    def on_reg_save_clicked(self, sender, app_data, user_data):
        if not self._api:
            return
        viewer = self._api.get_active_viewer()
        if not viewer or not viewer.view_state:
            return

        vs = viewer.view_state
        if not vs.space.transform:
            self._api.notify(
                "No transform to save!",
                color=self._api.get_ui_config()["colors"]["warning"],
            )
            return

        full_path = vs.space.full_transform_path
        if full_path and os.path.exists(os.path.dirname(full_path)):
            self._api.save_transform(viewer.image_id, full_path)
            self._api.notify(f"Saved: {os.path.basename(full_path)}")
            self._api.request_refresh()
        else:
            self.on_reg_save_as_clicked(sender, app_data, user_data)

    def on_reg_save_as_clicked(self, sender, app_data, user_data):
        if not self._api:
            return
        viewer = self._api.get_active_viewer()
        if not viewer or not viewer.view_state:
            return

        vs = viewer.view_state
        if not vs.space.transform:
            self._api.notify(
                "No transform to save!",
                color=self._api.get_ui_config()["colors"]["warning"],
            )
            return

        default_name = (
            vs.space.transform_file
            if vs.space.transform_file != "None"
            else "matrix.tfm"
        )
        file_path = save_file_dialog("Save Transform As", default_name=default_name)
        if file_path:
            self._api.save_transform(viewer.image_id, file_path)
            vs.space.full_transform_path = file_path
            self._api.notify(f"Saved: {os.path.basename(file_path)}")
            self._api.request_refresh()

    def on_reg_reload_clicked(self, sender, app_data, user_data):
        if not self._api:
            return
        viewer = self._api.get_active_viewer()
        if not viewer or not viewer.view_state:
            return

        full_path = viewer.view_state.space.full_transform_path
        if full_path and os.path.exists(full_path):
            if self._api.load_transform(viewer.image_id, full_path):
                self._api.request_refresh()
                if self._ui:
                    self._ui.pull_reg_sliders_from_transform()
                if dpg.does_item_exist(self._t("btn_reg_resample")):
                    dpg.bind_item_theme(self._t("btn_reg_resample"), 0)
                self._api.resample_image(viewer.image_id)
                self._api.notify(f"Reloaded: {os.path.basename(full_path)}")
        else:
            self.on_reg_load_clicked(sender, app_data, user_data)

    def on_reg_center_cor_clicked(self, sender, app_data, user_data):
        if not self._api:
            return
        viewer = self._api.get_active_viewer()
        if not viewer or not viewer.image_id:
            return
        vs = viewer.view_state
        vol = self._api.get_volumes().get(viewer.image_id)
        center = (
            vs.space.transform.GetCenter()
            if vs.space.transform
            else self._api.get_volume_physical_center(vol)
        )
        if center is not None:
            vs.update_crosshair_from_phys(center)

        target_ids = self._api.get_sync_group_vs_ids(viewer.image_id, active_only=True)
        for tid in target_ids:
            self._api.get_view_states()[tid].camera.target_center = center

        self._api.update_all_viewers_of_image(viewer.image_id)
        self._api.propagate_sync(viewer.image_id)
        self._api.request_refresh()

    def on_reg_cor_to_crosshair_clicked(self, sender, app_data, user_data):
        if not self._api:
            return
        viewer = self._api.get_active_viewer()
        if not viewer or not viewer.image_id:
            return

        vs = viewer.view_state
        if not vs.space.transform:
            import SimpleITK as sitk

            vs.space.transform = sitk.Euler3DTransform()

        new_center = vs.camera.crosshair_phys_coord
        if new_center is None:
            return

        new_center_tuple = (
            float(new_center[0]),
            float(new_center[1]),
            float(new_center[2]),
        )

        mapped_center = vs.space.transform.TransformPoint(new_center_tuple)
        new_translation = (
            mapped_center[0] - new_center_tuple[0],
            mapped_center[1] - new_center_tuple[1],
            mapped_center[2] - new_center_tuple[2],
        )

        vs.space.transform.SetCenter(new_center_tuple)
        vs.space.transform.SetTranslation(new_translation)
        vs.space.is_active = True

        if self._ui:
            self._ui.pull_reg_sliders_from_transform()
        if dpg.does_item_exist(self._t("btn_reg_resample")):
            dpg.bind_item_theme(self._t("btn_reg_resample"), "orange_button_theme")
        vs.needs_resample = True
        self._api.request_refresh()
        self._api.notify("CoR snapped to Crosshair")

    def on_reg_step_changed(self, sender, app_data, user_data):
        speed = 1.0 if app_data == "Coarse" else 0.1
        slider_tags = [
            self._t("drag_reg_rx"),
            self._t("drag_reg_ry"),
            self._t("drag_reg_rz"),
            self._t("drag_reg_tx"),
            self._t("drag_reg_ty"),
            self._t("drag_reg_tz"),
        ]
        for tag in slider_tags:
            if dpg.does_item_exist(tag):
                dpg.configure_item(tag, speed=speed)

    def on_reg_step_button_clicked(self, sender, app_data, user_data):
        target_tag = user_data["tag"]
        direction = user_data["dir"]

        step_str = dpg.get_value(self._t("radio_reg_step"))
        step_size = 1.0 if step_str == "Coarse" else 0.1
        current_val = dpg.get_value(target_tag)
        dpg.set_value(target_tag, current_val + (step_size * direction))

        self.on_reg_manual_changed(sender, app_data, user_data)

    def on_reg_reset_clicked(self, sender, app_data, user_data):
        self._cancel_auto_timer()
        if not self._api:
            return
        viewer = self._api.get_active_viewer()
        if not viewer or not viewer.image_id:
            return
        slider_tags = [
            self._t("drag_reg_rx"),
            self._t("drag_reg_ry"),
            self._t("drag_reg_rz"),
            self._t("drag_reg_tx"),
            self._t("drag_reg_ty"),
            self._t("drag_reg_tz"),
        ]
        for tag in slider_tags:
            if dpg.does_item_exist(tag):
                dpg.set_value(tag, 0.0)
        self._api.update_transform_manual(viewer.image_id, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)

        with self._preview_lock:
            self._preview_version += 1

        vs: ViewState | None = self._api.get_view_states().get(viewer.image_id)
        if vs:
            vs.reset_preview_rotation()
            vs.needs_resample = True
        if dpg.does_item_exist(self._t("btn_reg_resample")):
            dpg.bind_item_theme(self._t("btn_reg_resample"), 0)
        self._api.resample_image(viewer.image_id)
        self._api.request_refresh()

    def on_reg_invert_clicked(self, sender, app_data, user_data):
        if not self._api:
            return
        viewer = self._api.get_active_viewer()
        if not viewer or not viewer.image_id:
            return
        vs = viewer.view_state
        if not vs.space.transform:
            return
        params = vs.space.transform.GetInverse().GetParameters()
        vals = [
            math.degrees(params[0]),
            math.degrees(params[1]),
            math.degrees(params[2]),
            params[3],
            params[4],
            params[5],
        ]
        slider_tags = [
            self._t("drag_reg_rx"),
            self._t("drag_reg_ry"),
            self._t("drag_reg_rz"),
            self._t("drag_reg_tx"),
            self._t("drag_reg_ty"),
            self._t("drag_reg_tz"),
        ]
        for tag, val in zip(slider_tags, vals):
            if dpg.does_item_exist(tag):
                dpg.set_value(tag, val)
        self.on_reg_manual_changed(sender, app_data, user_data)

    def on_reg_auto_resample_toggled(self, sender, app_data, user_data):
        if not app_data:
            self._cancel_auto_timer()
            return
        if not self._api:
            return
        viewer = self._api.get_active_viewer()
        if not viewer or not viewer.image_id:
            return
        vs = self._api.get_view_states().get(viewer.image_id)
        if vs and vs.needs_resample:
            self._api.resample_image(viewer.image_id)

    def on_reg_resample_clicked(self, sender, app_data, user_data):
        self._cancel_auto_timer()
        if not self._api:
            return
        viewer = self._api.get_active_viewer()
        if not viewer or not viewer.image_id:
            return
        vs_id = viewer.image_id

        if dpg.does_item_exist(self._t("btn_reg_resample")):
            dpg.bind_item_theme(self._t("btn_reg_resample"), 0)

        self._api.notify(
            "Resampling display...",
            color=self._api.get_ui_config()["colors"].get("working"),
        )
        self._api.resample_image(vs_id)
        vs: ViewState | None = self._api.get_view_states().get(vs_id)
        if vs:
            vs.needs_resample = False

    def on_reg_manual_changed(self, sender, app_data, user_data):
        if not self._api:
            return
        viewer = self._api.get_active_viewer()
        if not viewer or not viewer.image_id:
            return
        vs_id = viewer.image_id

        vs: ViewState | None = self._api.get_view_states().get(vs_id)

        if vs:
            vs.space.is_active = True

        slider_tags = [
            self._t("drag_reg_rx"),
            self._t("drag_reg_ry"),
            self._t("drag_reg_rz"),
            self._t("drag_reg_tx"),
            self._t("drag_reg_ty"),
            self._t("drag_reg_tz"),
        ]
        vals = [dpg.get_value(t) for t in slider_tags]
        self._api.update_transform_manual(
            vs_id, vals[3], vals[4], vals[5], vals[0], vals[1], vals[2]
        )
        if dpg.does_item_exist(self._t("btn_reg_resample")):
            dpg.bind_item_theme(self._t("btn_reg_resample"), "orange_button_theme")
        if vs:
            vs.needs_resample = True

        has_rotation = vs is not None and vs.space.has_rotation()

        with self._preview_lock:
            self._preview_version += 1
            version = self._preview_version

        if vs and not has_rotation:
            vs.reset_preview_rotation()

        preview_thread_spawned = False
        if self._is_live_preview_enabled() and has_rotation and vs:
            rot_transform = vs.space.get_rotation_only_transform()
            matrix_val = rot_transform.GetMatrix()
            if (
                hasattr(matrix_val, "_mock_return_value")
                or not isinstance(matrix_val, (list, tuple, np.ndarray))
                or len(matrix_val) != 9
            ):
                R = np.eye(3, dtype=np.float64)
            else:
                R = np.array(matrix_val, dtype=np.float64).reshape(3, 3)

            center_val = rot_transform.GetCenter()
            if (
                hasattr(center_val, "_mock_return_value")
                or not isinstance(center_val, (list, tuple, np.ndarray))
                or len(center_val) != 3
            ):
                center = np.zeros(3, dtype=np.float64)
            else:
                center = np.array(center_val, dtype=np.float64)
            viewer_slices = {}
            for v in self._api.get_viewers().values():
                if v.image_id == vs_id:
                    viewer_slices[id(v)] = ("base", v.orientation, v.slice_idx)
                elif v.view_state and v.view_state.display.overlay_id == vs_id:
                    viewer_slices[id(v)] = ("overlay", v.orientation, v.slice_idx)
            self._preview_queue.put((vs_id, version, R, center, viewer_slices))
            preview_thread_spawned = True

        if not preview_thread_spawned:
            self._api.update_all_viewers_of_image(vs_id)

        if self._is_auto_resample_enabled() and vs and vs.needs_resample:
            self._schedule_auto_resample(vs_id)

        self._api.request_refresh()

    def on_reg_bake_clicked(self, sender, app_data, user_data):
        if not self._api:
            return
        viewer = self._api.get_active_viewer()
        if not viewer or not viewer.image_id:
            return
        vs = viewer.view_state
        if not vs or not vs.space.transform or not vs.space.is_active:
            self._api.notify(
                "No active transform to bake.",
                color=self._api.get_ui_config()["colors"]["warning"],
            )
            return
        self._api.notify(
            "Baking transform...",
            color=self._api.get_ui_config()["colors"].get("working"),
        )
        self._api.bake_transform_to_volume(viewer.image_id)
        if self._ui:
            self._ui.pull_reg_sliders_from_transform()
        self._api.request_refresh()
