import dearpygui.dearpygui as dpg


def build_tab_sync(gui):
    cfg_c = gui.ui_cfg["colors"]
    with dpg.tab(label="Sync", tag="tab_sync"):
        dpg.add_spacer(height=5)
        with dpg.group(horizontal=True):
            dpg.add_button(
                label="Link All", callback=lambda: gui.controller.link_all(), width=80
            )
            dpg.add_button(
                label="Unlink All",
                callback=lambda: gui.controller.unlink_all(),
                width=80,
            )
        dpg.add_spacer(height=5)
        dpg.add_text("Sync Groups", color=cfg_c["text_header"])
        dpg.add_separator()

        # Give the container a defined width so columns lay out nicely
        with dpg.child_window(border=False, no_scrollbar=True):
            dpg.add_group(tag="sync_list_container")


def refresh_sync_ui(gui):
    """Dynamically rebuilds the Sync list UI."""
    container = "sync_list_container"
    if not dpg.does_item_exist(container):
        return
    dpg.delete_item(container, children_only=True)
    gui.sync_label_tags.clear()

    max_active_group = max(
        [vs.sync_group for vs in gui.controller.view_states.values()] + [0]
    )
    num_groups = max(3, len(gui.controller.view_states), max_active_group)
    combo_items = ["None"] + [f"Group {i}" for i in range(1, num_groups + 1)]

    muted_col = gui.ui_cfg["colors"]["text_muted"]
    transparent = gui.ui_cfg["colors"]["transparent"]

    for vs_id, vs in gui.controller.view_states.items():
        with dpg.group(parent=container):
            # --- LINE 1: Image Name (Matches Images Tab) ---
            with dpg.group(horizontal=True):
                if vs.sync_group > 0:
                    dpg.add_text(f"[{vs.sync_group}]", color=muted_col)
                else:
                    dpg.add_text("   ", color=transparent)

                is_outdated = getattr(vs.volume, "_is_outdated", False)
                name_str = f"{vs.volume.name} *" if is_outdated else vs.volume.name

                lbl_id = dpg.add_text(name_str)

                if is_outdated:
                    dpg.configure_item(lbl_id, color=gui.ui_cfg["colors"]["outdated"])

                gui.sync_label_tags[vs_id] = lbl_id

            # --- LINE 2: Controls (Indented) ---
            with dpg.group(horizontal=True):
                dpg.add_spacer(width=15)  # Indent to match checkbox alignment
                dpg.add_combo(
                    items=combo_items,
                    default_value=(
                        "None" if not vs.sync_group else f"Group {vs.sync_group}"
                    ),
                    width=85,
                    user_data=vs_id,
                    callback=gui.on_sync_group_change,
                )
                dpg.add_spacer(width=5)

                is_rgb = getattr(vs.volume, "is_rgb", False)
                dpg.add_checkbox(
                    label="Sync W/L",
                    default_value=vs.sync_wl,
                    user_data=vs_id,
                    callback=gui.on_per_image_sync_wl_toggle,
                    enabled=not is_rgb,  # Don't allow W/L sync on RGB images
                )

            dpg.add_spacer(height=4)  # Tiny gap between image blocks


