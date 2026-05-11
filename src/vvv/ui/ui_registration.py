import os
import math
import threading
import numpy as np
import dearpygui.dearpygui as dpg
from vvv.ui.file_dialog import open_file_dialog, save_file_dialog
from vvv.utils import ViewMode, voxel_to_slice
from vvv.ui.ui_components import build_stepped_slider, build_section_title


class RegistrationUI:
    """
    Delegated UI handler for the Registration tab.

    ARCHITECTURE MANDATES (UI Components):
    1. REACTIVE REFRESH ONLY: Never call 'refresh_reg_ui' imperatively from
       within this class. Always set 'self.controller.ui_needs_refresh = True'
       and let the MainGUI tick loop handle the rebuild.

    2. STATE-DRIVEN BUILDING: Sliders and input fields must pull their
       'default_value' from the underlying 'SpatialEngine' transform during
       the refresh cycle.

    3. ONE-WAY DATA FLOW: Callbacks should exclusively update the transform
       parameters in the 'Controller'. Do not manually set values of other
       widgets within a callback.

    4. THREAD SAFETY: Registration resampling often happens in background
       threads. Ensure those threads NEVER call UI functions. Use
       'controller.status_message' for asynchronous reporting.
    """

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

    @staticmethod
    def build_tab_reg(gui):
        cfg_c = gui.ui_cfg["colors"]

        with dpg.group(tag="tab_reg", show=False):

            build_section_title("Registration", cfg_c["text_header"])

            dpg.add_text(
                "No Image Selected",
                tag="text_reg_active_title",
                color=cfg_c["text_active"],
            )

            dpg.add_text(
                "Registration disabled: DVF active",
                tag="text_reg_dvf_warning",
                color=cfg_c.get("outdated", [255, 200, 50]),
                show=False,
            )

            with dpg.group(tag="group_registration_controls"):
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
                with dpg.group(horizontal=True):
                    dpg.add_button(
                        label="Bake into Image",
                        tag="btn_reg_bake",
                        callback=gui.reg_ui.on_reg_bake_clicked,
                        width=-28,
                    )
                    btn_help_bake = dpg.add_button(label="\uf059", width=20)
                    if dpg.does_item_exist("icon_font_tag"):
                        dpg.bind_item_font(btn_help_bake, "icon_font_tag")
                    if dpg.does_item_exist("icon_button_theme"):
                        dpg.bind_item_theme(btn_help_bake, "icon_button_theme")
                    with dpg.tooltip(btn_help_bake):
                        dpg.add_text(
                            "Permanently applies the active spatial transform to the\n"
                            "underlying 3D pixel grid and resets the sliders to zero.\n"
                            "You can then 'Save' the resulting aligned image to disk.",
                            color=cfg_c.get("text_dim", [150, 150, 150])
                        )
                dpg.add_separator()

                # --- MIDDLE: Read-Only Math (Matrix & CoR) ---
                dpg.add_spacer(height=10)
                build_section_title("Affine Matrix", cfg_c["text_header"])
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
                build_section_title(
                    "Rigid Adjustment (Euler R = Rz Ry Rx)", cfg_c["text_header"]
                )
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

                # Translation Drag Floats
                build_stepped_slider(
                    "Tx ",
                    "drag_reg_tx",
                    callback=gui.reg_ui.on_reg_manual_changed,
                    step_callback=gui.reg_ui.on_reg_step_button_clicked,
                    min_val=-5000.0,
                    max_val=5000.0,
                    format="%.2f mm",
                )
                build_stepped_slider(
                    "Ty ",
                    "drag_reg_ty",
                    callback=gui.reg_ui.on_reg_manual_changed,
                    step_callback=gui.reg_ui.on_reg_step_button_clicked,
                    min_val=-5000.0,
                    max_val=5000.0,
                    format="%.2f mm",
                )
                build_stepped_slider(
                    "Tz ",
                    "drag_reg_tz",
                    callback=gui.reg_ui.on_reg_manual_changed,
                    step_callback=gui.reg_ui.on_reg_step_button_clicked,
                    min_val=-5000.0,
                    max_val=5000.0,
                    format="%.2f mm",
                )

                dpg.add_spacer(height=5)

                # Rotation Drag Floats (Euler)
                build_stepped_slider(
                    "Rx ",
                    "drag_reg_rx",
                    callback=gui.reg_ui.on_reg_manual_changed,
                    step_callback=gui.reg_ui.on_reg_step_button_clicked,
                    min_val=-360.0,
                    max_val=360.0,
                    format="%.2f \u00b0",
                )
                build_stepped_slider(
                    "Ry ",
                    "drag_reg_ry",
                    callback=gui.reg_ui.on_reg_manual_changed,
                    step_callback=gui.reg_ui.on_reg_step_button_clicked,
                    min_val=-360.0,
                    max_val=360.0,
                    format="%.2f \u00b0",
                )
                build_stepped_slider(
                    "Rz ",
                    "drag_reg_rz",
                    callback=gui.reg_ui.on_reg_manual_changed,
                    step_callback=gui.reg_ui.on_reg_step_button_clicked,
                    min_val=-360.0,
                    max_val=360.0,
                    format="%.2f \u00b0",
                )

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
                dpg.add_spacer(height=5)
                dpg.add_button(
                    label="Resample Display", width=-1, tag="btn_reg_resample", callback=gui.reg_ui.on_reg_resample_clicked
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

        is_dvf = getattr(vol, "is_dvf", False) if vol else False
        if dpg.does_item_exist("text_reg_dvf_warning"):
            dpg.configure_item("text_reg_dvf_warning", show=is_dvf)
        if dpg.does_item_exist("group_registration_controls"):
            dpg.configure_item("group_registration_controls", show=not is_dvf)

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

        if is_dvf:
            return

        if dpg.does_item_exist("text_reg_filename"):
            dpg.set_value("text_reg_filename", vs.space.transform_file)
        if dpg.does_item_exist("check_reg_apply"):
            dpg.set_value("check_reg_apply", vs.space.is_active)

        if vol:
            is_2d = min(vol.shape3d) == 1
            out_of_plane_tags = ["drag_reg_rx", "drag_reg_ry", "drag_reg_tz"]
            for tag in out_of_plane_tags:
                if dpg.does_item_exist(tag):
                    dpg.configure_item(tag, enabled=not is_2d)
                if dpg.does_item_exist(f"btn_{tag}_minus"):
                    dpg.configure_item(f"btn_{tag}_minus", enabled=not is_2d)
                if dpg.does_item_exist(f"btn_{tag}_plus"):
                    dpg.configure_item(f"btn_{tag}_plus", enabled=not is_2d)

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

    def trigger_resample(self, active_image_id):
        """
        [ASYNC_BOUNDARY]: Fires a background thread to resample the image.
        Math happens off-main-thread to keep the UI from freezing.
        """

        def _do_resample():
            active_vs = self.controller.view_states.get(active_image_id)
            if active_vs:
                active_vs.update_base_display_data()
                # Sync crosshair with the freshly resampled buffer so slice_idx and
                # values reflect the new geometry. Only needed if base image rotated!
                if active_vs.base_display_data is not None:
                    if active_vs.camera.crosshair_phys_coord is not None:
                        active_vs.update_crosshair_from_phys(active_vs.camera.crosshair_phys_coord)
                if active_vs.display.overlay_id:
                    active_vs.update_overlay_display_data(self.controller)
                    active_vs.is_data_dirty = True

            for vs in self.controller.view_states.values():
                if vs.display.overlay_id == active_image_id:
                    vs.update_overlay_display_data(self.controller)
                    vs.is_data_dirty = True

            self.controller.update_all_viewers_of_image(active_image_id)

            # Feedback when done
            self.controller.status_message = "Resampling complete"
            self.controller.ui_needs_refresh = True

        self.gui.show_status_message("Resampling display...", color=self.gui.ui_cfg["colors"]["working"])
        threading.Thread(target=_do_resample, daemon=True).start()

    # --- Callbacks ---
    def on_reg_load_clicked(self, sender, app_data, user_data):
        viewer = self.gui.context_viewer
        if not viewer or not viewer.image_id:
            return

        file_path = open_file_dialog(
            "Load Transform", multiple=False, extensions=[".tfm", ".txt", ".mat", ".xfm"]
        )
        if isinstance(file_path, str):
            vs = viewer.view_state
            # Capture the current world position of the crosshair BEFORE loading the new transform
            world_pos = vs.camera.crosshair_phys_coord

            if self.controller.load_transform(viewer.image_id, file_path):
                # Dynamically remember the exact file path for "Save"
                vs.space._full_transform_path = file_path
                self.gui.show_status_message(f"Loaded {os.path.basename(file_path)}")
                
                # Automatically enable the transform so the user sees it immediately
                vs.space.is_active = True

                if world_pos is not None:
                    vs.update_crosshair_from_phys(world_pos)

                self.controller.update_all_viewers_of_image(viewer.image_id)
                self.gui.update_sidebar_crosshair(viewer)
                self.pull_reg_sliders_from_transform()

                # Instantly trigger resample for loaded file
                self.trigger_resample(viewer.image_id)
                if dpg.does_item_exist("btn_reg_resample"):
                    dpg.bind_item_theme("btn_reg_resample", 0)
                self.controller.ui_needs_refresh = True
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
            self.controller.ui_needs_refresh = True
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
            self.controller.ui_needs_refresh = True

    def on_reg_reload_clicked(self, sender, app_data, user_data):
        viewer = self.gui.context_viewer
        if not viewer or not viewer.view_state:
            return

        full_path = getattr(viewer.view_state.space, "_full_transform_path", None)
        if full_path and os.path.exists(full_path):
            if self.controller.load_transform(viewer.image_id, full_path):
                self.controller.ui_needs_refresh = True
                self.pull_reg_sliders_from_transform()
                if dpg.does_item_exist("btn_reg_resample"):
                    dpg.bind_item_theme("btn_reg_resample", 0)
                self.trigger_resample(viewer.image_id)
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

    def on_reg_bake_clicked(self, sender, app_data, user_data):
        viewer = self.gui.context_viewer
        if not viewer or not viewer.image_id:
            return
        vs = viewer.view_state
        if not vs or not vs.space.transform or not vs.space.is_active:
            self.gui.show_status_message(
                "No active transform to bake.", color=self.gui.ui_cfg["colors"]["warning"]
            )
            return
        self.gui.show_status_message(
            "Baking transform...", color=self.gui.ui_cfg["colors"]["working"]
        )
        self.controller.bake_transform_to_volume(viewer.image_id)
        self.pull_reg_sliders_from_transform()
        self.controller.ui_needs_refresh = True

    def on_reg_apply_toggled(self, sender, app_data, user_data):
        viewer = self.gui.context_viewer
        if viewer and viewer.image_id:
            vs = viewer.view_state
            if vs:
                vs.space.is_active = app_data
                if dpg.does_item_exist("btn_reg_resample"):
                    dpg.bind_item_theme("btn_reg_resample", "orange_button_theme")
                self.controller.ui_needs_refresh = True

    def on_reg_step_changed(self, sender, app_data, user_data):
        speed = 1.0 if app_data == "Coarse" else 0.1
        for tag in self.SLIDER_TAGS:
            if dpg.does_item_exist(tag):
                dpg.configure_item(tag, speed=speed)
                
    def on_reg_resample_clicked(self, sender, app_data, user_data):
        viewer = self.gui.context_viewer
        if not viewer or not viewer.image_id:
            return
        vs_id = viewer.image_id
        
        if dpg.does_item_exist("btn_reg_resample"):
            dpg.bind_item_theme("btn_reg_resample", 0)
            
        self.trigger_resample(vs_id)

    def on_reg_manual_changed(self, sender, app_data, user_data):
        viewer = self.gui.context_viewer
        if not viewer or not viewer.image_id:
            return
        vs_id = viewer.image_id
        vals = [dpg.get_value(t) for t in self.SLIDER_TAGS]
        self.controller.update_transform_manual(
            vs_id, vals[3], vals[4], vals[5], vals[0], vals[1], vals[2]
        )
        if dpg.does_item_exist("btn_reg_resample"):
            dpg.bind_item_theme("btn_reg_resample", "orange_button_theme")
        self.controller.ui_needs_refresh = True

    def on_reg_reset_clicked(self, sender, app_data, user_data):
        viewer = self.gui.context_viewer
        if not viewer or not viewer.image_id:
            return
        for tag in self.SLIDER_TAGS:
            if dpg.does_item_exist(tag):
                dpg.set_value(tag, 0.0)
        self.controller.update_transform_manual(viewer.image_id, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
        if dpg.does_item_exist("btn_reg_resample"):
            dpg.bind_item_theme("btn_reg_resample", "orange_button_theme")
        self.pull_reg_sliders_from_transform()
        self.controller.ui_needs_refresh = True

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
        self.controller.update_transform_manual(
            viewer.image_id, vals[3], vals[4], vals[5], vals[0], vals[1], vals[2]
        )
        if dpg.does_item_exist("btn_reg_resample"):
            dpg.bind_item_theme("btn_reg_resample", "orange_button_theme")
        self.pull_reg_sliders_from_transform()
        self.controller.ui_needs_refresh = True

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
        if center is not None:
            vs.update_crosshair_from_phys(center)
        # State-Only Camera Snapping
        target_ids = self.controller.sync.get_sync_group_vs_ids(
            viewer.image_id, active_only=True
        )
        for tid in target_ids:
            self.controller.view_states[tid].camera.target_center = center

        self.controller.update_all_viewers_of_image(viewer.image_id)
        self.controller.sync.propagate_sync(viewer.image_id)
        self.controller.ui_needs_refresh = True

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
        if dpg.does_item_exist("btn_reg_resample"):
            dpg.bind_item_theme("btn_reg_resample", "orange_button_theme")
        self.controller.ui_needs_refresh = True

        self.gui.show_status_message("CoR snapped to Crosshair")
