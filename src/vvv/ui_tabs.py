import dearpygui.dearpygui as dpg


import dearpygui.dearpygui as dpg


def build_tab_sync(gui):
    cfg_c = gui.ui_cfg["colors"]
    with dpg.tab(label="Sync", tag="tab_sync"):  # Reverted label
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
        dpg.add_group(tag="sync_list_container")


def build_tab_fusion(gui):
    cfg_c = gui.ui_cfg["colors"]
    with dpg.tab(label="Overlay", tag="tab_fusion"):  # Reverted label
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
                    tag="combo_overlay_select",
                    width=-1,
                    callback=gui.on_overlay_selected,
                )
            with dpg.group(horizontal=True):
                dpg.add_text("Opacity")
                dpg.add_slider_float(
                    tag="slider_overlay_opacity",
                    min_value=0.0,
                    max_value=1.0,
                    width=-1,
                    callback=gui.on_opacity_changed,
                )
            with dpg.group(horizontal=True):
                dpg.add_text("Min Thr")
                dpg.add_input_float(
                    tag="input_overlay_threshold",
                    width=-1,
                    step=10,
                    callback=gui.on_threshold_changed,
                )
            with dpg.group(horizontal=True):
                dpg.add_text("Mode   ")
                dpg.add_combo(
                    ["Alpha", "Registration", "Checkerboard"],
                    tag="combo_overlay_mode",
                    width=-1,
                    callback=gui.on_overlay_mode_changed,
                )
            with dpg.group(horizontal=True, tag="group_checkerboard", show=False):
                dpg.add_text("Square ")
                dpg.add_slider_float(
                    tag="slider_chk_size",
                    min_value=1.0,
                    max_value=200.0,
                    format="%.1f mm",
                    width=100,
                    callback=gui.on_checkerboard_changed,
                )
                dpg.add_checkbox(
                    label="Swap",
                    tag="check_chk_swap",
                    callback=gui.on_checkerboard_changed,
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
                callback=gui.on_load_roi_clicked,
                tag="btn_roi_load",
            )
            dpg.add_combo(
                ["Binary Mask", "Label Map", "RT-Struct"],
                default_value="Binary Mask",
                width=-1,
                tag="combo_roi_type",
                callback=gui.on_roi_type_changed,
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
                callback=gui.on_roi_show_all,
                tag="btn_roi_show_all",
            )
            btn_hide = dpg.add_button(
                label="\uf070",
                width=20,
                callback=gui.on_roi_hide_all,
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
            callback=gui.on_export_roi_stats_clicked,
            tag="btn_roi_export_stats",
        )
        dpg.add_spacer(height=10)

        # --- BOTTOM: The Detail Panel ---
        dpg.add_text("Selected ROI Properties", color=cfg_c["text_header"])
        dpg.add_separator()

        with dpg.child_window(border=False, no_scrollbar=True):
            dpg.add_group(tag="roi_detail_container")