def build_tab_fusion(gui):
    cfg_c = gui.ui_cfg["colors"]
    with dpg.tab(label="Fusion", tag="tab_fusion"):  # Reverted label
        dpg.add_spacer(height=5)
        dpg.add_text("Active Overlay", color=cfg_c["text_header"])
        dpg.add_separator()
        with dpg.group(tag="image_fusion_group"):
            with dpg.group(horizontal=True):
                dpg.add_text("Base   ")
                dpg.add_text(
                    "-", tag="text_fusion_base_image", color=cfg_c["text_active"]
                )
            with dpg.group(horizontal=True):
                dpg.add_text("Target ")
                dpg.add_combo(
                    ["None"],
                    tag="combo_fusion_select",
                    width=-1,
                    callback=gui.fusion_ui.on_fusion_target_selected,
                )
            with dpg.group(horizontal=True):
                dpg.add_text("Opacity")
                dpg.add_slider_float(
                    tag="slider_fusion_opacity",
                    min_value=0.0,
                    max_value=1.0,
                    width=-1,
                    callback=gui.fusion_ui.on_fusion_opacity_changed,
                )
            with dpg.group(horizontal=True):
                dpg.add_text("Min Thr")
                dpg.add_input_float(
                    tag="input_fusion_threshold",
                    width=-1,
                    step=10,
                    callback=gui.fusion_ui.on_fusion_threshold_changed,
                )
            with dpg.group(horizontal=True):
                dpg.add_text("Mode   ")
                dpg.add_combo(
                    ["Alpha", "Registration", "Checkerboard"],
                    tag="combo_fusion_mode",
                    width=-1,
                    callback=gui.fusion_ui.on_fusion_mode_changed,
                )
            with dpg.group(
                horizontal=True, tag="group_fusion_checkerboard", show=False
            ):
                dpg.add_text("Square ")
                dpg.add_slider_float(
                    tag="slider_fusion_chk_size",
                    min_value=1.0,
                    max_value=200.0,
                    format="%.1f mm",
                    width=100,
                    callback=gui.fusion_ui.on_fusion_checkerboard_changed,
                )
                dpg.add_checkbox(
                    label="Swap",
                    tag="check_fusion_chk_swap",
                    callback=gui.fusion_ui.on_fusion_checkerboard_changed,
                )


def build_tab_rois(gui):
    cfg_c = gui.ui_cfg["colors"]
    cfg_l = gui.ui_cfg["layout"]

    with dpg.tab(label="ROIs", tag="tab_rois"):  # Reverted label
        dpg.add_spacer(height=5)

        # --- TOP: Load & Import ---
        with dpg.group(horizontal=True):
            dpg.add_button(
                label="Load ROI...",
                width=80,
                callback=gui.roi_ui.on_load_roi_clicked,
                tag="btn_roi_load",
            )
            dpg.add_combo(
                ["Binary Mask", "Label Map", "RT-Struct"],
                default_value="Binary Mask",
                width=-1,
                tag="combo_roi_type",
                callback=gui.roi_ui.on_roi_type_changed,
            )

        with dpg.group(horizontal=True, tag="group_roi_mode"):
            dpg.add_text("Rule:")
            dpg.add_combo(
                ["Ignore BG (val)", "Target FG (val)"],
                default_value="Ignore BG (val)",
                tag="combo_roi_mode",
                width=115,
            )
            dpg.add_text("Val:")
            dpg.add_input_float(
                default_value=0.0, step=1.0, width=-1, tag="input_roi_val"
            )

        dpg.add_spacer(height=10)

        # --- MIDDLE: The Master List ---
        with dpg.group(horizontal=True):
            # Show/Hide All Buttons
            btn_show = dpg.add_button(
                label="\uf06e",
                width=20,
                callback=gui.roi_ui.on_roi_show_all,
                tag="btn_roi_show_all",
            )
            btn_hide = dpg.add_button(
                label="\uf070",
                width=20,
                callback=gui.roi_ui.on_roi_hide_all,
                tag="btn_roi_hide_all",
            )
            if dpg.does_item_exist("icon_font_tag"):
                dpg.bind_item_font(btn_show, "icon_font_tag")
                dpg.bind_item_font(btn_hide, "icon_font_tag")

        dpg.add_separator()

        with dpg.child_window(
            tag="roi_list_window", height=150, border=False, no_scrollbar=True
        ):
            dpg.add_group(tag="roi_list_container")

        dpg.add_spacer(height=5)

        # Export Button
        dpg.add_button(
            label="Export All Stats to JSON",
            width=-1,
            callback=gui.roi_ui.on_export_roi_stats_clicked,
            tag="btn_roi_export_stats",
        )
        dpg.add_spacer(height=10)

        # --- BOTTOM: The Detail Panel ---
        dpg.add_text("Selected ROI Properties", color=cfg_c["text_header"])
        dpg.add_separator()

        with dpg.child_window(border=False, no_scrollbar=True):
            dpg.add_group(tag="roi_detail_container")


