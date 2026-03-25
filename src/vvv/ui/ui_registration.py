import os
import math
import threading
import numpy as np
import dearpygui.dearpygui as dpg
from vvv.ui.file_dialog import open_file_dialog, save_file_dialog


class RegistrationUI:
    """Delegated UI handler for the Registration tab."""

    def __init__(self, gui, controller):
        self.gui = gui
        self.controller = controller

    def pull_reg_sliders_from_transform(self):
        """ONLY call this when loading a file, switching images, or resetting. NOT during drag!"""
        viewer = self.gui.context_viewer
        if not viewer or not viewer.image_id:
            return

        vs = viewer.view_state
        if vs and vs.space.transform:
            params = vs.space.get_parameters()
            dpg.set_value("drag_reg_rx", math.degrees(params[0]))
            dpg.set_value("drag_reg_ry", math.degrees(params[1]))
            dpg.set_value("drag_reg_rz", math.degrees(params[2]))
            dpg.set_value("drag_reg_tx", params[3])
            dpg.set_value("drag_reg_ty", params[4])
            dpg.set_value("drag_reg_tz", params[5])
        else:
            for tag in [
                "drag_reg_tx",
                "drag_reg_ty",
                "drag_reg_tz",
                "drag_reg_rx",
                "drag_reg_ry",
                "drag_reg_rz",
            ]:
                if dpg.does_item_exist(tag):
                    dpg.set_value(tag, 0.0)

    def refresh_reg_ui(self):
        viewer = self.gui.context_viewer
        if not viewer or not viewer.view_state:
            return

        vs = viewer.view_state
        vol = self.controller.volumes.get(viewer.image_id)

        if dpg.does_item_exist("text_reg_active_title") and vol:
            dpg.set_value("text_reg_active_title", f"{vol.name}")
        if dpg.does_item_exist("text_reg_filename"):
            dpg.set_value("text_reg_filename", vs.space.transform_file)
        if dpg.does_item_exist("check_reg_apply"):
            dpg.set_value("check_reg_apply", vs.space.is_active)

        if vs.space.transform:
            matrix = np.array(vs.space.transform.GetMatrix()).reshape(3, 3)
            center = vs.space.transform.GetCenter()
            params = vs.space.get_parameters()

            for r in range(3):
                for c in range(3):
                    if dpg.does_item_exist(f"txt_reg_m_{r}_{c}"):
                        dpg.set_value(f"txt_reg_m_{r}_{c}", f"{matrix[r, c]:.4f}")
                if dpg.does_item_exist(f"txt_reg_m_{r}_3"):
                    dpg.set_value(f"txt_reg_m_{r}_3", f"{params[r+3]:.2f}")

            for c, val in enumerate(["0.000", "0.000", "0.000", "1.000"]):
                if dpg.does_item_exist(f"txt_reg_m_3_{c}"):
                    dpg.set_value(f"txt_reg_m_3_{c}", val)

            if dpg.does_item_exist("input_reg_cor"):
                dpg.set_value(
                    "input_reg_cor",
                    f"{center[0]:.1f}, {center[1]:.1f}, {center[2]:.1f}",
                )
        else:
            for r in range(4):
                for c in range(4):
                    if dpg.does_item_exist(f"txt_reg_m_{r}_{c}"):
                        dpg.set_value(
                            f"txt_reg_m_{r}_{c}", "1.000" if r == c else "0.000"
                        )
            if vol and dpg.does_item_exist("input_reg_cor"):
                center = self.controller._get_volume_physical_center(vol)
                dpg.set_value(
                    "input_reg_cor",
                    f"{center[0]:.1f}, {center[1]:.1f}, {center[2]:.1f}",
                )

    def trigger_debounced_rotation_update(self, active_image_id):
        if getattr(self, "_reg_debounce_timer", None) is not None:
            self._reg_debounce_timer.cancel()

        def _do_resample():
            self.gui.show_status_message(
                "Resampling Rotation...", duration=1.0, color=[255, 255, 0]
            )
            active_vs = self.controller.view_states.get(active_image_id)
            if active_vs:
                active_vs.update_base_display_data()
            self.controller.update_all_viewers_of_image(active_image_id)
            self.gui.show_status_message("Transform applied", color=[150, 255, 150])

        self._reg_debounce_timer = threading.Timer(0.3, _do_resample)
        self._reg_debounce_timer.start()

    def apply_transform_and_keep_world_fixed(
        self, viewer, new_state_val=None, skip_manual_update=False
    ):
        vs = viewer.view_state
        vs_id = viewer.image_id

        is_buf = vs.base_display_data is not None
        world_pos = vs.space.display_to_world(
            np.array(vs.camera.crosshair_voxel[:3]), is_buffered=is_buf
        )

        old_rx, old_ry, old_rz = 0.0, 0.0, 0.0
        old_tx, old_ty, old_tz = 0.0, 0.0, 0.0
        if vs.space.transform and vs.space.is_active:
            trans = vs.space.transform.GetTranslation()
            old_tx, old_ty, old_tz = trans[0], trans[1], trans[2]
            old_rx = vs.space.transform.GetAngleX()
            old_ry = vs.space.transform.GetAngleY()
            old_rz = vs.space.transform.GetAngleZ()

        if new_state_val is not None:
            vs.space.is_active = new_state_val

        if not skip_manual_update:
            tx, ty, tz = (
                dpg.get_value("drag_reg_tx"),
                dpg.get_value("drag_reg_ty"),
                dpg.get_value("drag_reg_tz"),
            )
            rx, ry, rz = (
                dpg.get_value("drag_reg_rx"),
                dpg.get_value("drag_reg_ry"),
                dpg.get_value("drag_reg_rz"),
            )
            self.controller.update_transform_manual(vs_id, tx, ty, tz, rx, ry, rz)

        new_rx, new_ry, new_rz = 0.0, 0.0, 0.0
        new_tx, new_ty, new_tz = 0.0, 0.0, 0.0
        if vs.space.transform and vs.space.is_active:
            trans = vs.space.transform.GetTranslation()
            new_tx, new_ty, new_tz = trans[0], trans[1], trans[2]
            new_rx = vs.space.transform.GetAngleX()
            new_ry = vs.space.transform.GetAngleY()
            new_rz = vs.space.transform.GetAngleZ()

        dtx, dty, dtz = new_tx - old_tx, new_ty - old_ty, new_tz - old_tz
        if dtx != 0 or dty != 0 or dtz != 0:
            self.gui._pan_viewers_by_delta(vs_id, dtx, dty, dtz)

        new_local_vox = vs.space.world_to_display(world_pos, is_buffered=is_buf)
        sh = vs.volume.shape3d
        from vvv.utils import ViewMode

        vs.camera.crosshair_voxel = [
            new_local_vox[0],
            new_local_vox[1],
            new_local_vox[2],
            vs.camera.time_idx,
        ]
        vs.camera.slices[ViewMode.AXIAL] = int(np.clip(new_local_vox[2], 0, sh[0] - 1))
        vs.camera.slices[ViewMode.SAGITTAL] = int(
            np.clip(new_local_vox[0], 0, sh[2] - 1)
        )
        vs.camera.slices[ViewMode.CORONAL] = int(
            np.clip(new_local_vox[1], 0, sh[1] - 1)
        )

        for v in self.controller.viewers.values():
            if v.image_id == vs_id:
                v.needs_recenter = True

        self.controller.update_all_viewers_of_image(vs_id)
        self.gui.update_sidebar_crosshair(viewer)

        rotation_changed = (
            abs(new_rx - old_rx) > 1e-5
            or abs(new_ry - old_ry) > 1e-5
            or abs(new_rz - old_rz) > 1e-5
        )
        if rotation_changed or new_state_val is not None:
            self.trigger_debounced_rotation_update(vs_id)

    # --- Callbacks ---
    def on_reg_load_clicked(self, sender, app_data, user_data):
        viewer = self.gui.context_viewer
        if not viewer or not viewer.image_id:
            return

        file_path = open_file_dialog(
            "Load Transform", multiple=False, extensions=[".tfm", ".txt"]
        )
        if file_path:
            vs = viewer.view_state
            is_buf = vs.base_display_data is not None
            world_pos = vs.space.display_to_world(
                np.array(vs.camera.crosshair_voxel[:3]), is_buffered=is_buf
            )

            if self.controller.load_transform(viewer.image_id, file_path):
                self.gui.show_status_message(f"Loaded {os.path.basename(file_path)}")

                new_local_vox = vs.space.world_to_display(world_pos, is_buffered=is_buf)
                sh = vs.volume.shape3d
                from vvv.utils import ViewMode

                vs.camera.crosshair_voxel = [
                    new_local_vox[0],
                    new_local_vox[1],
                    new_local_vox[2],
                    vs.camera.time_idx,
                ]
                vs.camera.slices[ViewMode.AXIAL] = int(
                    np.clip(new_local_vox[2], 0, sh[0] - 1)
                )
                vs.camera.slices[ViewMode.SAGITTAL] = int(
                    np.clip(new_local_vox[0], 0, sh[2] - 1)
                )
                vs.camera.slices[ViewMode.CORONAL] = int(
                    np.clip(new_local_vox[1], 0, sh[1] - 1)
                )

                for v in self.controller.viewers.values():
                    if v.image_id == viewer.image_id:
                        v.needs_recenter = True

                self.controller.update_all_viewers_of_image(viewer.image_id)
                self.gui.update_sidebar_crosshair(viewer)

                self.refresh_reg_ui()
                self.pull_reg_sliders_from_transform()
                self.trigger_debounced_rotation_update(viewer.image_id)
            else:
                self.gui.show_message("Error", "Failed to parse transform file.")

    def on_reg_save_clicked(self, sender, app_data, user_data):
        viewer = self.gui.context_viewer
        if not viewer or not viewer.view_state:
            return

        vs = viewer.view_state
        if not vs.space.transform:
            self.gui.show_status_message("No transform to save!", color=[255, 100, 100])
            return

        default_name = (
            vs.space.transform_file
            if vs.space.transform_file != "None"
            else "matrix.tfm"
        )
        file_path = save_file_dialog("Save Transform", default_name=default_name)
        if file_path:
            self.controller.save_transform(viewer.image_id, file_path)
            self.gui.show_status_message(f"Saved: {os.path.basename(file_path)}")
            self.refresh_reg_ui()

    def on_reg_reload_clicked(self, sender, app_data, user_data):
        self.on_reg_load_clicked(sender, app_data, user_data)

    def on_reg_apply_toggled(self, sender, app_data, user_data):
        viewer = self.gui.context_viewer
        if viewer and viewer.image_id:
            self.apply_transform_and_keep_world_fixed(
                viewer, new_state_val=app_data, skip_manual_update=True
            )

    def on_reg_step_changed(self, sender, app_data, user_data):
        speed = 1.0 if app_data == "Coarse" else 0.1
        for tag in [
            "drag_reg_tx",
            "drag_reg_ty",
            "drag_reg_tz",
            "drag_reg_rx",
            "drag_reg_ry",
            "drag_reg_rz",
        ]:
            if dpg.does_item_exist(tag):
                dpg.configure_item(tag, speed=speed)

    def on_reg_manual_changed(self, sender, app_data, user_data):
        viewer = self.gui.context_viewer
        if not viewer or not viewer.image_id:
            return
        self.apply_transform_and_keep_world_fixed(viewer)
        self.refresh_reg_ui()

    def on_reg_reset_clicked(self, sender, app_data, user_data):
        viewer = self.gui.context_viewer
        if not viewer or not viewer.image_id:
            return

        for tag in [
            "drag_reg_tx",
            "drag_reg_ty",
            "drag_reg_tz",
            "drag_reg_rx",
            "drag_reg_ry",
            "drag_reg_rz",
        ]:
            if dpg.does_item_exist(tag):
                dpg.set_value(tag, 0.0)

        self.on_reg_manual_changed(sender, app_data, user_data)
        self.pull_reg_sliders_from_transform()

    def on_reg_invert_clicked(self, sender, app_data, user_data):
        viewer = self.gui.context_viewer
        if not viewer or not viewer.image_id:
            return

        vs = viewer.view_state
        if not vs.space.transform:
            return

        params = vs.space.transform.GetInverse().GetParameters()
        dpg.set_value("drag_reg_rx", math.degrees(params[0]))
        dpg.set_value("drag_reg_ry", math.degrees(params[1]))
        dpg.set_value("drag_reg_rz", math.degrees(params[2]))
        dpg.set_value("drag_reg_tx", params[3])
        dpg.set_value("drag_reg_ty", params[4])
        dpg.set_value("drag_reg_tz", params[5])

        self.on_reg_manual_changed(sender, app_data, user_data)
        self.pull_reg_sliders_from_transform()

    def on_reg_center_cor_clicked(self, sender, app_data, user_data):
        viewer = self.gui.context_viewer
        if not viewer or not viewer.image_id:
            return

        vs = viewer.view_state
        vol = self.controller.volumes.get(viewer.image_id)

        if vs.space.transform:
            center = vs.space.GetCenter()
        else:
            center = self.controller._get_volume_physical_center(vol)

        is_buf = vs.base_display_data is not None
        new_local_vox = vs.space.world_to_display(center, is_buffered=is_buf)
        sh = vol.shape3d
        from vvv.utils import ViewMode

        vs.camera.crosshair_voxel = [
            new_local_vox[0],
            new_local_vox[1],
            new_local_vox[2],
            vs.camera.time_idx,
        ]
        vs.camera.slices[ViewMode.AXIAL] = int(np.clip(new_local_vox[2], 0, sh[0] - 1))
        vs.camera.slices[ViewMode.SAGITTAL] = int(
            np.clip(new_local_vox[0], 0, sh[2] - 1)
        )
        vs.camera.slices[ViewMode.CORONAL] = int(
            np.clip(new_local_vox[1], 0, sh[1] - 1)
        )

        for v in self.controller.viewers.values():
            if v.image_id == viewer.image_id:
                v.needs_recenter = True

        self.controller.update_all_viewers_of_image(viewer.image_id)
        self.gui.update_sidebar_crosshair(viewer)
        self.controller.sync.propagate_sync(viewer.image_id)
