import math
import numpy as np
import dearpygui.dearpygui as dpg
from vvv.ui.ui_components import (
    build_stepped_slider,
    build_section_title,
    build_help_button,
)
from vvv.plugins.plugin_api import PluginTagMixin
from .control_registration import RegistrationPluginController


class RegistrationPluginUI(PluginTagMixin):
    def __init__(self, plugin_id: str, controller: RegistrationPluginController):
        self._plugin_id = plugin_id
        self._c = controller

    def _bind_icon_font(self, item):
        if dpg.does_item_exist("icon_font_tag"):
            dpg.bind_item_font(item, "icon_font_tag")

    def create_ui(self, parent, api) -> None:
        cfg_c = api.get_ui_config()["colors"]

        with dpg.group(parent=parent or 0, tag=self._plugin_id):
            build_section_title("Transform", cfg_c["text_header"])

            dpg.add_text(
                "No Image Selected",
                tag=self._t("text_reg_active_title"),
                color=cfg_c["text_active"],
            )

            dpg.add_text(
                "Transform disabled: DVF active",
                tag=self._t("text_reg_dvf_warning"),
                color=cfg_c.get("outdated", [255, 200, 50]),
                show=False,
            )

            with dpg.group(tag=self._t("group_registration_controls")):
                # --- TOP: File Management ---
                dpg.add_spacer(height=10)
                with dpg.group(horizontal=True):
                    btn_load = dpg.add_button(
                        label="\uf07c",
                        tag=self._t("btn_reg_load"),
                        callback=self._c.on_reg_load_clicked,
                    )
                    self._bind_icon_font(btn_load)
                    build_help_button(
                        "Load Transform matrix file (.tfm, .mat, .txt)",
                        api,
                    )

                    btn_save_as = dpg.add_button(
                        label="\uf019",
                        tag=self._t("btn_reg_save_as"),
                        callback=self._c.on_reg_save_as_clicked,
                    )
                    self._bind_icon_font(btn_save_as)
                    build_help_button(
                        "Save Transform matrix as... (choose file name)",
                        api,
                    )

                    btn_save = dpg.add_button(
                        label="\uf0c7",
                        tag=self._t("btn_reg_save"),
                        callback=self._c.on_reg_save_clicked,
                        show=False,
                    )
                    self._bind_icon_font(btn_save)
                    build_help_button(
                        "Save Transform matrix to current file",
                        api,
                    )

                    lbl_file = dpg.add_text(
                        "",
                        tag=self._t("text_reg_filename"),
                        color=cfg_c["text_dim"],
                        show=False,
                    )

                    btn_reload = dpg.add_button(
                        label="\uf01e",
                        width=20,
                        tag=self._t("btn_reg_reload"),
                        callback=self._c.on_reg_reload_clicked,
                    )
                    self._bind_icon_font(btn_reload)
                    if dpg.does_item_exist("icon_button_theme"):
                        dpg.bind_item_theme(btn_reload, "icon_button_theme")

                    build_help_button(
                        "A Transform file (.tfm, .mat, .txt) contains a rigid 3D spatial matrix (Translations and Rotations) that aligns this image with another.",
                        api,
                    )

                # --- CoR Goto and Set ---
                with dpg.group(tag=self._t("group_reg_cor")):
                    dpg.add_spacer(height=10)
                    with dpg.group(horizontal=True):
                        dpg.add_text("CoR:")
                        dpg.add_input_text(
                            tag=self._t("input_reg_cor"), width=-28, readonly=True
                        )
                        build_help_button(
                            "Center of Rotation (CoR): The 3D pivot point around which rotations are applied. Snapping it to your crosshair makes rotating around anatomical landmarks easy.",
                            api,
                        )
                    with dpg.group(horizontal=True):
                        b = dpg.add_button(
                            label="\uf05b ", callback=self._c.on_reg_center_cor_clicked
                        )
                        self._bind_icon_font(b)
                        dpg.add_button(
                            label="Snap CoR",
                            width=100,
                            callback=self._c.on_reg_cor_to_crosshair_clicked,
                        )

                # --- Rigid Adjustment ---
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
                        tag=self._t("radio_reg_step"),
                        callback=self._c.on_reg_step_changed,
                    )

                dpg.add_spacer(height=5)

                # Translation Drag Floats
                build_stepped_slider(
                    "Tx ",
                    self._t("drag_reg_tx"),
                    callback=self._c.on_reg_manual_changed,
                    step_callback=self._c.on_reg_step_button_clicked,
                    min_val=-5000.0,
                    max_val=5000.0,
                    format="%.2f mm",
                    gui=api,
                    help_text="X Translation (Left/Right shift in mm)",
                )
                build_stepped_slider(
                    "Ty ",
                    self._t("drag_reg_ty"),
                    callback=self._c.on_reg_manual_changed,
                    step_callback=self._c.on_reg_step_button_clicked,
                    min_val=-5000.0,
                    max_val=5000.0,
                    format="%.2f mm",
                    gui=api,
                    help_text="Y Translation (Anterior/Posterior shift in mm)",
                )
                build_stepped_slider(
                    "Tz ",
                    self._t("drag_reg_tz"),
                    callback=self._c.on_reg_manual_changed,
                    step_callback=self._c.on_reg_step_button_clicked,
                    min_val=-5000.0,
                    max_val=5000.0,
                    format="%.2f mm",
                    gui=api,
                    help_text="Z Translation (Superior/Inferior shift in mm)",
                )

                dpg.add_spacer(height=5)

                # Rotation Drag Floats (Euler)
                build_stepped_slider(
                    "Rx ",
                    self._t("drag_reg_rx"),
                    callback=self._c.on_reg_manual_changed,
                    step_callback=self._c.on_reg_step_button_clicked,
                    min_val=-360.0,
                    max_val=360.0,
                    format="%.2f \u00b0",
                    gui=api,
                    help_text="X Rotation (Pitch rotation around Left/Right axis in degrees)",
                )
                build_stepped_slider(
                    "Ry ",
                    self._t("drag_reg_ry"),
                    callback=self._c.on_reg_manual_changed,
                    step_callback=self._c.on_reg_step_button_clicked,
                    min_val=-360.0,
                    max_val=360.0,
                    format="%.2f \u00b0",
                    gui=api,
                    help_text="Y Rotation (Roll rotation around Anterior/Posterior axis in degrees)",
                )
                build_stepped_slider(
                    "Rz ",
                    self._t("drag_reg_rz"),
                    callback=self._c.on_reg_manual_changed,
                    step_callback=self._c.on_reg_step_button_clicked,
                    min_val=-360.0,
                    max_val=360.0,
                    format="%.2f \u00b0",
                    gui=api,
                    help_text="Z Rotation (Yaw rotation around Superior/Inferior axis in degrees)",
                )

                dpg.add_spacer(height=5)
                with dpg.group(horizontal=True):
                    dpg.add_button(
                        label="Reset to Identity",
                        callback=self._c.on_reg_reset_clicked,
                    )
                    dpg.add_button(
                        label="Invert Transform",
                        width=-1,
                        tag=self._t("btn_reg_invert"),
                        callback=self._c.on_reg_invert_clicked,
                    )
                dpg.add_spacer(height=5)

                # --- Resample & Bake ---
                dpg.add_checkbox(
                    label="Auto-Update Preview",
                    tag=self._t("check_reg_auto_resample"),
                    default_value=False,
                    callback=self._c.on_reg_auto_resample_toggled,
                )
                with dpg.group(horizontal=True):
                    dpg.add_button(
                        label="Update Preview",
                        width=-28,
                        tag=self._t("btn_reg_resample"),
                        callback=self._c.on_reg_resample_clicked,
                    )
                    build_help_button(
                        "Auto-Update: Automatically recalculates the full ITK resample when you stop dragging sliders.\nUpdate Preview: Manually trigger the high-quality ITK resample to confirm alignment.",
                        api,
                    )
                with dpg.group(horizontal=True):
                    dpg.add_button(
                        label="Resample Image",
                        tag=self._t("btn_reg_bake"),
                        callback=self._c.on_reg_bake_clicked,
                        width=-28,
                    )
                    build_help_button(
                        "Permanently applies the active spatial transform to the\n"
                        "underlying 3D pixel grid and resets the sliders to zero.\n"
                        "You can then 'Save' the resulting aligned image to disk.",
                        api,
                    )

                # --- Affine Matrix ---
                with dpg.group(tag=self._t("group_reg_matrix_section")):
                    dpg.add_spacer(height=10)
                    dpg.add_separator()
                    dpg.add_spacer(height=10)
                    build_section_title("Affine Matrix", cfg_c["text_header"])
                    with dpg.group(tag=self._t("group_reg_matrix")):
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
                                            tag=self._t(f"txt_reg_m_{r}_{c}"),
                                            color=cfg_c["text_dim"],
                                        )

    def update_ui(self, api) -> None:
        viewer = api.get_active_viewer()
        has_image = bool(viewer and viewer.view_state and viewer.volume)

        # Update active title
        title_tag = self._t("text_reg_active_title")
        if dpg.does_item_exist(title_tag):
            if has_image:
                name_str, is_outdated = api.get_image_display_name(viewer.image_id)
                dpg.set_value(title_tag, name_str)
                col = (
                    api.get_ui_config()["colors"]["outdated"]
                    if is_outdated
                    else api.get_ui_config()["colors"]["text_active"]
                )
                dpg.configure_item(title_tag, color=col)
            else:
                dpg.set_value(title_tag, "No Image Selected")
                dpg.configure_item(
                    title_tag, color=api.get_ui_config()["colors"]["text_active"]
                )

        # DVF warning
        warning_tag = self._t("text_reg_dvf_warning")
        is_dvf = False
        if has_image:
            vol = viewer.volume
            is_dvf = getattr(vol, "is_dvf", False) is True
        if dpg.does_item_exist(warning_tag):
            dpg.configure_item(warning_tag, show=(has_image and is_dvf))

        # Registration controls group
        ctrls_group = self._t("group_registration_controls")
        if dpg.does_item_exist(ctrls_group):
            dpg.configure_item(ctrls_group, show=(has_image and not is_dvf))

        if not has_image or is_dvf:
            return

        # Update button theme for Resample
        resample_btn = self._t("btn_reg_resample")
        if dpg.does_item_exist(resample_btn):
            needs_resample = False
            if has_image and viewer.view_state:
                needs_resample = getattr(viewer.view_state, "needs_resample", False)
            theme = "orange_button_theme" if needs_resample else 0
            dpg.bind_item_theme(resample_btn, theme)

        # Transform file text and Save button state
        file_tag = self._t("text_reg_filename")
        btn_save_tag = self._t("btn_reg_save")
        btn_reload_tag = self._t("btn_reg_reload")

        tf_file = viewer.view_state.space.transform_file if (has_image and getattr(viewer.view_state, "space", None)) else "None"
        has_transform_file = bool(tf_file and tf_file != "None")

        if dpg.does_item_exist(file_tag):
            if has_transform_file:
                dpg.set_value(file_tag, tf_file)
                dpg.configure_item(file_tag, show=True)
            else:
                dpg.set_value(file_tag, "")
                dpg.configure_item(file_tag, show=False)

        if dpg.does_item_exist(btn_save_tag):
            dpg.configure_item(btn_save_tag, show=has_transform_file)

        if dpg.does_item_exist(btn_reload_tag):
            dpg.configure_item(btn_reload_tag, show=has_transform_file)

        # Disable out-of-plane sliders if 2D
        if has_image:
            vol = viewer.volume
            is_2d = min(vol.shape3d) == 1 if vol else False
            out_of_plane_tags = ["drag_reg_rx", "drag_reg_ry", "drag_reg_tz"]
            for name in out_of_plane_tags:
                tag = self._t(name)
                if dpg.does_item_exist(tag):
                    dpg.configure_item(tag, enabled=not is_2d)
                if dpg.does_item_exist(f"btn_{tag}_minus"):
                    dpg.configure_item(f"btn_{tag}_minus", enabled=not is_2d)
                if dpg.does_item_exist(f"btn_{tag}_plus"):
                    dpg.configure_item(f"btn_{tag}_plus", enabled=not is_2d)

        # Update sliders from transform (if not active/dragging)
        slider_tags = [
            self._t("drag_reg_rx"),
            self._t("drag_reg_ry"),
            self._t("drag_reg_rz"),
            self._t("drag_reg_tx"),
            self._t("drag_reg_ty"),
            self._t("drag_reg_tz"),
        ]
        if has_image and viewer.view_state and viewer.view_state.space.transform:
            params = viewer.view_state.space.get_parameters()
            vals = [
                math.degrees(params[0]),
                math.degrees(params[1]),
                math.degrees(params[2]),
                params[3],
                params[4],
                params[5],
            ]
            for tag, val in zip(slider_tags, vals):
                if dpg.does_item_exist(tag) and not dpg.is_item_active(tag):
                    dpg.set_value(tag, val)
        else:
            for tag in slider_tags:
                if dpg.does_item_exist(tag) and not dpg.is_item_active(tag):
                    dpg.set_value(tag, 0.0)

        # Update affine matrix display
        if has_image and viewer.view_state and viewer.view_state.space.transform:
            matrix = np.array(viewer.view_state.space.transform.GetMatrix()).reshape(
                3, 3
            )
            params = viewer.view_state.space.get_parameters()

            for r in range(3):
                for c in range(3):
                    tag = self._t(f"txt_reg_m_{r}_{c}")
                    if dpg.does_item_exist(tag):
                        dpg.set_value(tag, f"{matrix[r, c]:.4f}")
                tag_t = self._t(f"txt_reg_m_{r}_3")
                if dpg.does_item_exist(tag_t):
                    dpg.set_value(tag_t, f"{params[r+3]:.2f}")

            for c, val in enumerate(["0.000", "0.000", "0.000", "1.000"]):
                tag_b = self._t(f"txt_reg_m_3_{c}")
                if dpg.does_item_exist(tag_b):
                    dpg.set_value(tag_b, val)
        else:
            for r in range(4):
                for c in range(4):
                    tag = self._t(f"txt_reg_m_{r}_{c}")
                    if dpg.does_item_exist(tag):
                        val = "1.000" if r == c else "0.000"
                        dpg.set_value(tag, val)

        # CoR text
        cor_tag = self._t("input_reg_cor")
        if dpg.does_item_exist(cor_tag):
            if has_image and viewer.view_state and viewer.view_state.space.transform:
                center = viewer.view_state.space.transform.GetCenter()
                dpg.set_value(
                    cor_tag,
                    f"{center[0]:.1f}, {center[1]:.1f}, {center[2]:.1f}",
                )
            elif has_image and viewer.volume:
                center = api.get_volume_physical_center(viewer.volume)
                if (
                    center is not None
                    and isinstance(center, (list, tuple, np.ndarray))
                    and len(center) >= 3
                ):
                    dpg.set_value(
                        cor_tag,
                        f"{center[0]:.1f}, {center[1]:.1f}, {center[2]:.1f}",
                    )
                else:
                    dpg.set_value(cor_tag, "0.0, 0.0, 0.0")
            else:
                dpg.set_value(cor_tag, "0.0, 0.0, 0.0")

    def pull_reg_sliders_from_transform(self) -> None:
        """ONLY call this when loading a file, switching images, or resetting. NOT during drag!"""
        api = self._c._api
        if not api:
            return
        viewer = api.get_active_viewer()
        if not viewer or not viewer.image_id:
            return

        vs = viewer.view_state
        slider_tags = [
            self._t("drag_reg_rx"),
            self._t("drag_reg_ry"),
            self._t("drag_reg_rz"),
            self._t("drag_reg_tx"),
            self._t("drag_reg_ty"),
            self._t("drag_reg_tz"),
        ]
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

            for tag, val in zip(slider_tags, vals):
                if dpg.does_item_exist(tag):
                    dpg.set_value(tag, val)
        else:
            for tag in slider_tags:
                if dpg.does_item_exist(tag):
                    dpg.set_value(tag, 0.0)