def build_tab_reg(gui):
    cfg_c = gui.ui_cfg["colors"]

    with dpg.tab(label="Reg", tag="tab_reg"):
        dpg.add_spacer(height=5)

        dpg.add_text(
            "No Image Selected",
            tag="text_reg_active_title",
            color=cfg_c["text_active"],
        )
        dpg.add_separator()
        dpg.add_spacer(height=5)

        # --- TOP: File Management & Apply ---
        with dpg.group(horizontal=True):
            dpg.add_button(
                label="Load .tfm/.txt",
                width=80,
                tag="btn_reg_load",
                callback=gui.reg_ui.on_reg_load_clicked,
            )
            dpg.add_button(
                label="Save",
                width=50,
                tag="btn_reg_save",
                callback=gui.reg_ui.on_reg_save_clicked,
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

        dpg.add_spacer(height=5)
        dpg.add_checkbox(
            label="Apply Transform to Viewers",
            tag="check_reg_apply",
            callback=gui.reg_ui.on_reg_apply_toggled,
        )
        dpg.add_separator()

        # --- MIDDLE: Read-Only Math (Matrix & CoR) ---
        dpg.add_text("Affine Matrix (Read-Only)", color=cfg_c["text_header"])
        with dpg.group(tag="group_reg_matrix"):
            # A clean 4x4 table to display the matrix values
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
            dpg.add_input_text(tag="input_reg_cor", width=150, readonly=True)
            dpg.add_button(
                label="Center", callback=gui.reg_ui.on_reg_center_cor_clicked
            )

        dpg.add_separator()

        # --- BOTTOM: Manual 6-DOF Tweaking ---
        dpg.add_text("Manual Adjustment (Rigid)", color=cfg_c["text_header"])

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
        with dpg.group(horizontal=True):
            dpg.add_text("Tx ")
            dpg.add_drag_float(
                tag="drag_reg_tx",
                width=-1,
                format="%.2f mm",
                speed=1.0,
                min_value=-5000.0,
                max_value=5000.0,
                callback=gui.reg_ui.on_reg_manual_changed,
            )
        with dpg.group(horizontal=True):
            dpg.add_text("Ty ")
            dpg.add_drag_float(
                tag="drag_reg_ty",
                width=-1,
                format="%.2f mm",
                speed=1.0,
                min_value=-5000.0,
                max_value=5000.0,
                callback=gui.reg_ui.on_reg_manual_changed,
            )
        with dpg.group(horizontal=True):
            dpg.add_text("Tz ")
            dpg.add_drag_float(
                tag="drag_reg_tz",
                width=-1,
                format="%.2f mm",
                speed=1.0,
                min_value=-5000.0,
                max_value=5000.0,
                callback=gui.reg_ui.on_reg_manual_changed,
            )

        dpg.add_spacer(height=5)

        # Rotation Drag Floats (Euler)
        with dpg.group(horizontal=True):
            dpg.add_text("Rx ")
            dpg.add_drag_float(
                tag="drag_reg_rx",
                width=-1,
                format="%.2f \u00b0",
                speed=1.0,
                min_value=-360.0,
                max_value=360.0,
                callback=gui.reg_ui.on_reg_manual_changed,
            )
        with dpg.group(horizontal=True):
            dpg.add_text("Ry ")
            dpg.add_drag_float(
                tag="drag_reg_ry",
                width=-1,
                format="%.2f \u00b0",
                speed=1.0,
                min_value=-360.0,
                max_value=360.0,
                callback=gui.reg_ui.on_reg_manual_changed,
            )
        with dpg.group(horizontal=True):
            dpg.add_text("Rz ")
            dpg.add_drag_float(
                tag="drag_reg_rz",
                width=-1,
                format="%.2f \u00b0",
                speed=1.0,
                min_value=-360.0,
                max_value=360.0,
                callback=gui.reg_ui.on_reg_manual_changed,
            )

        dpg.add_spacer(height=5)
        with dpg.group(horizontal=True):
            dpg.add_button(
                label="Reset to Zero",
                width=120,
                callback=gui.reg_ui.on_reg_reset_clicked,
            )
            dpg.add_button(
                label="Invert", width=-1, callback=gui.reg_ui.on_reg_invert_clicked
            )
