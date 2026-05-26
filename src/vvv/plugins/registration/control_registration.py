import os
import math
from typing import Optional
import dearpygui.dearpygui as dpg
from vvv.plugins.plugin_api import PluginAPI, PluginTagMixin
from vvv.ui.file_dialog import open_file_dialog, save_file_dialog


class RegistrationPluginController(PluginTagMixin):
    """Controller for the registration plugin."""

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
        pass

    def serialize_image_state(self, image_id: str) -> dict:
        return {}

    def restore_image_state(self, image_id: str, data: dict) -> None:
        pass

    def save_settings(self, api: PluginAPI) -> None:
        pass

    def load_settings(self, api: PluginAPI) -> None:
        pass

    def destroy(self) -> None:
        pass

    # --- UI Callbacks ---

    def on_reg_load_clicked(self, sender, app_data, user_data):
        if not self._api:
            return
        viewer = self._api.get_active_viewer()
        if not viewer or not viewer.image_id:
            return

        file_path = open_file_dialog(
            "Load Transform", multiple=False, extensions=[".tfm", ".txt", ".mat", ".xfm"]
        )
        if isinstance(file_path, str):
            vs = viewer.view_state
            world_pos = vs.camera.crosshair_phys_coord

            if self._api.load_transform(viewer.image_id, file_path):
                vs.space._full_transform_path = file_path
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

        full_path = getattr(vs.space, "_full_transform_path", None)
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
            vs.space._full_transform_path = file_path
            self._api.notify(f"Saved: {os.path.basename(file_path)}")
            self._api.request_refresh()

    def on_reg_reload_clicked(self, sender, app_data, user_data):
        if not self._api:
            return
        viewer = self._api.get_active_viewer()
        if not viewer or not viewer.view_state:
            return

        full_path = getattr(viewer.view_state.space, "_full_transform_path", None)
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
        self._api.update_transform_manual(
            viewer.image_id, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0
        )

        vs = self._api.get_view_states().get(viewer.image_id)
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
        # Auto-update timer and previews are not wired yet in Step 2.
        pass

    def on_reg_resample_clicked(self, sender, app_data, user_data):
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

    def on_reg_manual_changed(self, sender, app_data, user_data):
        if not self._api:
            return
        viewer = self._api.get_active_viewer()
        if not viewer or not viewer.image_id:
            return
        vs_id = viewer.image_id

        vs = self._api.get_view_states().get(vs_id)
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

        self._api.update_all_viewers_of_image(vs_id)
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
