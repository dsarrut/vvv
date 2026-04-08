import os
import math
import threading
import numpy as np
import dearpygui.dearpygui as dpg
from vvv.ui.file_dialog import open_file_dialog, save_file_dialog


class RegistrationUI:
    """Delegated UI handler for the Registration tab."""

    # Define slider tags once to avoid copy-pasting lists of strings
    SLIDER_TAGS = [
        "drag_reg_rx",
        "drag_reg_ry",
        "drag_reg_rz",
        "drag_reg_tx",
        "drag_reg_ty",
        "drag_reg_tz",
    ]

    def __init__(self, gui, controller):
        self.gui = gui
        self.controller = controller
        self._reg_debounce_timer = None

    @staticmethod
    def build_tab_reg(gui):
        cfg_c = gui.ui_cfg["colors"]

        with dpg.tab(label="Reg", tag="tab_reg"):
            dpg.add_spacer(height=5)

            dpg.add_text("Registration", color=cfg_c["text_header"])
            dpg.add_separator()

            dpg.add_text(
                "No Image Selected",
                tag="text_reg_active_title",
                color=cfg_c["text_active"],
            )

            # --- TOP: File Management & Apply ---
            dpg.add_spacer(height=10)
            with dpg.group(horizontal=True):
                dpg.add_button(
                    label="Load",
                    width=50,
                    tag="btn_reg_load",
                    callback=gui.reg_ui.on_reg_load_clicked,
                )
                dpg.add_button(
                    label="Save",
                    width=50,
                    tag="btn_reg_save",
                    callback=gui.reg_ui.on_reg_save_clicked,
                )
                dpg.add_button(
                    label="Save As",
                    width=65,
                    tag="btn_reg_save_as",
                    callback=gui.reg_ui.on_reg_save_as_clicked,
                )

                btn_reload = dpg.add_button(
                    label="\uf01e",
                    width=20,
                    tag="btn_reg_reload",
                    callback=gui.reg_ui.on_reg_reload_clicked,
                )
                if dpg.does_item_exist("icon_font_tag"):
                    dpg.bind_item_font(btn_reload, "icon_font_tag")
                if dpg.does_item_exist("icon_button_theme"):
                    dpg.bind_item_theme(btn_reload, "icon_button_theme")

            with dpg.group(horizontal=True):
                dpg.add_text("File: ")
                dpg.add_text("None", tag="text_reg_filename", color=cfg_c["text_dim"])

            dpg.add_checkbox(
                label="Apply Transform to Viewers",
                tag="check_reg_apply",
                callback=gui.reg_ui.on_reg_apply_toggled,
            )

            # --- MIDDLE: Read-Only Math (Matrix & CoR) ---
            dpg.add_spacer(height=10)
            dpg.add_text("Affine Matrix", color=cfg_c["text_header"])
            dpg.add_separator()
            with dpg.group(tag="group_reg_matrix"):
                with dpg.table(
                    header_row=False,
                    borders_innerV=True,
                    borders_innerH=True,
                    resizable=False,
                ):
                    for _ in range(4):
                        dpg.add_table_column()
                    for r in range(4):
                        with dpg.table_row():
                            for c in range(4):
                                dpg.add_text(
                                    "0.000",
                                    tag=f"txt_reg_m_{r}_{c}",
                                    color=cfg_c["text_dim"],
                                )

            dpg.add_spacer(height=5)
            with dpg.group(horizontal=True):
                dpg.add_text("CoR:")
                dpg.add_input_text(tag="input_reg_cor", width=125, readonly=True)
                b = dpg.add_button(
                    label="\uf05b ", callback=gui.reg_ui.on_reg_center_cor_clicked
                )
                if dpg.does_item_exist("icon_font_tag"):
                    dpg.bind_item_font(b, "icon_font_tag")
                # Sets the CoR to the current crosshair
                dpg.add_button(
                    label="Set",
                    callback=gui.reg_ui.on_reg_cor_to_crosshair_clicked,
                )

            # --- BOTTOM: Manual 6-DOF Tweaking ---
            dpg.add_spacer(height=10)
            dpg.add_text(
                "Rigid Adjustment (Euler R = Rz Ry Rx)", color=cfg_c["text_header"]
            )
            dpg.add_separator()
            with dpg.group(horizontal=True):
                dpg.add_text("Step:")
                dpg.add_radio_button(
                    items=["Coarse", "Fine"],
                    default_value="Coarse",
                    horizontal=True,
                    tag="radio_reg_step",
                    callback=gui.reg_ui.on_reg_step_changed,
                )

            dpg.add_spacer(height=5)

            # Helper to generate a clean row with [-] [Slider] [+]
            def build_slider_row(label, tag, fmt, min_v, max_v):
                with dpg.group(horizontal=True):
                    dpg.add_text(label)
                    dpg.add_button(
                        label="-",
                        width=20,
                        user_data={"tag": tag, "dir": -1},
                        callback=gui.reg_ui.on_reg_step_button_clicked,
                    )
                    dpg.add_drag_float(
                        tag=tag,
                        width=-35,
                        format=fmt,
                        speed=1.0,
                        min_value=min_v,
                        max_value=max_v,
                        callback=gui.reg_ui.on_reg_manual_changed,
                    )
                    dpg.add_button(
                        label="+",
                        width=20,
                        user_data={"tag": tag, "dir": 1},
                        callback=gui.reg_ui.on_reg_step_button_clicked,
                    )

            # Translation Drag Floats
            build_slider_row("Tx ", "drag_reg_tx", "%.2f mm", -5000.0, 5000.0)
            build_slider_row("Ty ", "drag_reg_ty", "%.2f mm", -5000.0, 5000.0)
            build_slider_row("Tz ", "drag_reg_tz", "%.2f mm", -5000.0, 5000.0)

            dpg.add_spacer(height=5)

            # Rotation Drag Floats (Euler)
            build_slider_row("Rx ", "drag_reg_rx", "%.2f \u00b0", -360.0, 360.0)
            build_slider_row("Ry ", "drag_reg_ry", "%.2f \u00b0", -360.0, 360.0)
            build_slider_row("Rz ", "drag_reg_rz", "%.2f \u00b0", -360.0, 360.0)

            dpg.add_spacer(height=5)
            with dpg.group(horizontal=True):
                dpg.add_button(
                    label="Reset to ID",
                    width=120,
                    callback=gui.reg_ui.on_reg_reset_clicked,
                )
                dpg.add_button(
                    label="Invert", width=-1, callback=gui.reg_ui.on_reg_invert_clicked
                )

    def _snap_viewer_to_world_pos(self, viewer, world_pos):
        """Calculates the new local voxel coordinates and updates the camera slices to stay pinned to a world point."""
        vs = viewer.view_state
        is_buf = vs.base_display_data is not None
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

    def pull_reg_sliders_from_transform(self):
        """ONLY call this when loading a file, switching images, or resetting. NOT during drag!"""
        viewer = self.gui.context_viewer
        if not viewer or not viewer.image_id:
            return

        vs = viewer.view_state
        if vs and vs.space.transform:
            params = vs.space.get_parameters()
            vals = [
                math.degrees(params[0]),
                math.degrees(params[1]),
                math.degrees(params[2]),
                params[3],
                params[4],
                params[5],
            ]

            for tag, val in zip(self.SLIDER_TAGS, vals):
                if dpg.does_item_exist(tag):
                    dpg.set_value(tag, val)
        else:
            for tag in self.SLIDER_TAGS:
                if dpg.does_item_exist(tag):
                    dpg.set_value(tag, 0.0)

    def refresh_reg_ui(self):
        viewer = self.gui.context_viewer
        if not viewer or not viewer.view_state:
            return

        vs = viewer.view_state
        vol = self.controller.volumes.get(viewer.image_id)

        if dpg.does_item_exist("text_reg_active_title") and vol:
            name_str, is_outdated = self.controller.get_image_display_name(
                viewer.image_id
            )
            dpg.set_value("text_reg_active_title", name_str)

            # Apply orange if modified, default active color if not
            col = (
                self.gui.ui_cfg["colors"]["outdated"]
                if is_outdated
                else self.gui.ui_cfg["colors"]["text_active"]
            )
            dpg.configure_item("text_reg_active_title", color=col)

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
                center = self.controller.get_volume_physical_center(vol)
                dpg.set_value(
                    "input_reg_cor",
                    f"{center[0]:.1f}, {center[1]:.1f}, {center[2]:.1f}",
                )

    def trigger_debounced_rotation_update(self, active_image_id, immediate=False):
        if getattr(self, "_reg_debounce_timer", None) is not None:
            self._reg_debounce_timer.cancel()

        def _do_resample():
            self.gui.show_status_message(
                "Resampling Rotation...",
                duration=1.0,
                color=self.gui.ui_cfg["colors"]["working"],
            )
            active_vs = self.controller.view_states.get(active_image_id)
            if active_vs:
                active_vs.update_base_display_data()
                if active_vs.display.overlay_id:
                    active_vs.update_overlay_display_data(self.controller)
                    active_vs.is_data_dirty = True

            for v in self.controller.viewers.values():
                if (
                    v.view_state
                    and getattr(v.view_state.display, "overlay_id", None)
                    == active_image_id
                ):
                    v.view_state.update_overlay_display_data(self.controller)
                    v.view_state.is_data_dirty = True

            self.controller.update_all_viewers_of_image(active_image_id)
            self.gui.show_status_message(
                "Transform applied", color=self.gui.ui_cfg["colors"]["text_status_ok"]
            )

        # Execute instantly if requested
        if immediate:
            _do_resample()
        else:
            self._reg_debounce_timer = threading.Timer(0.3, _do_resample)
            self._reg_debounce_timer.start()

    def apply_transform_and_keep_world_fixed(
        self, viewer, new_state_val=None, skip_manual_update=False
    ):
        vs = viewer.view_state
        vs_id = viewer.image_id

        # 1. Capture the exact crosshair world position
        is_buf = vs.base_display_data is not None
        world_pos = vs.space.display_to_world(
            np.array(vs.camera.crosshair_voxel[:3]), is_buffered=is_buf
        )

        old_tx, old_ty, old_tz = 0.0, 0.0, 0.0
        old_rx, old_ry, old_rz = 0.0, 0.0, 0.0
        if vs.space.transform and vs.space.is_active:
            trans = vs.space.transform.GetTranslation()
            old_tx, old_ty, old_tz = trans[0], trans[1], trans[2]
            params = vs.space.get_parameters()
            old_rx, old_ry, old_rz = params[0], params[1], params[2]

        # Capture RAW voxel coordinate BEFORE transform
        old_raw_vox = vs.space.world_to_display(world_pos, is_buffered=False)
        old_vox = list(vs.camera.crosshair_voxel[:3])

        if new_state_val is not None:
            vs.space.is_active = new_state_val

        if not skip_manual_update:
            new_tx = dpg.get_value("drag_reg_tx")
            new_ty = dpg.get_value("drag_reg_ty")
            new_tz = dpg.get_value("drag_reg_tz")
            new_rx = dpg.get_value("drag_reg_rx")
            new_ry = dpg.get_value("drag_reg_ry")
            new_rz = dpg.get_value("drag_reg_rz")
            self.controller.update_transform_manual(
                vs_id, new_tx, new_ty, new_tz, new_rx, new_ry, new_rz
            )
        else:
            if vs.space.transform and vs.space.is_active:
                trans = vs.space.transform.GetTranslation()
                new_tx, new_ty, new_tz = trans[0], trans[1], trans[2]
                params = vs.space.get_parameters()
                new_rx, new_ry, new_rz = params[0], params[1], params[2]
            else:
                new_tx, new_ty, new_tz = 0.0, 0.0, 0.0
                new_rx, new_ry, new_rz = 0.0, 0.0, 0.0

        # Capture RAW voxel coordinate AFTER transform
        new_raw_vox = vs.space.world_to_display(world_pos, is_buffered=False)

        # Bypass the frozen buffer mapping
        # We manually apply the raw voxel delta directly to the crosshair,
        # forcing it to counter-shift in the opposite direction of the pan.
        delta_vox = new_raw_vox - old_raw_vox

        new_vx = old_vox[0] + delta_vox[0]
        new_vy = old_vox[1] + delta_vox[1]
        new_vz = old_vox[2] + delta_vox[2]

        vs.camera.crosshair_voxel = [new_vx, new_vy, new_vz, vs.camera.time_idx]

        from vvv.utils import ViewMode

        raw_sh = vs.volume.shape3d
        vs.camera.slices[ViewMode.AXIAL] = int(np.clip(new_vz, 0, raw_sh[0] - 1))
        vs.camera.slices[ViewMode.SAGITTAL] = int(np.clip(new_vx, 0, raw_sh[2] - 1))
        vs.camera.slices[ViewMode.CORONAL] = int(np.clip(new_vy, 0, raw_sh[1] - 1))
        # -------------------------------------------------------

        from vvv.utils import voxel_to_slice

        # --- Calculate the difference and Counter-Pan! ---
        for v in self.controller.viewers.values():
            if v.image_id == vs_id:
                shape = v.get_slice_shape()

                old_tx_slice, old_ty_slice = voxel_to_slice(
                    old_raw_vox[0], old_raw_vox[1], old_raw_vox[2], v.orientation, shape
                )
                new_tx_slice, new_ty_slice = voxel_to_slice(
                    new_raw_vox[0], new_raw_vox[1], new_raw_vox[2], v.orientation, shape
                )

                if shape[1] > 0 and shape[0] > 0:
                    # Query the mapper directly to bypass float/integer scaling discrepancies
                    old_screen_x = (old_tx_slice / shape[1]) * v.mapper.disp_w
                    old_screen_y = (old_ty_slice / shape[0]) * v.mapper.disp_h

                    new_screen_x = (new_tx_slice / shape[1]) * v.mapper.disp_w
                    new_screen_y = (new_ty_slice / shape[0]) * v.mapper.disp_h

                    dx_screen = old_screen_x - new_screen_x
                    dy_screen = old_screen_y - new_screen_y

                    # Shift the camera to perfectly counteract the crosshair movement
                    v.pan_offset[0] += dx_screen
                    v.pan_offset[1] += dy_screen
                    v.is_geometry_dirty = True
        # ----------------------------------------------------------------

        self.controller.update_all_viewers_of_image(vs_id)

        # Force Live Rendering on ALL ViewStates
        for v in self.controller.viewers.values():
            if v.view_state:
                v.view_state.is_data_dirty = True

        self.gui.update_sidebar_crosshair(viewer)

        transform_changed = (
            abs(new_rx - old_rx) > 1e-5
            or abs(new_ry - old_ry) > 1e-5
            or abs(new_rz - old_rz) > 1e-5
            or abs(new_tx - old_tx) > 1e-5
            or abs(new_ty - old_ty) > 1e-5
            or abs(new_tz - old_tz) > 1e-5
        )

        if (transform_changed and vs.space.is_active) or new_state_val is not None:
            self.trigger_debounced_rotation_update(vs_id)

    # --- Callbacks ---
    def on_reg_load_clicked(self, sender, app_data, user_data):
        viewer = self.gui.context_viewer
        if not viewer or not viewer.image_id:
            return

        file_path = open_file_dialog(
            "Load Transform", multiple=False, extensions=[".tfm", ".txt", ".mat"]
        )
        if file_path:
            vs = viewer.view_state
            is_buf = vs.base_display_data is not None
            world_pos = vs.space.display_to_world(
                np.array(vs.camera.crosshair_voxel[:3]), is_buffered=is_buf
            )

            if self.controller.load_transform(viewer.image_id, file_path):
                # Dynamically remember the exact file path for "Save"
                vs.space._full_transform_path = file_path
                self.gui.show_status_message(f"Loaded {os.path.basename(file_path)}")

                self._snap_viewer_to_world_pos(viewer, world_pos)

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
            self.gui.show_status_message(
                "No transform to save!", color=self.gui.ui_cfg["colors"]["warning"]
            )
            return

        # If we already have a loaded path, overwrite it seamlessly
        full_path = getattr(vs.space, "_full_transform_path", None)
        if full_path and os.path.exists(os.path.dirname(full_path)):
            self.controller.save_transform(viewer.image_id, full_path)
            self.gui.show_status_message(f"Saved: {os.path.basename(full_path)}")
            self.refresh_reg_ui()
        else:
            # Fallback to Save As
            self.on_reg_save_as_clicked(sender, app_data, user_data)

    def on_reg_save_as_clicked(self, sender, app_data, user_data):
        viewer = self.gui.context_viewer
        if not viewer or not viewer.view_state:
            return

        vs = viewer.view_state
        if not vs.space.transform:
            self.gui.show_status_message(
                "No transform to save!", color=self.gui.ui_cfg["colors"]["warning"]
            )
            return

        default_name = (
            vs.space.transform_file
            if vs.space.transform_file != "None"
            else "matrix.tfm"
        )
        file_path = save_file_dialog("Save Transform As", default_name=default_name)
        if file_path:
            self.controller.save_transform(viewer.image_id, file_path)
            # Update the tracked path so future "Save" clicks overwrite this new file!
            vs.space._full_transform_path = file_path
            self.gui.show_status_message(f"Saved: {os.path.basename(file_path)}")
            self.refresh_reg_ui()

    def on_reg_reload_clicked(self, sender, app_data, user_data):
        viewer = self.gui.context_viewer
        if not viewer or not viewer.view_state:
            return

        full_path = getattr(viewer.view_state.space, "_full_transform_path", None)
        if full_path and os.path.exists(full_path):
            if self.controller.load_transform(viewer.image_id, full_path):
                self.refresh_reg_ui()
                self.pull_reg_sliders_from_transform()
                self.trigger_debounced_rotation_update(viewer.image_id)
                self.gui.show_status_message(f"Reloaded: {os.path.basename(full_path)}")
        else:
            self.on_reg_load_clicked(sender, app_data, user_data)

    def on_reg_step_button_clicked(self, sender, app_data, user_data):
        """Handles the + and - buttons next to the manual registration sliders."""
        target_tag = user_data["tag"]
        direction = user_data["dir"]

        # Respect the Coarse (1.0) or Fine (0.1) radio button selection
        step_str = dpg.get_value("radio_reg_step")
        step_size = 1.0 if step_str == "Coarse" else 0.1
        current_val = dpg.get_value(target_tag)
        dpg.set_value(target_tag, current_val + (step_size * direction))

        # Immediately trigger the transform update
        self.on_reg_manual_changed(sender, app_data, user_data)

    def on_reg_apply_toggled(self, sender, app_data, user_data):
        viewer = self.gui.context_viewer
        if viewer and viewer.image_id:
            self.apply_transform_and_keep_world_fixed(
                viewer, new_state_val=app_data, skip_manual_update=True
            )

    def on_reg_step_changed(self, sender, app_data, user_data):
        speed = 1.0 if app_data == "Coarse" else 0.1
        for tag in self.SLIDER_TAGS:
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
        for tag in self.SLIDER_TAGS:
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
        vals = [
            math.degrees(params[0]),
            math.degrees(params[1]),
            math.degrees(params[2]),
            params[3],
            params[4],
            params[5],
        ]
        for tag, val in zip(self.SLIDER_TAGS, vals):
            if dpg.does_item_exist(tag):
                dpg.set_value(tag, val)
        self.on_reg_manual_changed(sender, app_data, user_data)
        self.pull_reg_sliders_from_transform()

    def on_reg_center_cor_clicked(self, sender, app_data, user_data):
        viewer = self.gui.context_viewer
        if not viewer or not viewer.image_id:
            return
        vs = viewer.view_state
        vol = self.controller.volumes.get(viewer.image_id)
        center = (
            vs.space.transform.GetCenter()
            if vs.space.transform
            else self.controller.get_volume_physical_center(vol)
        )
        self._snap_viewer_to_world_pos(viewer, center)
        for v in self.controller.viewers.values():
            if v.image_id == viewer.image_id:
                v.needs_recenter = True
        self.controller.update_all_viewers_of_image(viewer.image_id)
        self.gui.update_sidebar_crosshair(viewer)
        self.controller.sync.propagate_sync(viewer.image_id)

    def on_reg_cor_to_crosshair_clicked(self, sender, app_data, user_data):
        viewer = self.gui.context_viewer
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

        self.pull_reg_sliders_from_transform()
        self.refresh_reg_ui()

        # Instantly sync the 3D buffer so the math doesn't glitch
        self.trigger_debounced_rotation_update(viewer.image_id, immediate=True)

        self.gui.show_status_message("CoR snapped to Crosshair")
