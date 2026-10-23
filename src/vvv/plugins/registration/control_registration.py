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
        self._target_role: str = "Base"

    def get_target_info(self) -> tuple[str | None, Optional["ViewState"], Any, str]:
        """Returns (target_id, target_vs, target_vol, actual_role).

        actual_role is either 'Base' or 'Fusion'. If 'Fusion' is selected but no
        overlay is loaded in the active viewer, falls back to 'Base'.
        """
        if not self._api:
            return None, None, None, "Base"
        viewer = self._api.get_active_viewer()
        if not viewer or not viewer.image_id:
            return None, None, None, "Base"

        base_id = viewer.image_id
        base_vs = viewer.view_state
        if base_vs is None and self._api:
            vss = self._api.get_view_states()
            if base_id in vss:
                base_vs = vss.get(base_id)

        base_vol = None
        if self._api:
            vols = self._api.get_volumes()
            if base_id in vols:
                base_vol = vols.get(base_id)
        if base_vol is None:
            base_vol = getattr(viewer, "volume", None)

        overlay_id = None
        if base_vs and getattr(base_vs, "display", None) and getattr(base_vs.display, "overlay", None):
            raw_ov_id = base_vs.display.overlay.image_id
            if isinstance(raw_ov_id, str) and raw_ov_id:
                overlay_id = raw_ov_id

        if self._target_role == "Fusion" and overlay_id:
            ov_vs = self._api.get_view_states().get(overlay_id)
            ov_vol = self._api.get_volumes().get(overlay_id)
            return overlay_id, ov_vs, ov_vol, "Fusion"

        return base_id, base_vs, base_vol, "Base"

    def on_reg_target_changed(self, sender, app_data, user_data):
        self._target_role = app_data
        if self._ui:
            self._ui.pull_reg_sliders_from_transform()
        if self._api:
            self._api.request_refresh()

    def bind(self, api: PluginAPI) -> None:
        self._api = api

    def bind_ui(self, ui) -> None:
        self._ui = ui

    def _ensure_tracked(self, image_id: str) -> None:
        """Register image for data-reload detection. Call when its transform becomes active."""
        if image_id not in self._last_data_ids and self._api:
            vol = self._api.get_volumes().get(image_id)
            if vol is not None:
                self._last_data_ids[image_id] = id(vol.data)

    def update(self, api: PluginAPI) -> None:
        # Detect reload of registered (transformed) volumes only — O(k) not O(N)
        for img_id in list(self._last_data_ids):
            vol = api.get_volumes().get(img_id)
            if vol is None:
                continue
            curr_id = id(vol.data)
            if self._last_data_ids[img_id] != curr_id:
                self._last_data_ids[img_id] = curr_id
                vs = api.get_view_states().get(img_id)
                if vs and vs.space.is_active:
                    vs.needs_resample = True
                    api.resample_image(img_id)

        checked_ids = set()
        for v in api.get_viewers().values():
            if v and v.image_id and v.image_id not in checked_ids:
                checked_ids.add(v.image_id)
                self._check_preview_slice_needed(v.image_id)
            if v and v.view_state and v.view_state.display.overlay.image_id:
                ov_id = v.view_state.display.overlay.image_id
                if ov_id not in checked_ids:
                    checked_ids.add(ov_id)
                    self._check_preview_slice_needed(ov_id)
        if self._ui:
            self._ui.update_ui(api)

    def _find_tfm_candidate(self, vol) -> str | None:
        """Looks for a matching .tfm file on disk for a loaded volume."""
        if not vol:
            return None

        candidates = []
        file_paths = getattr(vol, "file_paths", None)
        if file_paths and len(file_paths) > 0:
            p0 = file_paths[0]
            if p0.lower().endswith(".nii.gz") or p0.lower().endswith(".tar.gz"):
                stem = p0[:-7]
            else:
                stem = os.path.splitext(p0)[0]

            candidates.append(f"{stem}.tfm")
            candidates.append(f"{stem}.TFM")
            candidates.append(f"{p0}.tfm")
            candidates.append(f"{p0}.TFM")

            # Check directory-level names for multi-file series (e.g. DICOM)
            dir_path = os.path.dirname(os.path.abspath(p0))
            folder_name = os.path.basename(dir_path)
            candidates.append(f"{dir_path}.tfm")
            candidates.append(f"{dir_path}.TFM")
            candidates.append(os.path.join(dir_path, f"{folder_name}.tfm"))
            candidates.append(os.path.join(dir_path, f"{folder_name}.TFM"))
            if getattr(vol, "name", None):
                candidates.append(os.path.join(dir_path, f"{vol.name}.tfm"))
                candidates.append(os.path.join(dir_path, f"{vol.name}.TFM"))

        name = getattr(vol, "name", None)
        if name:
            if name.lower().endswith(".nii.gz") or name.lower().endswith(".tar.gz"):
                nstem = name[:-7]
            else:
                nstem = os.path.splitext(name)[0]
            candidates.append(f"{nstem}.tfm")
            candidates.append(f"{nstem}.TFM")

        for c in candidates:
            if c and os.path.isfile(c):
                return os.path.abspath(c)
        return None

    def on_image_loaded(self, image_id: str) -> None:
        if not self._api:
            return
        vol = self._api.get_volumes().get(image_id)
        vs = self._api.get_view_states().get(image_id)
        if not vol or not vs:
            return

        # Do not overwrite if transform is already set
        if vs.space.transform is not None:
            return

        tfm_path = self._find_tfm_candidate(vol)
        if not tfm_path:
            return

        if self._api.load_transform(image_id, tfm_path):
            vs.space.full_transform_path = tfm_path
            vs.space.is_active = True
            self._ensure_tracked(image_id)

            world_pos = vs.camera.crosshair_phys_coord
            if world_pos is not None:
                vs.update_crosshair_from_phys(world_pos)

            self._api.resample_image(image_id)
            self._api.update_all_viewers_of_image(image_id)
            if self._ui:
                self._ui.pull_reg_sliders_from_transform()
            self._api.notify(f"Auto-applied transform: {os.path.basename(tfm_path)}")
            self._api.request_refresh()

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

        # Mark any in-flight resample/bake for this image as stale (e.g. from auto-applied .tfm)
        self._api.invalidate_resample(image_id)
        with self._auto_timer_lock:
            if self._auto_timer_vs_id == image_id and self._auto_timer is not None:
                self._auto_timer.cancel()
                self._auto_timer = None
                self._auto_timer_vs_id = None
        with self._preview_lock:
            self._preview_version += 1
        vs.reset_preview_rotation()

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
            self._ensure_tracked(image_id)
            vs.needs_resample = True
            self._api.resample_image(image_id)
        else:
            if getattr(vs, "base_display_data", None) is not None:
                vs.base_display_data = None
                vs._sitk_base_cache = None
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
            vs_id, version, R, center, tasks, overlay_vol, t_idx = req
            self._compute_fast_preview(vs_id, version, R, center, tasks, overlay_vol, t_idx)

    def _compute_fast_preview(self, image_id, version, R, center, tasks, overlay_vol, t_idx):
        if not self._api:
            return

        new_previews = {}
        new_overlay_previews = {}

        for viewer_id, kind, orientation, slice_idx, base_vol in tasks:
            if kind == "base":
                if base_vol is None or getattr(base_vol, "is_dvf", False):
                    continue
                preview = compute_preview_2d_affine(
                    base_vol, orientation, slice_idx, R, center, t_idx
                )
                if preview is not None:
                    new_previews[(orientation, slice_idx)] = preview

            elif kind == "overlay":
                if base_vol is None or getattr(base_vol, "is_dvf", False) or overlay_vol is None:
                    continue
                ov_preview = compute_overlay_preview_2d_affine(
                    base_vol, overlay_vol, orientation, slice_idx, R, center, t_idx
                )
                if ov_preview is not None:
                    new_overlay_previews[(orientation, slice_idx)] = ov_preview

        def _commit():
            with self._preview_lock:
                if self._preview_version != version:
                    return
                vs: ViewState | None = self._api.get_view_states().get(image_id) if self._api else None
                if not vs:
                    return
                vs._preview_R = R
                vs._preview_center = center

            for viewer in self._api.get_viewers().values():
                if viewer.image_id == image_id:
                    viewer._preview_slices = new_previews
                elif viewer.view_state and viewer.view_state.display.overlay.image_id == image_id:
                    viewer._overlay_preview_slices = new_overlay_previews

            vs.is_data_dirty = True
            self._api.request_refresh()

        self._api.run_on_main_thread(_commit)

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
        try:
            R = np.array(rot_transform.GetMatrix(), dtype=np.float64).reshape(3, 3)
            center = np.array(rot_transform.GetCenter(), dtype=np.float64)
        except Exception:
            R = np.eye(3, dtype=np.float64)
            center = np.zeros(3, dtype=np.float64)
        tasks = []
        for v in self._api.get_viewers().values():
            if v.image_id == vs_id:
                tasks.append((id(v), "base", v.orientation, v.slice_idx, v.volume))
            elif v.view_state and v.view_state.display.overlay.image_id == vs_id:
                tasks.append((id(v), "overlay", v.orientation, v.slice_idx, v.volume))
        if not tasks:
            return
        overlay_vol = vs.volume
        t_idx = getattr(vs.camera, "time_idx", 0) if hasattr(vs, "camera") else 0
        num_tp = getattr(overlay_vol, "num_timepoints", 1)
        if isinstance(num_tp, int) and num_tp > 1 and isinstance(t_idx, int):
            t_idx = min(t_idx, num_tp - 1)
        with self._preview_lock:
            self._preview_version += 1
            version = self._preview_version
        self._preview_queue.put((vs_id, version, R, center, tasks, overlay_vol, t_idx))

    def _trigger_fast_preview(self, image_id, version, R, center, viewer_slices):
        """Backwards compatibility helper: converts viewer_slices dict to tasks list and computes preview."""
        tasks = []
        if self._api:
            for viewer in self._api.get_viewers().values():
                ctx = viewer_slices.get(id(viewer))
                if ctx is not None:
                    kind, orientation, slice_idx = ctx
                    tasks.append((id(viewer), kind, orientation, slice_idx, viewer.volume))
            vs = self._api.get_view_states().get(image_id)
            overlay_vol = vs.volume if vs else None
            t_idx = getattr(vs.camera, "time_idx", 0) if vs and hasattr(vs, "camera") else 0
        else:
            overlay_vol = None
            t_idx = 0
        self._compute_fast_preview(image_id, version, R, center, tasks, overlay_vol, t_idx)

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
            self._api.run_on_main_thread(lambda: self._api.resample_image(vs_id))

    def destroy(self) -> None:
        self._cancel_auto_timer()
        try:
            self._preview_queue.put(None)
        except Exception:
            pass

    # --- UI Callbacks ---

    def on_reg_load_clicked(self, sender, app_data, user_data):
        if not self._api:
            return
        target_id, vs, vol, role = self.get_target_info()
        if not target_id or not vs:
            return

        file_path = open_file_dialog(
            f"Load Transform ({role})",
            multiple=False,
            extensions=[".tfm", ".txt", ".mat", ".xfm"],
        )
        if isinstance(file_path, str):
            world_pos = vs.camera.crosshair_phys_coord

            if self._api.load_transform(target_id, file_path):
                vs.space.full_transform_path = file_path
                self._api.notify(f"Loaded ({role}): {os.path.basename(file_path)}")
                vs.space.is_active = True
                self._ensure_tracked(target_id)

                if world_pos is not None:
                    vs.update_crosshair_from_phys(world_pos)

                self._api.update_all_viewers_of_image(target_id)
                viewer = self._api.get_active_viewer()
                if viewer:
                    self._api.update_sidebar_crosshair(viewer)
                if self._ui:
                    self._ui.pull_reg_sliders_from_transform()

                self._api.resample_image(target_id)
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
        target_id, vs, vol, role = self.get_target_info()
        if not target_id or not vs:
            return

        if not vs.space.transform:
            self._api.notify(
                "No transform to save!",
                color=self._api.get_ui_config()["colors"]["warning"],
            )
            return

        full_path = vs.space.full_transform_path
        if full_path and os.path.exists(os.path.dirname(full_path)):
            self._api.save_transform(target_id, full_path)
            self._api.notify(f"Saved ({role}): {os.path.basename(full_path)}")
            self._api.request_refresh()
        else:
            self.on_reg_save_as_clicked(sender, app_data, user_data)

    def on_reg_save_as_clicked(self, sender, app_data, user_data):
        if not self._api:
            return
        target_id, vs, vol, role = self.get_target_info()
        if not target_id or not vs:
            return

        if not vs.space.transform:
            self._api.notify(
                "No transform to save!",
                color=self._api.get_ui_config()["colors"]["warning"],
            )
            return

        start_dir = None
        if vs.space.full_transform_path:
            start_dir = os.path.dirname(vs.space.full_transform_path)

        if vs.space.transform_file and vs.space.transform_file != "None":
            default_name = vs.space.transform_file
        elif vol and getattr(vol, "file_paths", None) and vol.file_paths:
            fp0 = vol.file_paths[0]
            if start_dir is None:
                start_dir = os.path.dirname(fp0)
            if fp0.lower().endswith(".nii.gz") or fp0.lower().endswith(".tar.gz"):
                img_stem = os.path.basename(fp0[:-7])
            else:
                img_stem = os.path.splitext(os.path.basename(fp0))[0]
            default_name = f"{img_stem}.tfm"
        elif vol and getattr(vol, "name", None):
            name = vol.name
            if name.lower().endswith(".nii.gz") or name.lower().endswith(".tar.gz"):
                nstem = name[:-7]
            else:
                nstem = os.path.splitext(name)[0]
            default_name = f"{nstem}.tfm"
        else:
            default_name = "matrix.tfm"

        if not os.path.splitext(default_name)[1]:
            default_name += ".tfm"

        file_path = save_file_dialog(
            f"Save Transform As ({role}) (.tfm)",
            default_name=default_name,
            start_dir=start_dir,
        )
        if file_path:
            if not os.path.splitext(file_path)[1]:
                file_path += ".tfm"

            self._api.save_transform(target_id, file_path)
            vs.space.full_transform_path = file_path
            self._api.notify(f"Saved ({role}): {os.path.basename(file_path)}")
            self._api.request_refresh()

    def on_reg_reload_clicked(self, sender, app_data, user_data):
        if not self._api:
            return
        target_id, vs, vol, role = self.get_target_info()
        if not target_id or not vs:
            return

        full_path = vs.space.full_transform_path
        if full_path and os.path.exists(full_path):
            if self._api.load_transform(target_id, full_path):
                self._api.request_refresh()
                if self._ui:
                    self._ui.pull_reg_sliders_from_transform()
                if dpg.does_item_exist(self._t("btn_reg_resample")):
                    dpg.bind_item_theme(self._t("btn_reg_resample"), 0)
                self._api.resample_image(target_id)
                self._api.notify(f"Reloaded ({role}): {os.path.basename(full_path)}")
        else:
            self.on_reg_load_clicked(sender, app_data, user_data)

    def on_reg_unload_clicked(self, sender, app_data, user_data):
        self._cancel_auto_timer()
        if not self._api:
            return
        target_id, vs, vol, role = self.get_target_info()
        if not target_id or not vs or vs.space.transform is None:
            return
        name = vs.space.transform_file
        with self._preview_lock:
            self._preview_version += 1  # drop a pending rotation preview
        self._api.unload_transform(target_id)
        if self._ui:
            self._ui.pull_reg_sliders_from_transform()
        if dpg.does_item_exist(self._t("btn_reg_resample")):
            dpg.bind_item_theme(self._t("btn_reg_resample"), 0)
        self._api.notify(f"Unloaded ({role}): {name}")
        self._api.request_refresh()

    def on_reg_center_cor_clicked(self, sender, app_data, user_data):
        if not self._api:
            return
        target_id, vs, vol, role = self.get_target_info()
        if not target_id or not vs:
            return

        center = (
            vs.space.transform.GetCenter()
            if vs.space.transform
            else self._api.get_volume_physical_center(vol)
        )
        if center is not None:
            vs.update_crosshair_from_phys(center)

        target_ids = self._api.get_sync_group_vs_ids(target_id, active_only=True)
        for tid in target_ids:
            self._api.get_view_states()[tid].camera.target_center = center

        self._api.update_all_viewers_of_image(target_id)
        self._api.propagate_sync(target_id)
        self._api.request_refresh()

    def on_reg_cor_to_crosshair_clicked(self, sender, app_data, user_data):
        if not self._api:
            return
        target_id, vs, vol, role = self.get_target_info()
        if not target_id or not vs:
            return

        if not vs.space.transform:
            import SimpleITK as sitk

            vs.space.transform = sitk.Euler3DTransform()

        viewer = self._api.get_active_viewer()
        active_vs = viewer.view_state if viewer else vs
        new_center = active_vs.camera.crosshair_phys_coord
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
        self._ensure_tracked(target_id)

        if self._ui:
            self._ui.pull_reg_sliders_from_transform()
        if dpg.does_item_exist(self._t("btn_reg_resample")):
            dpg.bind_item_theme(self._t("btn_reg_resample"), "orange_button_theme")
        vs.needs_resample = True
        self._api.request_refresh()
        self._api.notify(f"CoR snapped to Crosshair ({role})")

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
        target_id, vs, vol, role = self.get_target_info()
        if not target_id or not vs:
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
        self._api.update_transform_manual(target_id, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)

        with self._preview_lock:
            self._preview_version += 1

        vs.reset_preview_rotation()
        vs.needs_resample = True
        if dpg.does_item_exist(self._t("btn_reg_resample")):
            dpg.bind_item_theme(self._t("btn_reg_resample"), 0)
        self._api.resample_image(target_id)
        self._api.request_refresh()

    def on_reg_invert_clicked(self, sender, app_data, user_data):
        if not self._api:
            return
        target_id, vs, vol, role = self.get_target_info()
        if not target_id or not vs or not vs.space.transform:
            self._api.notify(
                "No transform to invert!",
                color=self._api.get_ui_config()["colors"].get("warning"),
            )
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
        self._apply_manual_transform(target_id, vs, vals)
        self._api.notify(f"Inverted transform ({role})")

    def on_reg_auto_resample_toggled(self, sender, app_data, user_data):
        if not app_data:
            self._cancel_auto_timer()
            return
        if not self._api:
            return
        target_id, vs, vol, role = self.get_target_info()
        if not target_id or not vs:
            return
        if vs.needs_resample:
            self._api.resample_image(target_id)

    def on_reg_resample_clicked(self, sender, app_data, user_data):
        self._cancel_auto_timer()
        if not self._api:
            return
        target_id, vs, vol, role = self.get_target_info()
        if not target_id or not vs:
            return

        if dpg.does_item_exist(self._t("btn_reg_resample")):
            dpg.bind_item_theme(self._t("btn_reg_resample"), 0)

        self._api.notify(
            f"Resampling display ({role})...",
            color=self._api.get_ui_config()["colors"].get("working"),
        )
        self._api.resample_image(target_id)
        vs.needs_resample = False

    def _apply_manual_transform(self, target_id: str, vs, vals: list[float]):
        vs.space.is_active = True
        self._ensure_tracked(target_id)

        self._api.update_transform_manual(
            target_id, vals[3], vals[4], vals[5], vals[0], vals[1], vals[2]
        )
        if dpg.does_item_exist(self._t("btn_reg_resample")):
            dpg.bind_item_theme(self._t("btn_reg_resample"), "orange_button_theme")
        vs.needs_resample = True

        has_rotation = vs.space.has_rotation()

        with self._preview_lock:
            self._preview_version += 1
            version = self._preview_version

        if not has_rotation:
            vs.reset_preview_rotation()

        preview_thread_spawned = False
        if has_rotation:
            rot_transform = vs.space.get_rotation_only_transform()
            try:
                R = np.array(rot_transform.GetMatrix(), dtype=np.float64).reshape(3, 3)
                center = np.array(rot_transform.GetCenter(), dtype=np.float64)
            except Exception:
                R = np.eye(3, dtype=np.float64)
                center = np.zeros(3, dtype=np.float64)
            tasks = []
            for v in self._api.get_viewers().values():
                if v.image_id == target_id:
                    tasks.append((id(v), "base", v.orientation, v.slice_idx, v.volume))
                elif v.view_state and v.view_state.display.overlay.image_id == target_id:
                    tasks.append((id(v), "overlay", v.orientation, v.slice_idx, v.volume))
            overlay_vol = vs.volume
            t_idx = getattr(vs.camera, "time_idx", 0) if hasattr(vs, "camera") else 0
            num_tp = getattr(overlay_vol, "num_timepoints", 1)
            if isinstance(num_tp, int) and num_tp > 1 and isinstance(t_idx, int):
                t_idx = min(t_idx, num_tp - 1)
            self._preview_queue.put((target_id, version, R, center, tasks, overlay_vol, t_idx))
            preview_thread_spawned = True

        if not preview_thread_spawned:
            self._api.update_all_viewers_of_image(target_id)

        if self._is_auto_resample_enabled() and vs.needs_resample:
            self._schedule_auto_resample(target_id)

        self._api.request_refresh()

    def on_reg_manual_changed(self, sender, app_data, user_data):
        if not self._api:
            return
        target_id, vs, vol, role = self.get_target_info()
        if not target_id or not vs:
            return

        slider_tags = [
            self._t("drag_reg_rx"),
            self._t("drag_reg_ry"),
            self._t("drag_reg_rz"),
            self._t("drag_reg_tx"),
            self._t("drag_reg_ty"),
            self._t("drag_reg_tz"),
        ]
        vals = [
            dpg.get_value(t) if (dpg.does_item_exist(t) and dpg.get_value(t) is not None) else 0.0
            for t in slider_tags
        ]
        self._apply_manual_transform(target_id, vs, vals)

    def on_reg_bake_clicked(self, sender, app_data, user_data):
        if not self._api:
            return
        target_id, vs, vol, role = self.get_target_info()
        if not target_id or not vs:
            return
        if not vs.space.transform or not vs.space.is_active:
            self._api.notify(
                f"No active transform to bake on {role}.",
                color=self._api.get_ui_config()["colors"]["warning"],
            )
            return
        self._api.notify(
            f"Baking transform on {role}...",
            color=self._api.get_ui_config()["colors"].get("working"),
        )
        self._api.bake_transform_to_volume(target_id)
        if self._ui:
            self._ui.pull_reg_sliders_from_transform()
        self._api.request_refresh()
